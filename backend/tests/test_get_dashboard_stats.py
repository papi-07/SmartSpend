"""
Unit tests for SmartSpend get_dashboard_stats Lambda handler.
"""

import json
import sys
import os
import importlib.util
from unittest.mock import patch
from decimal import Decimal

_fn_dir = os.path.join(os.path.dirname(__file__), "..", "functions", "get_dashboard_stats")
sys.path.insert(0, _fn_dir)
_spec = importlib.util.spec_from_file_location("dashboard_app", os.path.join(_fn_dir, "app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["dashboard_app"] = _mod
_spec.loader.exec_module(_mod)

lambda_handler = _mod.lambda_handler
_aggregate_expenses = _mod._aggregate_expenses
_get_month_range = _mod._get_month_range
_get_prev_month = _mod._get_prev_month
MOD = "dashboard_app"


def _make_event(params=None, user_id="test-user-123"):
    return {
        "httpMethod": "GET",
        "requestContext": {"authorizer": {"claims": {"sub": user_id}}},
        "queryStringParameters": params,
        "headers": {},
    }


def _mock_expense(expense_id, amount_paise, merchant, category, date):
    return {
        "userId": "test-user-123",
        "expenseId": expense_id,
        "amountPaise": amount_paise,
        "amount": amount_paise,
        "merchant": merchant,
        "category": category,
        "date": date,
    }


SAMPLE_EXPENSES = [
    _mock_expense("e1", 50000, "Swiggy", "Food", "2026-03-01"),
    _mock_expense("e2", 30000, "Zomato", "Food", "2026-03-05"),
    _mock_expense("e3", 100000, "Amazon", "Shopping", "2026-03-10"),
    _mock_expense("e4", 20000, "Uber", "Transport", "2026-03-10"),
    _mock_expense("e5", 15000, "Swiggy", "Food", "2026-03-15"),
]


class TestHelpers:
    def test_get_month_range(self):
        start, end = _get_month_range("2026-03")
        assert start == "2026-03-01"
        assert end == "2026-04-01"

    def test_get_month_range_december(self):
        start, end = _get_month_range("2026-12")
        assert start == "2026-12-01"
        assert end == "2027-01-01"

    def test_get_prev_month(self):
        assert _get_prev_month("2026-03") == "2026-02"

    def test_get_prev_month_january(self):
        assert _get_prev_month("2026-01") == "2025-12"


class TestAggregation:
    def test_aggregate_expenses(self):
        total, cats, daily, merchants = _aggregate_expenses(SAMPLE_EXPENSES)
        assert total == Decimal("215000")
        cat_names = [c["category"] for c in cats]
        assert "Food" in cat_names
        assert "Shopping" in cat_names
        assert "Transport" in cat_names
        food = next(c for c in cats if c["category"] == "Food")
        assert food["count"] == 3
        assert food["amount"] == 950.0
        assert cats[0]["category"] == "Shopping"

    def test_aggregate_empty(self):
        total, cats, daily, merchants = _aggregate_expenses([])
        assert total == Decimal("0")
        assert cats == []
        assert daily == []
        assert merchants == []

    def test_daily_totals_sorted(self):
        _, _, daily, _ = _aggregate_expenses(SAMPLE_EXPENSES)
        dates = [d["date"] for d in daily]
        assert dates == sorted(dates)

    def test_top_merchants(self):
        _, _, _, merchants = _aggregate_expenses(SAMPLE_EXPENSES)
        assert merchants[0]["merchant"] == "Amazon"
        swiggy = next(m for m in merchants if m["merchant"] == "Swiggy")
        assert swiggy["amount"] == 650.0
        assert swiggy["count"] == 2


class TestDashboardHandler:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items")
    def test_returns_full_stats(self, mock_query, mock_ddb, mock_apigw, mock_track):
        mock_query.side_effect = [SAMPLE_EXPENSES, []]
        resp = lambda_handler(_make_event({"month": "2026-03"}), None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["totalSpent"] == 2150.0
        assert body["expenseCount"] == 5
        assert len(body["categoryBreakdown"]) == 3
        assert len(body["dailyTotals"]) > 0
        assert len(body["topMerchants"]) > 0
        assert body["comparisonWithLastMonth"]["lastMonth"] == 0.0

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items")
    def test_month_comparison(self, mock_query, mock_ddb, mock_apigw, mock_track):
        prev_expenses = [_mock_expense("pe1", 100000, "Swiggy", "Food", "2026-02-15")]
        mock_query.side_effect = [SAMPLE_EXPENSES, prev_expenses]
        resp = lambda_handler(_make_event({"month": "2026-03"}), None)
        body = json.loads(resp["body"])
        comp = body["comparisonWithLastMonth"]
        assert comp["currentMonth"] == 2150.0
        assert comp["lastMonth"] == 1000.0
        assert comp["changePercent"] == 115.0

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items")
    def test_empty_month(self, mock_query, mock_ddb, mock_apigw, mock_track):
        mock_query.side_effect = [[], []]
        resp = lambda_handler(_make_event({"month": "2026-03"}), None)
        body = json.loads(resp["body"])
        assert body["totalSpent"] == 0.0
        assert body["expenseCount"] == 0

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_invalid_month_format(self, mock_apigw, mock_track):
        resp = lambda_handler(_make_event({"month": "March 2026"}), None)
        assert resp["statusCode"] == 400

    @patch(f"{MOD}.track_lambda_invocation")
    def test_options_preflight(self, mock_track):
        event = _make_event()
        event["httpMethod"] = "OPTIONS"
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200
