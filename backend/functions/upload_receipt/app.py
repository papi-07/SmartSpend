"""
SmartSpend — Upload Receipt Lambda
====================================
Accepts a base64-encoded receipt image via POST, validates it,
uploads to S3, and returns a pre-signed URL for immediate preview.

Does NOT call Textract — the S3 upload triggers process_receipt
via S3 Event Notification automatically.

Triggered by: POST /receipts/upload via API Gateway (Cognito-authorized)

Request body (JSON):
  { "image": "<base64-encoded image data>", "filename": "receipt.jpg" }
  OR multipart binary via API Gateway with isBase64Encoded=true
"""

import os
import json
import time
import uuid
import base64
import logging

import boto3

from auth_utils import get_user_id
from response_utils import created, error, server_error, options_response
from resource_tracker import (
    track_lambda_invocation, track_s3_operation, track_api_gateway_call,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

RECEIPTS_BUCKET = os.environ.get("RECEIPTS_BUCKET", "")
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
PRESIGNED_URL_EXPIRY = 3600  # 1 hour

ALLOWED_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/jpg": "jpg",
}

# Map file extensions to content types
EXT_TO_CONTENT_TYPE = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}


def _detect_content_type(filename, provided_type=None):
    """Detect content type from filename extension or provided type."""
    if provided_type and provided_type in ALLOWED_TYPES:
        return provided_type, ALLOWED_TYPES[provided_type]

    if filename:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in EXT_TO_CONTENT_TYPE:
            return EXT_TO_CONTENT_TYPE[ext], ext if ext != "jpeg" else "jpg"

    return None, None


def lambda_handler(event, context):
    """Handle POST /receipts/upload — upload a receipt image to S3."""
    start_time = time.time()

    try:
        if event.get("httpMethod") == "OPTIONS":
            return options_response()

        track_api_gateway_call("upload_receipt")

        user_id = get_user_id(event)

        if not RECEIPTS_BUCKET:
            return server_error("RECEIPTS_BUCKET not configured")

        # Parse request body
        try:
            body = json.loads(event.get("body") or "{}")
        except (json.JSONDecodeError, TypeError):
            # Might be raw base64 binary from API Gateway
            body = {}

        image_b64 = body.get("image", "")
        filename = body.get("filename", "receipt.jpg")
        content_type_hint = body.get("contentType", "")

        # If API Gateway sent base64-encoded binary body
        if not image_b64 and event.get("isBase64Encoded"):
            image_b64 = event.get("body", "")

        if not image_b64:
            return error("'image' field is required (base64-encoded image data)")

        # Decode base64
        try:
            image_data = base64.b64decode(image_b64)
        except Exception:
            return error("Invalid base64 image data")

        # Validate file size
        if len(image_data) > MAX_FILE_SIZE:
            return error(f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB")

        if len(image_data) < 100:
            return error("File too small to be a valid image")

        # Detect and validate content type
        content_type, ext = _detect_content_type(filename, content_type_hint)

        # Also check magic bytes
        if image_data[:2] == b'\xff\xd8':
            content_type = content_type or "image/jpeg"
            ext = ext or "jpg"
        elif image_data[:8] == b'\x89PNG\r\n\x1a\n':
            content_type = content_type or "image/png"
            ext = ext or "png"

        if not content_type or content_type not in ALLOWED_TYPES:
            return error("Invalid file type. Only JPEG and PNG images are allowed")

        # Generate unique S3 key
        receipt_id = str(uuid.uuid4())
        s3_key = f"receipts/{user_id}/{receipt_id}.{ext}"

        # Upload to S3
        s3 = boto3.client("s3", region_name=os.environ.get("REGION", "us-east-1"))
        s3.put_object(
            Bucket=RECEIPTS_BUCKET,
            Key=s3_key,
            Body=image_data,
            ContentType=content_type,
            Metadata={
                "userId": user_id,
                "originalFilename": filename[:255],
            },
        )
        track_s3_operation("upload_receipt", "put", size_bytes=len(image_data))

        # Generate pre-signed URL for immediate preview
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": RECEIPTS_BUCKET, "Key": s3_key},
            ExpiresIn=PRESIGNED_URL_EXPIRY,
        )

        logger.info(
            "Receipt uploaded: s3://%s/%s (%d bytes, %s)",
            RECEIPTS_BUCKET, s3_key, len(image_data), content_type,
        )

        return created({
            "receiptKey": s3_key,
            "receiptId": receipt_id,
            "previewUrl": presigned_url,
            "fileSize": len(image_data),
            "contentType": content_type,
            "message": "Receipt uploaded. OCR processing will begin automatically.",
        })

    except Exception as e:
        logger.error("upload_receipt failed: %s", str(e))
        return server_error("Internal error uploading receipt")
    finally:
        track_lambda_invocation("upload_receipt", start_time)
