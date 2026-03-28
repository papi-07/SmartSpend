"""
Unit tests for SmartSpend upload_receipt Lambda handler.
"""

import json
import base64
import sys
import os
import importlib.util
from unittest.mock import patch, MagicMock

_fn_dir = os.path.join(os.path.dirname(__file__), "..", "functions", "upload_receipt")
sys.path.insert(0, _fn_dir)
_spec = importlib.util.spec_from_file_location("upload_receipt_app", os.path.join(_fn_dir, "app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["upload_receipt_app"] = _mod
_spec.loader.exec_module(_mod)

lambda_handler = _mod.lambda_handler
MOD = "upload_receipt_app"

# Minimal valid JPEG header (magic bytes)
FAKE_JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 200
FAKE_PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 200
FAKE_JPEG_B64 = base64.b64encode(FAKE_JPEG).decode()
FAKE_PNG_B64 = base64.b64encode(FAKE_PNG).decode()


def _make_event(body=None, user_id="test-user-123"):
    return {
        "httpMethod": "POST",
        "requestContext": {"authorizer": {"claims": {"sub": user_id}}},
        "body": json.dumps(body) if body else None,
        "headers": {},
        "isBase64Encoded": False,
    }


class TestUploadReceiptValidation:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_missing_image(self, mock_apigw, mock_track):
        resp = lambda_handler(_make_event({"filename": "test.jpg"}), None)
        assert resp["statusCode"] == 400
        assert "image" in json.loads(resp["body"])["error"].lower()

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_invalid_base64(self, mock_apigw, mock_track):
        resp = lambda_handler(_make_event({"image": "not-valid-base64!!!"}), None)
        assert resp["statusCode"] == 400

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_file_too_small(self, mock_apigw, mock_track):
        tiny = base64.b64encode(b'\xff\xd8' + b'\x00' * 10).decode()
        resp = lambda_handler(_make_event({"image": tiny, "filename": "t.jpg"}), None)
        assert resp["statusCode"] == 400
        assert "small" in json.loads(resp["body"])["error"].lower()

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_invalid_file_type(self, mock_apigw, mock_track):
        # GIF magic bytes — not allowed
        gif = base64.b64encode(b'GIF89a' + b'\x00' * 200).decode()
        resp = lambda_handler(_make_event({"image": gif, "filename": "test.gif"}), None)
        assert resp["statusCode"] == 400
        assert "JPEG" in json.loads(resp["body"])["error"] or "PNG" in json.loads(resp["body"])["error"]

    @patch(f"{MOD}.track_lambda_invocation")
    def test_options_preflight(self, mock_track):
        event = _make_event()
        event["httpMethod"] = "OPTIONS"
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200


class TestUploadReceiptSuccess:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_s3_operation")
    @patch(f"{MOD}.boto3")
    def test_uploads_jpeg(self, mock_boto, mock_s3track, mock_apigw, mock_track):
        mock_s3 = MagicMock()
        mock_boto.client.return_value = mock_s3
        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/presigned"

        resp = lambda_handler(_make_event({
            "image": FAKE_JPEG_B64,
            "filename": "receipt.jpg",
        }), None)

        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["receiptKey"].startswith("receipts/test-user-123/")
        assert body["receiptKey"].endswith(".jpg")
        assert body["previewUrl"] == "https://s3.example.com/presigned"
        assert body["contentType"] == "image/jpeg"
        assert "receiptId" in body

        mock_s3.put_object.assert_called_once()

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_s3_operation")
    @patch(f"{MOD}.boto3")
    def test_uploads_png(self, mock_boto, mock_s3track, mock_apigw, mock_track):
        mock_s3 = MagicMock()
        mock_boto.client.return_value = mock_s3
        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/presigned"

        resp = lambda_handler(_make_event({
            "image": FAKE_PNG_B64,
            "filename": "receipt.png",
        }), None)

        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["receiptKey"].endswith(".png")
        assert body["contentType"] == "image/png"
