"""
SmartSpend — Get Dashboard Stats Lambda
=========================================
Returns aggregated spending statistics for a given month:
- Total spent and expense count
- Category breakdown (amount + count per category)
- Daily totals
- Top merchants
- Month-over-month comparison

Triggered by: GET /dashboard/stats via API Gateway (Cognito-authorized)

Query params:
  month — YYYY-MM format (defaults to current month)
"""

import os
import time
import logging
from datetime import datetime, timezone
from decimal import Decimal
from collections import defaultdict

from boto3.dynamodb.conditions import Key

from auth_utils import get_user_id
from response_utils import success, error, server_error, options_response
from db_utils import query_items
from resource_tracker import (
    track_lambda_invocation, track_dynamodb_operation, track_api_gateway_call,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

EXPENSES_TABLE = os.environ.get("EXPENSES_TABLE", "SmartSpend-Expenses")


def _get_month_range(year_month):
    """Get start and end dates for a YYYY-MM month string."""
    year, month = int(year_month[:4]), int(year_month[5:7])
    start_date = f"{year:04d}-{month:02d}-01"
    # End date: first day of next month
    if month == 12:
        end_date = f"{year + 1:04d}-01-01"
    else:
        end_date = f"{year:04d}-{month + 1:02d}-01"
    return start_date, end_date


def _get_prev_month(year_month):
    """Get the YYYY-MM string for the previous month."""
    year, month = int(year_month[:4]), int(year_month[5:7])
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def _aggregate_expenses(expenses):
    """Compute category breakdown, daily totals, and top merchants."""
    category_map = defaultdict(lambda: {"amount": Decimal("0"), "count": 0})
    daily_map = defaultdict(lambda: Decimal("0"))
    merchant_map = defaultdict(lambda: {"amount": Decimal("0"), "count": 0})

    total_paise = Decimal("0")

    for exp in expenses:
        amount = Decimal(str(exp.get("amountPaise") or exp.get("amount", 0)))
        cat = exp.get("category", "Other")
        date = exp.get("date", "")
        merchant = exp.get("merchant", "Unknown")

        total_paise += amount
        category_map[cat]["amount"] += amount
        category_map[cat]["count"] += 1
        daily_map[date] += amount
        merchant_map[merchant]["amount"] += amount
        merchant_map[merchant]["count"] += 1

    # Build category breakdown (sorted by amount descending)
    category_breakdown = sorted(
        [
            {"category": cat, "amount": float(d["amount"] / 100), "count": d["count"]}
            for cat, d in category_map.items()
        ],
        key=lambda x: x["amount"],
        reverse=True,
    )

    # Build daily totals (sorted by date ascending)
    daily_totals = sorted(
        [{"date": d, "amount": float(amt / 100)} for d, amt in daily_map.items()],
        key=lambda x: x["date"],
    )

    # Build top merchants (top 10 by amount)
    top_merchants = sorted(
        [
            {"merchant": m, "amount": float(d["amount"] / 100), "count": d["count"]}
            for m, d in merchant_map.items()
        ],
        key=lambda x: x["amount"],
        reverse=True,
    )[:10]

    return total_paise, category_breakdown, daily_totals, top_merchants


def lambda_handler(event, context):
    """Handle GET /dashboard/stats — return aggregated spending statistics."""
    start_time = time.time()

    try:
        if event.get("httpMethod") == "OPTIONS":
            return options_response()

        track_api_gateway_call("get_dashboard_stats")

        user_id = get_user_id(event)
        params = event.get("queryStringParameters") or {}

        # Default to current month
        month = params.get("month")
        if not month:
            month = datetime.now(timezone.utc).strftime("%Y-%m")

        # Validate format
        try:
            datetime.strptime(month + "-01", "%Y-%m-%d")
        except ValueError:
            return error("'month' must be in YYYY-MM format")

        # Query current month expenses
        start_date, end_date = _get_month_range(month)
        current_expenses = query_items(
            EXPENSES_TABLE,
            Key("userId").eq(user_id) & Key("date").between(start_date, end_date),
            index_name="date-index",
            scan_forward=True,
        )
        track_dynamodb_operation("get_dashboard_stats", "read", units=max(1, len(current_expenses) // 4))

        # Aggregate current month
        total_paise, category_breakdown, daily_totals, top_merchants = _aggregate_expenses(current_expenses)

        # Query previous month for comparison
        prev_month = _get_prev_month(month)
        prev_start, prev_end = _get_month_range(prev_month)
        prev_expenses = query_items(
            EXPENSES_TABLE,
            Key("userId").eq(user_id) & Key("date").between(prev_start, prev_end),
            index_name="date-index",
        )
        track_dynamodb_operation("get_dashboard_stats", "read", units=max(1, len(prev_expenses) // 4))

        prev_total_paise = sum(
            Decimal(str(e.get("amountPaise") or e.get("amount", 0))) for e in prev_expenses
        )

        # Calculate change percentage
        current_rupees = float(total_paise / 100)
        prev_rupees = float(prev_total_paise / 100)
        if prev_rupees > 0:
            change_percent = round(((current_rupees - prev_rupees) / prev_rupees) * 100, 1)
        else:
            change_percent = 0.0 if current_rupees == 0 else 100.0

        return success({
            "month": month,
            "totalSpent": current_rupees,
            "expenseCount": len(current_expenses),
            "categoryBreakdown": category_breakdown,
            "dailyTotals": daily_totals,
            "topMerchants": top_merchants,
            "comparisonWithLastMonth": {
                "currentMonth": current_rupees,
                "lastMonth": prev_rupees,
                "changePercent": change_percent,
            },
        })

    except Exception as e:
        logger.error("get_dashboard_stats failed: %s", str(e))
        return server_error("Internal error computing dashboard stats")
    finally:
        track_lambda_invocation("get_dashboard_stats", start_time)
