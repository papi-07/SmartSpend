"""
Unit tests for SmartSpend delete_expense Lambda handler.
"""

import json
import sys
import os
import importlib.util
from unittest.mock import patch

_fn_dir = os.path.join(os.path.dirname(__file__), "..", "functions", "delete_expense")
sys.path.insert(0, _fn_dir)
_spec = importlib.util.spec_from_file_location("delete_expense_app", os.path.join(_fn_dir, "app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["delete_expense_app"] = _mod
_spec.loader.exec_module(_mod)

lambda_handler = _mod.lambda_handler
MOD = "delete_expense_app"


def _make_event(expense_id="exp-123", user_id="test-user-123"):
    return {
        "httpMethod": "DELETE",
        "requestContext": {"authorizer": {"claims": {"sub": user_id}}},
        "pathParameters": {"expenseId": expense_id} if expense_id else None,
        "headers": {},
    }


EXISTING_EXPENSE = {
    "userId": "test-user-123",
    "expenseId": "exp-123",
    "amountPaise": 25050,
    "merchant": "Swiggy",
    "category": "Food",
    "date": "2026-03-15",
}

EXPENSE_WITH_RECEIPT = {
    **EXISTING_EXPENSE,
    "receiptKey": "receipts/test-user-123/receipt-abc.jpg",
}


class TestDeleteExpenseValidation:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_missing_expense_id(self, mock_apigw, mock_track):
        event = _make_event(expense_id=None)
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.get_item", return_value=None)
    def test_expense_not_found(self, mock_get, mock_ddb, mock_apigw, mock_track):
        resp = lambda_handler(_make_event(), None)
        assert resp["statusCode"] == 404

    @patch(f"{MOD}.track_lambda_invocation")
    def test_options_preflight(self, mock_track):
        event = _make_event()
        event["httpMethod"] = "OPTIONS"
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200


class TestDeleteExpenseSuccess:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.delete_item", return_value={"success": True})
    @patch(f"{MOD}.get_item", return_value=EXISTING_EXPENSE)
    def test_delete_no_receipt(self, mock_get, mock_delete, mock_ddb, mock_apigw, mock_track):
        resp = lambda_handler(_make_event(), None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["message"] == "Expense deleted successfully"
        assert body["expenseId"] == "exp-123"

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.delete_item", return_value={"success": True})
    @patch(f"{MOD}._delete_receipt")
    @patch(f"{MOD}.get_item", return_value=EXPENSE_WITH_RECEIPT)
    def test_delete_with_receipt(self, mock_get, mock_del_receipt, mock_delete, mock_ddb, mock_apigw, mock_track):
        resp = lambda_handler(_make_event(), None)
        assert resp["statusCode"] == 200
        mock_del_receipt.assert_called_once_with("receipts/test-user-123/receipt-abc.jpg")

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.delete_item", return_value={"success": False, "error": "DDB error"})
    @patch(f"{MOD}.get_item", return_value=EXISTING_EXPENSE)
    def test_ddb_failure(self, mock_get, mock_delete, mock_ddb, mock_apigw, mock_track):
        resp = lambda_handler(_make_event(), None)
        assert resp["statusCode"] == 500
