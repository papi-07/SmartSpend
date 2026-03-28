"""
Unit tests for SmartSpend get_expenses Lambda handler.
"""

import json
import base64
import sys
import os
import importlib.util
from unittest.mock import patch
from decimal import Decimal

_fn_dir = os.path.join(os.path.dirname(__file__), "..", "functions", "get_expenses")
sys.path.insert(0, _fn_dir)
_spec = importlib.util.spec_from_file_location("get_expenses_app", os.path.join(_fn_dir, "app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["get_expenses_app"] = _mod
_spec.loader.exec_module(_mod)

lambda_handler = _mod.lambda_handler
MOD = "get_expenses_app"


def _make_event(params=None, user_id="test-user-123", method="GET"):
    return {
        "httpMethod": method,
        "requestContext": {"authorizer": {"claims": {"sub": user_id}}},
        "queryStringParameters": params,
        "headers": {},
    }


def _mock_expense(expense_id="exp-1", amount_paise=25050, merchant="Swiggy",
                  category="Food", date="2026-03-15"):
    return {
        "userId": "test-user-123",
        "expenseId": expense_id,
        "amountPaise": amount_paise,
        "amount": amount_paise,
        "merchant": merchant,
        "category": category,
        "date": date,
        "notes": "",
        "tags": [],
        "source": "manual",
        "createdAt": "2026-03-15T10:00:00Z",
    }


class TestGetExpensesBasic:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items", return_value=[])
    def test_empty_results(self, mock_query, mock_ddb, mock_apigw, mock_track):
        resp = lambda_handler(_make_event(), None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["expenses"] == []
        assert body["count"] == 0
        assert body["totalCount"] == 0
        assert body["nextKey"] is None

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items")
    def test_returns_expenses_with_rupee_conversion(self, mock_query, mock_ddb, mock_apigw, mock_track):
        mock_query.return_value = [_mock_expense()]
        resp = lambda_handler(_make_event(), None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["count"] == 1
        assert body["expenses"][0]["amount"] == 250.50
        assert body["expenses"][0]["amountPaise"] == 25050
        assert "userId" not in body["expenses"][0]

    @patch(f"{MOD}.track_lambda_invocation")
    def test_options_preflight(self, mock_track):
        event = _make_event()
        event["httpMethod"] = "OPTIONS"
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200


class TestGetExpensesFiltering:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items")
    def test_date_range_uses_gsi(self, mock_query, mock_ddb, mock_apigw, mock_track):
        mock_query.return_value = [_mock_expense()]
        resp = lambda_handler(_make_event({"startDate": "2026-03-01", "endDate": "2026-03-31"}), None)
        assert resp["statusCode"] == 200
        call_kwargs = mock_query.call_args
        assert call_kwargs[1].get("index_name") == "date-index"

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items")
    def test_search_filter(self, mock_query, mock_ddb, mock_apigw, mock_track):
        mock_query.return_value = [
            _mock_expense("exp-1", merchant="Swiggy"),
            _mock_expense("exp-2", merchant="Amazon"),
        ]
        resp = lambda_handler(_make_event({"search": "swiggy"}), None)
        body = json.loads(resp["body"])
        assert body["count"] == 1
        assert body["expenses"][0]["merchant"] == "Swiggy"

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items")
    def test_search_empty_returns_all(self, mock_query, mock_ddb, mock_apigw, mock_track):
        mock_query.return_value = [_mock_expense(), _mock_expense("exp-2")]
        resp = lambda_handler(_make_event({"search": ""}), None)
        body = json.loads(resp["body"])
        assert body["count"] == 2


class TestGetExpensesPagination:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items")
    def test_pagination_with_limit(self, mock_query, mock_ddb, mock_apigw, mock_track):
        items = [_mock_expense(f"exp-{i}", date=f"2026-03-{15-i:02d}") for i in range(5)]
        mock_query.return_value = items
        resp = lambda_handler(_make_event({"limit": "2"}), None)
        body = json.loads(resp["body"])
        assert body["count"] == 2
        assert body["totalCount"] == 5
        assert body["nextKey"] is not None

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items")
    def test_pagination_next_page(self, mock_query, mock_ddb, mock_apigw, mock_track):
        items = [_mock_expense(f"exp-{i}") for i in range(5)]
        mock_query.return_value = items
        token = base64.b64encode(json.dumps({"expenseId": "exp-1", "date": "2026-03-15"}).encode()).decode()
        resp = lambda_handler(_make_event({"limit": "2", "lastKey": token}), None)
        body = json.loads(resp["body"])
        assert body["count"] == 2
        assert body["expenses"][0]["expenseId"] == "exp-2"

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_invalid_pagination_token(self, mock_apigw, mock_track):
        resp = lambda_handler(_make_event({"lastKey": "not-valid!!!"}), None)
        assert resp["statusCode"] == 400


class TestGetExpensesReceipts:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}._generate_presigned_url", return_value="https://s3.example.com/receipt.jpg")
    @patch(f"{MOD}.query_items")
    def test_generates_presigned_url(self, mock_query, mock_url, mock_ddb, mock_apigw, mock_track):
        exp = _mock_expense()
        exp["receiptKey"] = "receipts/test-user/receipt.jpg"
        mock_query.return_value = [exp]
        resp = lambda_handler(_make_event(), None)
        body = json.loads(resp["body"])
        assert body["expenses"][0]["receiptUrl"] == "https://s3.example.com/receipt.jpg"
