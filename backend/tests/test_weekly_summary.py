"""
Unit tests for SmartSpend weekly_summary Lambda handler.
Tests summary building, email formatting, and scheduled execution.
"""

import json
import sys
import os
import importlib.util
from unittest.mock import patch, MagicMock
from datetime import date

_fn_dir = os.path.join(os.path.dirname(__file__), "..", "functions", "weekly_summary")
sys.path.insert(0, _fn_dir)
_spec = importlib.util.spec_from_file_location("weekly_summary_app", os.path.join(_fn_dir, "app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["weekly_summary_app"] = _mod
_spec.loader.exec_module(_mod)

lambda_handler = _mod.lambda_handler
_get_week_range = _mod._get_week_range
_build_summary = _mod._build_summary
_format_email = _mod._format_email
MOD = "weekly_summary_app"


# ═══════════════════════════════════════════════════════════════════
# _get_week_range tests
# ═══════════════════════════════════════════════════════════════════

class TestGetWeekRange:
    def test_monday(self):
        start, end = _get_week_range(date(2026, 3, 23))  # Monday
        assert start == "2026-03-23"
        assert end == "2026-03-29"

    def test_sunday(self):
        start, end = _get_week_range(date(2026, 3, 29))  # Sunday
        assert start == "2026-03-23"
        assert end == "2026-03-29"

    def test_wednesday(self):
        start, end = _get_week_range(date(2026, 3, 25))  # Wednesday
        assert start == "2026-03-23"
        assert end == "2026-03-29"


# ═══════════════════════════════════════════════════════════════════
# _build_summary tests
# ═══════════════════════════════════════════════════════════════════

class TestBuildSummary:
    def test_empty_expenses(self):
        summary = _build_summary([])
        assert summary["totalSpent"] == 0
        assert summary["expenseCount"] == 0
        assert summary["categoryBreakdown"] == {}
        assert summary["topMerchants"] == []

    def test_single_expense(self):
        expenses = [
            {"amountPaise": 50000, "category": "Food", "merchant": "Swiggy", "date": "2026-03-25"},
        ]
        summary = _build_summary(expenses)
        assert summary["totalSpent"] == 50000
        assert summary["expenseCount"] == 1
        assert summary["categoryBreakdown"]["Food"] == 50000
        assert summary["topMerchants"][0] == ("Swiggy", 50000)

    def test_multiple_categories(self):
        expenses = [
            {"amountPaise": 50000, "category": "Food", "merchant": "Swiggy", "date": "2026-03-25"},
            {"amountPaise": 30000, "category": "Transport", "merchant": "Uber", "date": "2026-03-25"},
            {"amountPaise": 20000, "category": "Food", "merchant": "Zomato", "date": "2026-03-26"},
        ]
        summary = _build_summary(expenses)
        assert summary["totalSpent"] == 100000
        assert summary["expenseCount"] == 3
        assert summary["categoryBreakdown"]["Food"] == 70000
        assert summary["categoryBreakdown"]["Transport"] == 30000
        # Categories sorted by amount desc
        cats = list(summary["categoryBreakdown"].keys())
        assert cats[0] == "Food"

    def test_top_merchants_limited_to_5(self):
        expenses = [
            {"amountPaise": i * 1000, "category": "Food", "merchant": f"Merchant-{i}", "date": "2026-03-25"}
            for i in range(1, 8)
        ]
        summary = _build_summary(expenses)
        assert len(summary["topMerchants"]) == 5
        # Highest first
        assert summary["topMerchants"][0][0] == "Merchant-7"

    def test_daily_totals(self):
        expenses = [
            {"amountPaise": 30000, "category": "Food", "merchant": "A", "date": "2026-03-25"},
            {"amountPaise": 20000, "category": "Food", "merchant": "B", "date": "2026-03-25"},
            {"amountPaise": 10000, "category": "Food", "merchant": "C", "date": "2026-03-26"},
        ]
        summary = _build_summary(expenses)
        assert summary["dailyTotals"]["2026-03-25"] == 50000
        assert summary["dailyTotals"]["2026-03-26"] == 10000


# ═══════════════════════════════════════════════════════════════════
# _format_email tests
# ═══════════════════════════════════════════════════════════════════

class TestFormatEmail:
    def test_basic_email_format(self):
        this_week = {
            "totalSpent": 500000,
            "expenseCount": 5,
            "categoryBreakdown": {"Food": 300000, "Transport": 200000},
            "topMerchants": [("Swiggy", 200000), ("Uber", 200000)],
            "dailyTotals": {"2026-03-25": 300000, "2026-03-26": 200000},
        }
        last_week = {"totalSpent": 400000, "expenseCount": 4, "categoryBreakdown": {},
                     "topMerchants": [], "dailyTotals": {}}

        email = _format_email("user-1", this_week, last_week, "2026-03-23", "2026-03-29")

        assert "₹5,000.00" in email
        assert "WEEKLY OVERVIEW" in email
        assert "BY CATEGORY" in email
        assert "Food" in email
        assert "Transport" in email
        assert "Swiggy" in email
        assert "SmartSpend" in email

    def test_week_over_week_increase(self):
        this_week = {"totalSpent": 600000, "expenseCount": 5, "categoryBreakdown": {},
                     "topMerchants": [], "dailyTotals": {}}
        last_week = {"totalSpent": 400000, "expenseCount": 4, "categoryBreakdown": {},
                     "topMerchants": [], "dailyTotals": {}}

        email = _format_email("user-1", this_week, last_week, "2026-03-23", "2026-03-29")
        assert "▲" in email
        assert "more" in email

    def test_week_over_week_decrease(self):
        this_week = {"totalSpent": 300000, "expenseCount": 3, "categoryBreakdown": {},
                     "topMerchants": [], "dailyTotals": {}}
        last_week = {"totalSpent": 500000, "expenseCount": 5, "categoryBreakdown": {},
                     "topMerchants": [], "dailyTotals": {}}

        email = _format_email("user-1", this_week, last_week, "2026-03-23", "2026-03-29")
        assert "▼" in email
        assert "less" in email

    def test_no_last_week_data(self):
        this_week = {"totalSpent": 300000, "expenseCount": 3, "categoryBreakdown": {},
                     "topMerchants": [], "dailyTotals": {}}
        last_week = {"totalSpent": 0, "expenseCount": 0, "categoryBreakdown": {},
                     "topMerchants": [], "dailyTotals": {}}

        email = _format_email("user-1", this_week, last_week, "2026-03-23", "2026-03-29")
        assert "No data from last week" in email


# ═══════════════════════════════════════════════════════════════════
# Lambda handler tests
# ═══════════════════════════════════════════════════════════════════

class TestWeeklySummaryHandler:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.SNS_TOPIC_ARN", "")
    def test_no_sns_topic(self, mock_track):
        resp = lambda_handler({"source": "aws.events"}, None)
        assert resp["statusCode"] == 200
        assert "SNS not configured" in resp["body"]

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123:topic")
    @patch(f"{MOD}._get_active_users", return_value=[])
    def test_no_active_users(self, mock_users, mock_ddb, mock_track):
        resp = lambda_handler({"source": "aws.events"}, None)
        body = json.loads(resp["body"])
        assert "No users" in body["message"]

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.track_sns_publish")
    @patch(f"{MOD}.SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123:topic")
    @patch(f"{MOD}.boto3")
    @patch(f"{MOD}.query_by_partition", return_value=[])
    @patch(f"{MOD}._get_expenses_in_range")
    @patch(f"{MOD}._get_active_users")
    def test_sends_summary_for_active_user(self, mock_users, mock_expenses,
                                            mock_budgets, mock_boto,
                                            mock_sns_track, mock_ddb, mock_track):
        mock_users.return_value = [
            {"userId": "user-1", "email": "test@example.com", "name": "Test"},
        ]
        # This week has expenses, last week doesn't
        mock_expenses.side_effect = [
            [  # This week
                {"amountPaise": 50000, "category": "Food", "merchant": "Swiggy", "date": "2026-03-25"},
                {"amountPaise": 30000, "category": "Transport", "merchant": "Uber", "date": "2026-03-26"},
            ],
            [],  # Last week
        ]

        mock_sns = MagicMock()
        mock_boto.client.return_value = mock_sns

        resp = lambda_handler({"source": "aws.events"}, None)
        body = json.loads(resp["body"])

        assert body["summariesSent"] == 1
        mock_sns.publish.assert_called_once()
        call_kwargs = mock_sns.publish.call_args[1]
        assert "Weekly Summary" in call_kwargs["Subject"]
        assert "₹800.00" in call_kwargs["Message"]  # 50000 + 30000 = 80000 paise = ₹800

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123:topic")
    @patch(f"{MOD}.boto3")
    @patch(f"{MOD}.query_by_partition", return_value=[])
    @patch(f"{MOD}._get_expenses_in_range", return_value=[])
    @patch(f"{MOD}._get_active_users")
    def test_skips_user_with_no_expenses(self, mock_users, mock_expenses,
                                          mock_budgets, mock_boto,
                                          mock_ddb, mock_track):
        mock_users.return_value = [
            {"userId": "user-1", "email": "test@example.com", "name": "Test"},
        ]
        mock_sns = MagicMock()
        mock_boto.client.return_value = mock_sns

        resp = lambda_handler({"source": "aws.events"}, None)
        body = json.loads(resp["body"])

        assert body["summariesSent"] == 0
        mock_sns.publish.assert_not_called()
