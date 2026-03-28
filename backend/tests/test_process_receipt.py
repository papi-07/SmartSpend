"""
Unit tests for SmartSpend process_receipt Lambda handler.
"""

import json
import sys
import os
import importlib.util
from unittest.mock import patch, MagicMock
from decimal import Decimal

_fn_dir = os.path.join(os.path.dirname(__file__), "..", "functions", "process_receipt")
sys.path.insert(0, _fn_dir)
_spec = importlib.util.spec_from_file_location("process_receipt_app", os.path.join(_fn_dir, "app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["process_receipt_app"] = _mod
_spec.loader.exec_module(_mod)

lambda_handler = _mod.lambda_handler
_extract_user_id_from_key = _mod._extract_user_id_from_key
MOD = "process_receipt_app"


def _make_s3_event(bucket="smartspend-receipts-test", key="receipts/user-123/abc.jpg"):
    return {
        "Records": [{
            "s3": {
                "bucket": {"name": bucket},
                "object": {"key": key},
            }
        }]
    }


MOCK_TEXTRACT_RESPONSE = {
    "ExpenseDocuments": [{
        "SummaryFields": [
            {"Type": {"Text": "VENDOR_NAME", "Confidence": 95.0},
             "ValueDetection": {"Text": "Swiggy", "Confidence": 92.0}},
            {"Type": {"Text": "TOTAL", "Confidence": 98.0},
             "ValueDetection": {"Text": "₹450.00", "Confidence": 97.0}},
            {"Type": {"Text": "INVOICE_RECEIPT_DATE", "Confidence": 90.0},
             "ValueDetection": {"Text": "15/03/2026", "Confidence": 88.0}},
        ],
        "LineItemGroups": [],
    }]
}

MOCK_NO_AMOUNT_RESPONSE = {
    "ExpenseDocuments": [{
        "SummaryFields": [
            {"Type": {"Text": "VENDOR_NAME", "Confidence": 50.0},
             "ValueDetection": {"Text": "???", "Confidence": 40.0}},
        ],
        "LineItemGroups": [],
    }]
}


class TestExtractUserId:
    def test_valid_key(self):
        assert _extract_user_id_from_key("receipts/user-123/abc.jpg") == "user-123"

    def test_invalid_key_no_prefix(self):
        assert _extract_user_id_from_key("images/user-123/abc.jpg") is None

    def test_invalid_key_too_short(self):
        assert _extract_user_id_from_key("receipts/") is None


class TestProcessReceiptHandler:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_s3_operation")
    @patch(f"{MOD}.track_textract_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.check_budget", return_value=None)
    @patch(f"{MOD}.check_anomaly", return_value=(False, Decimal("0"), ""))
    @patch(f"{MOD}.put_item", return_value={"success": True})
    @patch(f"{MOD}.boto3")
    def test_successful_ocr(self, mock_boto, mock_put, mock_anom, mock_budget, mock_ddb,
                            mock_textract_track, mock_s3track, mock_track):
        mock_textract = MagicMock()
        mock_boto.client.return_value = mock_textract
        mock_textract.analyze_expense.return_value = MOCK_TEXTRACT_RESPONSE
        mock_textract.exceptions = MagicMock()

        resp = lambda_handler(_make_s3_event(), None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 200
        assert body["merchant"] == "Swiggy"
        assert body["amount"] == 450.0
        assert body["date"] == "2026-03-15"
        assert body["category"] == "Food"
        assert "expenseId" in body

        # Verify DynamoDB was called with correct item
        mock_put.assert_called_once()
        saved_item = mock_put.call_args[0][1]
        assert saved_item["source"] == "receipt-ocr"
        assert saved_item["amountPaise"] == 45000
        assert saved_item["receiptKey"] == "receipts/user-123/abc.jpg"

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_s3_operation")
    @patch(f"{MOD}.track_textract_call")
    @patch(f"{MOD}.boto3")
    def test_no_amount_detected(self, mock_boto, mock_textract_track, mock_s3track, mock_track):
        mock_textract = MagicMock()
        mock_boto.client.return_value = mock_textract
        mock_textract.analyze_expense.return_value = MOCK_NO_AMOUNT_RESPONSE
        mock_textract.exceptions = MagicMock()

        resp = lambda_handler(_make_s3_event(), None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 200
        assert body["needsManualReview"] is True
        assert "no valid amount" in body["message"].lower()

    @patch(f"{MOD}.track_lambda_invocation")
    def test_no_records(self, mock_track):
        resp = lambda_handler({"Records": []}, None)
        assert resp["statusCode"] == 200
        assert "No records" in resp["body"]

    @patch(f"{MOD}.track_lambda_invocation")
    def test_invalid_key_format(self, mock_track):
        event = _make_s3_event(key="images/random/file.jpg")
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_s3_operation")
    @patch(f"{MOD}.track_textract_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.check_budget", return_value=None)
    @patch(f"{MOD}.check_anomaly", return_value=(True, Decimal("10000"), "Anomaly!"))
    @patch(f"{MOD}.publish_anomaly_alert")
    @patch(f"{MOD}.put_item", return_value={"success": True})
    @patch(f"{MOD}.boto3")
    def test_anomaly_triggers_alert(self, mock_boto, mock_put, mock_pub,
                                    mock_anom, mock_budget, mock_ddb,
                                    mock_textract_track,
                                    mock_s3track, mock_track):
        mock_textract = MagicMock()
        mock_s3_client = MagicMock()

        def client_factory(service, **kwargs):
            if service == "textract":
                return mock_textract
            return mock_s3_client

        mock_boto.client.side_effect = client_factory
        mock_textract.analyze_expense.return_value = MOCK_TEXTRACT_RESPONSE
        mock_textract.exceptions = MagicMock()
        mock_s3_client.head_object.return_value = {"Metadata": {}}

        resp = lambda_handler(_make_s3_event(), None)
        body = json.loads(resp["body"])

        assert body["isAnomaly"] is True
        mock_pub.assert_called_once()
