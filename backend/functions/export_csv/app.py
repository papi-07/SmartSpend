"""
SmartSpend — Export CSV Lambda
================================
Exports expenses as a CSV file for a given date range.
Returns base64-encoded CSV body with Content-Type: text/csv.

Triggered by: GET /expenses/export via API Gateway (Cognito-authorized)

Query params:
  startDate — start date (YYYY-MM-DD, defaults to 30 days ago)
  endDate   — end date (YYYY-MM-DD, defaults to today)
"""

import os
import csv
import io
import time
import base64
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from boto3.dynamodb.conditions import Key

from auth_utils import get_user_id
from response_utils import error, server_error, options_response, CORS_HEADERS
from db_utils import query_items
from resource_tracker import (
    track_lambda_invocation, track_dynamodb_operation, track_api_gateway_call,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

EXPENSES_TABLE = os.environ.get("EXPENSES_TABLE", "SmartSpend-Expenses")

CSV_COLUMNS = ["Date", "Merchant", "Category", "Amount (₹)", "Notes", "Tags", "Source"]


def lambda_handler(event, context):
    """Handle GET /expenses/export — export expenses as CSV."""
    start_time = time.time()

    try:
        if event.get("httpMethod") == "OPTIONS":
            return options_response()

        track_api_gateway_call("export_csv")

        user_id = get_user_id(event)
        params = event.get("queryStringParameters") or {}

        # Default date range: last 30 days
        today = datetime.now(timezone.utc)
        end_date = params.get("endDate", today.strftime("%Y-%m-%d"))
        start_date = params.get("startDate", (today - timedelta(days=30)).strftime("%Y-%m-%d"))

        # Validate dates
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            return error("Dates must be in YYYY-MM-DD format")

        if start_date > end_date:
            return error("startDate must be before endDate")

        # Query expenses
        expenses = query_items(
            EXPENSES_TABLE,
            Key("userId").eq(user_id) & Key("date").between(start_date, end_date),
            index_name="date-index",
            scan_forward=True,
        )
        track_dynamodb_operation("export_csv", "read", units=max(1, len(expenses) // 4))

        # Build CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(CSV_COLUMNS)

        for exp in expenses:
            amount_paise = exp.get("amountPaise") or exp.get("amount", 0)
            amount_rupees = float(Decimal(str(amount_paise)) / Decimal("100"))
            tags = exp.get("tags", [])
            tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags)

            writer.writerow([
                exp.get("date", ""),
                exp.get("merchant", ""),
                exp.get("category", "Other"),
                f"{amount_rupees:.2f}",
                exp.get("notes", ""),
                tags_str,
                exp.get("source", "manual"),
            ])

        csv_content = output.getvalue()
        csv_base64 = base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")

        # Return as base64-encoded binary response
        headers = dict(CORS_HEADERS)
        headers["Content-Type"] = "text/csv"
        headers["Content-Disposition"] = (
            f"attachment; filename=smartspend_expenses_{start_date}_to_{end_date}.csv"
        )

        return {
            "statusCode": 200,
            "headers": headers,
            "body": csv_base64,
            "isBase64Encoded": True,
        }

    except Exception as e:
        logger.error("export_csv failed: %s", str(e))
        return server_error("Internal error exporting CSV")
    finally:
        track_lambda_invocation("export_csv", start_time)
