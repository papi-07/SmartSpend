"""
Unit tests for SmartSpend export_csv Lambda handler.
"""

import json
import csv
import io
import base64
import sys
import os
import importlib.util
from unittest.mock import patch

_fn_dir = os.path.join(os.path.dirname(__file__), "..", "functions", "export_csv")
sys.path.insert(0, _fn_dir)
_spec = importlib.util.spec_from_file_location("export_csv_app", os.path.join(_fn_dir, "app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["export_csv_app"] = _mod
_spec.loader.exec_module(_mod)

lambda_handler = _mod.lambda_handler
MOD = "export_csv_app"


def _make_event(params=None, user_id="test-user-123"):
    return {
        "httpMethod": "GET",
        "requestContext": {"authorizer": {"claims": {"sub": user_id}}},
        "queryStringParameters": params,
        "headers": {},
    }


def _mock_expense(expense_id, amount_paise, merchant, category, date,
                  notes="", tags=None, source="manual"):
    return {
        "userId": "test-user-123",
        "expenseId": expense_id,
        "amountPaise": amount_paise,
        "amount": amount_paise,
        "merchant": merchant,
        "category": category,
        "date": date,
        "notes": notes,
        "tags": tags or [],
        "source": source,
    }


SAMPLE_EXPENSES = [
    _mock_expense("e1", 50000, "Swiggy", "Food", "2026-03-01", notes="Lunch"),
    _mock_expense("e2", 100000, "Amazon", "Shopping", "2026-03-05", tags=["online", "electronics"]),
    _mock_expense("e3", 20000, "Uber", "Transport", "2026-03-10"),
]


class TestExportCSVSuccess:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items", return_value=SAMPLE_EXPENSES)
    def test_exports_csv_correct_headers(self, mock_query, mock_ddb, mock_apigw, mock_track):
        resp = lambda_handler(_make_event({"startDate": "2026-03-01", "endDate": "2026-03-31"}), None)
        assert resp["statusCode"] == 200
        assert resp["headers"]["Content-Type"] == "text/csv"
        assert resp["isBase64Encoded"] is True
        assert "attachment" in resp["headers"]["Content-Disposition"]
        csv_content = base64.b64decode(resp["body"]).decode("utf-8")
        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)
        assert len(rows) == 4
        assert rows[0] == ["Date", "Merchant", "Category", "Amount (₹)", "Notes", "Tags", "Source"]

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items", return_value=SAMPLE_EXPENSES)
    def test_csv_data_values(self, mock_query, mock_ddb, mock_apigw, mock_track):
        resp = lambda_handler(_make_event({"startDate": "2026-03-01", "endDate": "2026-03-31"}), None)
        csv_content = base64.b64decode(resp["body"]).decode("utf-8")
        rows = list(csv.reader(io.StringIO(csv_content)))
        assert rows[1][0] == "2026-03-01"
        assert rows[1][1] == "Swiggy"
        assert rows[1][2] == "Food"
        assert rows[1][3] == "500.00"
        assert rows[1][4] == "Lunch"
        assert rows[2][5] == "online, electronics"

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items", return_value=[])
    def test_empty_export(self, mock_query, mock_ddb, mock_apigw, mock_track):
        resp = lambda_handler(_make_event({"startDate": "2026-03-01", "endDate": "2026-03-31"}), None)
        assert resp["statusCode"] == 200
        csv_content = base64.b64decode(resp["body"]).decode("utf-8")
        rows = list(csv.reader(io.StringIO(csv_content)))
        assert len(rows) == 1  # Header only


class TestExportCSVValidation:
    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_invalid_date_format(self, mock_apigw, mock_track):
        resp = lambda_handler(_make_event({"startDate": "01-03-2026", "endDate": "2026-03-31"}), None)
        assert resp["statusCode"] == 400

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    def test_start_after_end(self, mock_apigw, mock_track):
        resp = lambda_handler(_make_event({"startDate": "2026-04-01", "endDate": "2026-03-01"}), None)
        assert resp["statusCode"] == 400

    @patch(f"{MOD}.track_lambda_invocation")
    @patch(f"{MOD}.track_api_gateway_call")
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items", return_value=[])
    def test_defaults_to_last_30_days(self, mock_query, mock_ddb, mock_apigw, mock_track):
        resp = lambda_handler(_make_event(), None)
        assert resp["statusCode"] == 200

    @patch(f"{MOD}.track_lambda_invocation")
    def test_options_preflight(self, mock_track):
        event = _make_event()
        event["httpMethod"] = "OPTIONS"
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 200
