"""
Unit tests for SmartSpend create_expense Lambda handler.
"""

import json
import time
import sys
import os
import importlib.util
from unittest.mock import patch, MagicMock
from decimal import Decimal

# Load function module with unique name to avoid collisions
_fn_dir = os.path.join(os.path.dirname(__file__), "..", "functions", "create_expense")
sys.path.insert(0, _fn_dir)
_spec = importlib.util.spec_from_file_location("create_expense_app", os.path.join(_fn_dir, "app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["create_expense_app"] = _mod
_spec.loader.exec_module(_mod)

lambda_handler = _mod.lambda_handler
MOD = "create_expense_app"


def _make_event(body=None, user_id="test-user-123", method="POST"):
    return {
        "httpMethod": method,
        "requestContext": {"authorizer": {"claims": {"sub": user_id, "email": "test@example.com"}}},
        "body": json.dumps(body) if body else None,
        "headers": {},
    }


class TestCreateExpenseValidation:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_missing_amount(self, mock_apigw, mock_track):
        event = _make_event({"merchant": "Swiggy", "date": "2026-03-01"})
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400
        assert "amount" in json.loads(resp["body"])["error"]

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_missing_merchant(self, mock_apigw, mock_track):
        event = _make_event({"amount": 100, "date": "2026-03-01"})
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400
        assert "merchant" in json.loads(resp["body"])["error"]

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_missing_date(self, mock_apigw, mock_track):
        event = _make_event({"amount": 100, "merchant": "Swiggy"})
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400
        assert "date" in json.loads(resp["body"])["error"]

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_negative_amount(self, mock_apigw, mock_track):
        event = _make_event({"amount": -50, "merchant": "Swiggy", "date": "2026-03-01"})
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400
        assert "positive" in json.loads(resp["body"])["error"]

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_zero_amount(self, mock_apigw, mock_track):
        event = _make_event({"amount": 0, "merchant": "Swiggy", "date": "2026-03-01"})
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_invalid_date_format(self, mock_apigw, mock_track):
        event = _make_event({"amount": 100, "merchant": "Swiggy", "date": "01-03-2026"})
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400
        assert "YYYY-MM-DD" in json.loads(resp["body"])["error"]

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_invalid_json_body(self, mock_apigw, mock_track):
        event = _make_event()
        event["body"] = "not json"
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_string_amount(self, mock_apigw, mock_track):
        event = _make_event({"amount": "not-a-number", "merchant": "Swiggy", "date": "2026-03-01"})
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400

    @patch(f"{MOD}.track_lambda_invocation")
    def test_options_returns_200(self, mock_track):
        event = _make_event()
        event["httpMethod"] = "OPTIONS"
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200


class TestCreateExpenseSuccess:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.check_budget", return_value=None)
    @patch(f"{MOD}.check_anomaly", return_value=(False, Decimal("0"), ""))
    @patch(f"{MOD}.put_item", return_value={"success": True})
    def test_creates_expense_with_auto_category(self, mock_put, mock_anomaly, mock_budget, mock_ddb, mock_apigw, mock_track):
        event = _make_event({"amount": 250.50, "merchant": "Swiggy", "date": "2026-03-15"})
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["amount"] == 250.50
        assert body["amountPaise"] == 25050
        assert body["merchant"] == "Swiggy"
        assert body["category"] == "Food"
        assert body["categoryConfidence"] > 0
        assert "expenseId" in body
        assert body["source"] == "manual"

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.check_budget", return_value=None)
    @patch(f"{MOD}.check_anomaly", return_value=(False, Decimal("0"), ""))
    @patch(f"{MOD}.put_item", return_value={"success": True})
    def test_uses_provided_category(self, mock_put, mock_anomaly, mock_budget, mock_ddb, mock_apigw, mock_track):
        event = _make_event({
            "amount": 100, "merchant": "Unknown Store",
            "date": "2026-03-15", "category": "Shopping"
        })
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["category"] == "Shopping"

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.check_budget", return_value=None)
    @patch(f"{MOD}.check_anomaly", return_value=(False, Decimal("0"), ""))
    @patch(f"{MOD}.put_item", return_value={"success": True})
    def test_stores_optional_fields(self, mock_put, mock_anomaly, mock_budget, mock_ddb, mock_apigw, mock_track):
        event = _make_event({
            "amount": 100, "merchant": "Netflix", "date": "2026-03-15",
            "notes": "Monthly sub", "tags": ["subscription", "entertainment"],
            "isRecurring": True, "recurringFrequency": "monthly"
        })
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["notes"] == "Monthly sub"
        assert body["tags"] == ["subscription", "entertainment"]
        assert body["isRecurring"] is True
        assert body["recurringFrequency"] == "monthly"

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.check_budget", return_value=None)
    @patch(f"{MOD}.publish_anomaly_alert")
    @patch(f"{MOD}.check_anomaly", return_value=(True, Decimal("5000"), "Anomaly detected"))
    @patch(f"{MOD}.put_item", return_value={"success": True})
    def test_anomaly_detected_returns_alert(self, mock_put, mock_anomaly, mock_pub, mock_budget, mock_ddb, mock_apigw, mock_track):
        event = _make_event({"amount": 500, "merchant": "Swiggy", "date": "2026-03-15"})
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert "anomalyAlert" in body

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.check_anomaly", return_value=(False, Decimal("0"), ""))
    @patch(f"{MOD}.put_item", return_value={"success": False, "error": "DDB error"})
    def test_ddb_failure_returns_500(self, mock_put, mock_anomaly, mock_ddb, mock_apigw, mock_track):
        event = _make_event({"amount": 100, "merchant": "Swiggy", "date": "2026-03-15"})
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 500

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.check_budget", return_value=None)
    @patch(f"{MOD}.check_anomaly", return_value=(False, Decimal("0"), ""))
    @patch(f"{MOD}.put_item", return_value={"success": True})
    def test_amount_paise_conversion(self, mock_put, mock_anomaly, mock_budget, mock_ddb, mock_apigw, mock_track):
        event = _make_event({"amount": 99.99, "merchant": "Test", "date": "2026-03-15"})
        resp = lambda_handler(event, None)
        body = json.loads(resp["body"])
        assert body["amountPaise"] == 9999
        assert body["amount"] == 99.99
