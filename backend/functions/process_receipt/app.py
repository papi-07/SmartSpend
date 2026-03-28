"""
SmartSpend — Process Receipt Lambda
=====================================
Triggered automatically by S3 PutObject event when a receipt image
is uploaded to the receipts/ prefix.

Flow:
  1. Receive S3 event with bucket name and object key
  2. Call Amazon Textract AnalyzeExpense on the image
  3. Parse response to extract merchant, amount, date, line items
  4. Auto-categorize via rule-based categorizer
  5. Check for anomaly via shared anomaly_utils
  6. Save expense to DynamoDB with source="receipt-ocr"
  7. If anomaly → publish SNS alert
  8. Track all resource usage

NOT triggered via API Gateway — no auth headers needed.
"""

import os
import json
import time
import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import unquote_plus

import boto3

from db_utils import put_item
from categorizer import categorize_expense
from textract_parser import parse_textract_expense, LOW_CONFIDENCE_THRESHOLD
from anomaly_utils import check_anomaly, publish_anomaly_alert, check_budget
from resource_tracker import (
    track_lambda_invocation, track_textract_call, track_dynamodb_operation,
    track_s3_operation, track_sns_publish,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

EXPENSES_TABLE = os.environ.get("EXPENSES_TABLE", "SmartSpend-Expenses")


def _extract_user_id_from_key(s3_key):
    """Extract userId from S3 key format: receipts/{userId}/{uuid}.{ext}"""
    parts = s3_key.split("/")
    if len(parts) >= 3 and parts[0] == "receipts":
        return parts[1]
    return None


def lambda_handler(event, context):
    """Handle S3 PutObject event — process uploaded receipt with Textract."""
    start_time = time.time()

    try:
        # Parse S3 event
        records = event.get("Records", [])
        if not records:
            logger.warning("No records in S3 event")
            return {"statusCode": 200, "body": "No records to process"}

        record = records[0]
        s3_info = record.get("s3", {})
        bucket_name = s3_info.get("bucket", {}).get("name", "")
        s3_key = unquote_plus(s3_info.get("object", {}).get("key", ""))

        if not bucket_name or not s3_key:
            logger.error("Missing bucket or key in S3 event")
            return {"statusCode": 400, "body": "Invalid S3 event"}

        logger.info("Processing receipt: s3://%s/%s", bucket_name, s3_key)

        # Extract userId from S3 key
        user_id = _extract_user_id_from_key(s3_key)
        if not user_id:
            logger.error("Cannot extract userId from key: %s", s3_key)
            return {"statusCode": 400, "body": "Invalid S3 key format"}

        track_s3_operation("process_receipt", "get")

        # ─── Call Textract AnalyzeExpense ──────────────────────
        textract = boto3.client("textract", region_name=os.environ.get("REGION", "us-east-1"))

        try:
            textract_response = textract.analyze_expense(
                Document={
                    "S3Object": {
                        "Bucket": bucket_name,
                        "Name": s3_key,
                    }
                }
            )
            track_textract_call("process_receipt", pages=1)
        except textract.exceptions.UnsupportedDocumentException:
            logger.warning("Textract: unsupported document format for %s", s3_key)
            return {"statusCode": 200, "body": "Unsupported document format — skipping OCR"}
        except textract.exceptions.InvalidS3ObjectException:
            logger.error("Textract: invalid S3 object %s/%s", bucket_name, s3_key)
            return {"statusCode": 400, "body": "Invalid S3 object"}
        except Exception as e:
            logger.error("Textract call failed: %s", str(e))
            return {"statusCode": 500, "body": f"Textract error: {str(e)}"}

        # ─── Parse Textract response ──────────────────────────
        parsed = parse_textract_expense(textract_response)

        merchant_name = parsed["merchant_name"] or "Unknown Merchant"
        total_amount = parsed["total_amount"]
        receipt_date = parsed["date"]
        ocr_confidence = parsed["confidence"]
        line_items = parsed["line_items"]
        low_conf_fields = parsed["low_confidence_fields"]

        logger.info(
            "Textract extracted: merchant=%s, amount=%s, date=%s, confidence=%.2f, line_items=%d",
            merchant_name, total_amount, receipt_date, ocr_confidence, len(line_items),
        )

        # Use today's date if receipt date not detected
        if not receipt_date:
            receipt_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            logger.info("No date detected — using today: %s", receipt_date)

        # If no total amount detected, skip expense creation
        if total_amount is None or total_amount <= 0:
            logger.warning("No valid total amount detected for %s — skipping expense creation", s3_key)
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "Receipt processed but no valid amount detected",
                    "merchant": merchant_name,
                    "ocrConfidence": ocr_confidence,
                    "receiptKey": s3_key,
                    "needsManualReview": True,
                }),
            }

        # ─── Categorize and create expense ─────────────────────
        category, cat_confidence = categorize_expense(merchant_name)

        expense_id = str(uuid.uuid4())
        amount_paise = int(round(total_amount * 100))
        now = datetime.now(timezone.utc).isoformat()

        # Build expense item
        item = {
            "userId": user_id,
            "expenseId": expense_id,
            "amount": amount_paise,
            "amountPaise": amount_paise,
            "merchant": merchant_name,
            "category": category,
            "categoryConfidence": Decimal(str(round(cat_confidence, 2))),
            "date": receipt_date,
            "notes": "",
            "tags": ["receipt-ocr"],
            "isRecurring": False,
            "recurringFrequency": "",
            "source": "receipt-ocr",
            "receiptKey": s3_key,
            "ocrConfidence": Decimal(str(round(ocr_confidence, 3))),
            "ocrRawFields": json.dumps(parsed["raw_fields"]),
            "needsReview": ocr_confidence < LOW_CONFIDENCE_THRESHOLD or len(low_conf_fields) > 0,
            "createdAt": now,
            "updatedAt": now,
        }

        # Add line items if present
        if line_items:
            item["lineItems"] = json.dumps(line_items)

        # Save to DynamoDB
        result = put_item(EXPENSES_TABLE, item)
        if not result.get("success"):
            logger.error("Failed to save OCR expense: %s", result.get("error", "unknown"))
            return {"statusCode": 500, "body": "Failed to save expense"}
        track_dynamodb_operation("process_receipt", "write", units=1)

        logger.info(
            "OCR expense created: expenseId=%s, merchant=%s, amount=₹%.2f, category=%s",
            expense_id, merchant_name, total_amount, category,
        )

        # ─── Anomaly detection ─────────────────────────────────
        is_anomaly, avg, anomaly_msg = check_anomaly(
            user_id, category, amount_paise, caller="process_receipt"
        )

        if is_anomaly:
            # Try to get user email from S3 object metadata
            try:
                s3 = boto3.client("s3", region_name=os.environ.get("REGION", "us-east-1"))
                obj_meta = s3.head_object(Bucket=bucket_name, Key=s3_key)
                user_email = obj_meta.get("Metadata", {}).get("useremail", "")
            except Exception:
                user_email = ""

            publish_anomaly_alert(user_id, user_email, anomaly_msg, caller="process_receipt")

        # Budget check — alert only when threshold is crossed
        try:
            s3_client = boto3.client("s3", region_name=os.environ.get("REGION", "us-east-1"))
            obj_meta = s3_client.head_object(Bucket=bucket_name, Key=s3_key)
            user_email_for_budget = obj_meta.get("Metadata", {}).get("useremail", "")
        except Exception:
            user_email_for_budget = ""
        budget_info = check_budget(
            user_id, user_email_for_budget, category,
            caller="process_receipt",
            current_amount_paise=amount_paise,
        )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Receipt processed successfully",
                "expenseId": expense_id,
                "merchant": merchant_name,
                "amount": total_amount,
                "category": category,
                "date": receipt_date,
                "ocrConfidence": ocr_confidence,
                "needsReview": item["needsReview"],
                "isAnomaly": is_anomaly,
                "budgetAlert": budget_info is not None and budget_info.get("alertSent", False),
                "lineItems": len(line_items),
            }),
        }

    except Exception as e:
        logger.error("process_receipt failed: %s", str(e))
        return {"statusCode": 500, "body": f"Internal error: {str(e)}"}
    finally:
        track_lambda_invocation("process_receipt", start_time)
