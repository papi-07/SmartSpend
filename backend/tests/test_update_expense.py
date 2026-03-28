"""
Unit tests for SmartSpend update_expense Lambda handler.
"""

import json
import sys
import os
import importlib.util
from unittest.mock import patch
from decimal import Decimal

_fn_dir = os.path.join(os.path.dirname(__file__), "..", "functions", "update_expense")
sys.path.insert(0, _fn_dir)
_spec = importlib.util.spec_from_file_location("update_expense_app", os.path.join(_fn_dir, "app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["update_expense_app"] = _mod
_spec.loader.exec_module(_mod)

lambda_handler = _mod.lambda_handler
MOD = "update_expense_app"


def _make_event(body=None, expense_id="exp-123", user_id="test-user-123"):
    return {
        "httpMethod": "PUT",
        "requestContext": {"authorizer": {"claims": {"sub": user_id}}},
        "pathParameters": {"expenseId": expense_id} if expense_id else None,
        "body": json.dumps(body) if body else None,
        "headers": {},
    }


EXISTING_EXPENSE = {
    "userId": "test-user-123",
    "expenseId": "exp-123",
    "amountPaise": 25050,
    "amount": 25050,
    "merchant": "Swiggy",
    "category": "Food",
    "date": "2026-03-15",
    "notes": "",
    "tags": [],
    "createdAt": "2026-03-15T10:00:00Z",
    "updatedAt": "2026-03-15T10:00:00Z",
}


class TestUpdateExpenseValidation:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_missing_expense_id(self, mock_apigw, mock_track):
        event = _make_event({"amount": 100}, expense_id=None)
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_empty_body(self, mock_apigw, mock_track):
        resp = lambda_handler(_make_event({}), None)
        assert resp["statusCode"] == 400

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_invalid_json(self, mock_apigw, mock_track):
        event = _make_event()
        event["body"] = "not json"
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.get_item", return_value=None)
    def test_expense_not_found(self, mock_get, mock_ddb, mock_apigw, mock_track):
        resp = lambda_handler(_make_event({"amount": 100}), None)
        assert resp["statusCode"] == 404

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.get_item", return_value=EXISTING_EXPENSE)
    def test_negative_amount(self, mock_get, mock_ddb, mock_apigw, mock_track):
        resp = lambda_handler(_make_event({"amount": -50}), None)
        assert resp["statusCode"] == 400

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.get_item", return_value=EXISTING_EXPENSE)
    def test_invalid_date(self, mock_get, mock_ddb, mock_apigw, mock_track):
        resp = lambda_handler(_make_event({"date": "03-15-2026"}), None)
        assert resp["statusCode"] == 400


class TestUpdateExpenseSuccess:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.update_item")
    @patch(f"{MOD}.get_item", return_value=EXISTING_EXPENSE)
    def test_update_amount(self, mock_get, mock_update, mock_ddb, mock_apigw, mock_track):
        updated = dict(EXISTING_EXPENSE)
        updated["amountPaise"] = 30000
        updated["amount"] = 30000
        mock_update.return_value = updated
        resp = lambda_handler(_make_event({"amount": 300}), None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["amount"] == 300.0
        assert body["amountPaise"] == 30000

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.update_item")
    @patch(f"{MOD}.get_item", return_value=EXISTING_EXPENSE)
    def test_update_merchant_recategorizes(self, mock_get, mock_update, mock_ddb, mock_apigw, mock_track):
        updated = dict(EXISTING_EXPENSE)
        updated["merchant"] = "Uber"
        updated["category"] = "Transport"
        mock_update.return_value = updated
        resp = lambda_handler(_make_event({"merchant": "Uber"}), None)
        assert resp["statusCode"] == 200
        call_args = mock_update.call_args
        update_expr = call_args[0][2]
        assert "category" in update_expr.lower() or "#category" in update_expr

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.update_item")
    @patch(f"{MOD}.get_item", return_value=EXISTING_EXPENSE)
    def test_update_notes_and_tags(self, mock_get, mock_update, mock_ddb, mock_apigw, mock_track):
        updated = dict(EXISTING_EXPENSE)
        updated["notes"] = "lunch"
        updated["tags"] = ["work"]
        mock_update.return_value = updated
        resp = lambda_handler(_make_event({"notes": "lunch", "tags": ["work"]}), None)
        assert resp["statusCode"] == 200

    @patch(f"{MOD}.track_lambda_invocation")
    def test_options_preflight(self, mock_track):
        event = _make_event()
        event["httpMethod"] = "OPTIONS"
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200
