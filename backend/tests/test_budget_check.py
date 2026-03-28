"""
Unit tests for SmartSpend budget_check Lambda handler.
Tests budget CRUD, status calculation, and alert triggering.
"""

import json
import sys
import os
import importlib.util
from decimal import Decimal
from unittest.mock import patch, MagicMock

_fn_dir = os.path.join(os.path.dirname(__file__), "..", "functions", "budget_check")
sys.path.insert(0, _fn_dir)
_spec = importlib.util.spec_from_file_location("budget_check_app", os.path.join(_fn_dir, "app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["budget_check_app"] = _mod
_spec.loader.exec_module(_mod)

lambda_handler = _mod.lambda_handler
_get_budget_status = _mod._get_budget_status
_get_month_spending = _mod._get_month_spending
MOD = "budget_check_app"


def _make_event(method="GET", body=None, path="/budgets", user_id="test-user-123"):
    return {
        "httpMethod": method,
        "path": path,
        "requestContext": {"authorizer": {"claims": {"sub": user_id, "email": "test@example.com"}}},
        "body": json.dumps(body) if body else None,
        "headers": {},
    }


# ═══════════════════════════════════════════════════════════════════
# Budget Status Calculation
# ═══════════════════════════════════════════════════════════════════

class TestBudgetStatusCalculation:
    def test_safe_status(self):
        budget = {"category": "Food", "monthlyLimitPaise": 500000, "alertThreshold": 80}
        status = _get_budget_status(budget, 200000)
        assert status["status"] == "safe"
        assert status["percentUsed"] == 40.0
        assert status["spent"] == 2000.0
        assert status["remaining"] == 3000.0

    def test_warning_status(self):
        budget = {"category": "Food", "monthlyLimitPaise": 500000, "alertThreshold": 80}
        status = _get_budget_status(budget, 350000)
        assert status["status"] == "warning"
        assert status["percentUsed"] == 70.0

    def test_exceeded_status(self):
        budget = {"category": "Food", "monthlyLimitPaise": 500000, "alertThreshold": 80}
        status = _get_budget_status(budget, 475000)
        assert status["status"] == "exceeded"
        assert status["percentUsed"] == 95.0

    def test_over_status(self):
        budget = {"category": "Food", "monthlyLimitPaise": 500000, "alertThreshold": 80}
        status = _get_budget_status(budget, 600000)
        assert status["status"] == "over"
        assert status["percentUsed"] == 120.0
        assert status["remaining"] == 0  # Can't be negative

    def test_zero_limit_returns_none(self):
        budget = {"category": "Food", "monthlyLimitPaise": 0}
        assert _get_budget_status(budget, 100) is None


# ═══════════════════════════════════════════════════════════════════
# POST /budgets — Set Budget
# ═══════════════════════════════════════════════════════════════════

class TestSetBudget:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.publish_budget_alert")
    @patch(f"{MOD}._get_month_spending", return_value={"Food": 200000})
    @patch(f"{MOD}.put_item", return_value={"success": True})
    def test_set_budget_success(self, mock_put, mock_spending, mock_pub,
                                 mock_ddb, mock_apigw, mock_track):
        event = _make_event("POST", body={
            "category": "Food",
            "monthlyLimit": 5000,
            "alertThreshold": 80,
        })
        resp = lambda_handler(event, None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 201
        assert body["category"] == "Food"
        assert body["monthlyLimit"] == 5000
        assert body["alertThreshold"] == 80
        assert body["currentSpent"] == 2000.0
        assert body["percentUsed"] == 40.0
        assert body["alertSent"] is False  # 40% < 80% threshold
        mock_put.assert_called_once()

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.publish_budget_alert")
    @patch(f"{MOD}._get_month_spending", return_value={"Food": 450000})
    @patch(f"{MOD}.put_item", return_value={"success": True})
    def test_set_budget_triggers_alert(self, mock_put, mock_spending, mock_pub,
                                        mock_ddb, mock_apigw, mock_track):
        """Setting budget where spending already exceeds threshold → sends alert."""
        event = _make_event("POST", body={
            "category": "Food",
            "monthlyLimit": 5000,
            "alertThreshold": 80,
        })
        resp = lambda_handler(event, None)
        body = json.loads(resp["body"])

        assert body["percentUsed"] == 90.0
        assert body["alertSent"] is True
        mock_pub.assert_called_once()

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_missing_category(self, mock_apigw, mock_track):
        event = _make_event("POST", body={"monthlyLimit": 5000})
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400
        assert "category" in json.loads(resp["body"])["error"].lower()

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_invalid_category(self, mock_apigw, mock_track):
        event = _make_event("POST", body={"category": "InvalidCat", "monthlyLimit": 5000})
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400
        assert "invalid category" in json.loads(resp["body"])["error"].lower()

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_missing_monthly_limit(self, mock_apigw, mock_track):
        event = _make_event("POST", body={"category": "Food"})
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400
        assert "monthlyLimit" in json.loads(resp["body"])["error"]

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_negative_limit(self, mock_apigw, mock_track):
        event = _make_event("POST", body={"category": "Food", "monthlyLimit": -100})
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_invalid_json_body(self, mock_apigw, mock_track):
        event = _make_event("POST")
        event["body"] = "not json{{"
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400

    @patch(f"{MOD}.track_lambda_invocation")
    def test_options_preflight(self, mock_track):
        event = _make_event("OPTIONS")
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200


# ═══════════════════════════════════════════════════════════════════
# GET /budgets
# ═══════════════════════════════════════════════════════════════════

class TestGetBudgets:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_by_partition")
    def test_get_budgets_returns_list(self, mock_query, mock_ddb, mock_apigw, mock_track):
        mock_query.return_value = [
            {
                "userId": "test-user-123", "category": "Food",
                "monthlyLimitPaise": 500000, "alertThreshold": Decimal("80"),
                "createdAt": "2026-03-01T00:00:00", "updatedAt": "2026-03-01T00:00:00",
            },
            {
                "userId": "test-user-123", "category": "Transport",
                "monthlyLimitPaise": 200000, "alertThreshold": Decimal("90"),
                "createdAt": "2026-03-01T00:00:00", "updatedAt": "2026-03-01T00:00:00",
            },
        ]
        resp = lambda_handler(_make_event("GET"), None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 200
        assert body["count"] == 2
        assert body["budgets"][0]["category"] == "Food"
        assert body["budgets"][0]["monthlyLimit"] == 5000.0
        assert body["budgets"][1]["category"] == "Transport"

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_by_partition", return_value=[])
    def test_get_budgets_empty(self, mock_query, mock_ddb, mock_apigw, mock_track):
        resp = lambda_handler(_make_event("GET"), None)
        body = json.loads(resp["body"])
        assert resp["statusCode"] == 200
        assert body["count"] == 0


# ═══════════════════════════════════════════════════════════════════
# GET /budgets/status
# ═══════════════════════════════════════════════════════════════════

class TestGetBudgetStatus:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}._get_month_spending", return_value={"Food": 350000, "Transport": 50000})
    @patch(f"{MOD}.query_by_partition")
    def test_get_status_with_budgets(self, mock_query, mock_spending,
                                      mock_ddb, mock_apigw, mock_track):
        mock_query.return_value = [
            {"userId": "test-user-123", "category": "Food",
             "monthlyLimitPaise": 500000, "alertThreshold": Decimal("80")},
            {"userId": "test-user-123", "category": "Transport",
             "monthlyLimitPaise": 200000, "alertThreshold": Decimal("80")},
        ]
        resp = lambda_handler(_make_event("GET", path="/budgets/status"), None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 200
        assert len(body["budgets"]) == 2

        # Should be sorted by percentUsed descending
        food = body["budgets"][0]
        assert food["category"] == "Food"
        assert food["percentUsed"] == 70.0
        assert food["status"] == "warning"

        transport = body["budgets"][1]
        assert transport["category"] == "Transport"
        assert transport["percentUsed"] == 25.0
        assert transport["status"] == "safe"

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_by_partition", return_value=[])
    def test_get_status_no_budgets(self, mock_query, mock_ddb, mock_apigw, mock_track):
        resp = lambda_handler(_make_event("GET", path="/budgets/status"), None)
        body = json.loads(resp["body"])
        assert resp["statusCode"] == 200
        assert body["budgets"] == []
        assert "No budgets" in body["message"]
