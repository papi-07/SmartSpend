"""
SmartSpend — Budget Check Lambda
=================================
POST /budgets       — Set/update monthly budget for a category
GET  /budgets       — Get all budgets for user
GET  /budgets/status — Get current month's spending vs budget for all categories

Triggered by: API Gateway (Cognito-authorized)
"""

import os
import json
import time
import logging
from datetime import datetime, timezone
from decimal import Decimal

from auth_utils import get_user_id, get_user_email
from response_utils import success, error, server_error, options_response
from db_utils import put_item, query_items, query_by_partition
from anomaly_utils import publish_budget_alert
from resource_tracker import (
    track_lambda_invocation, track_dynamodb_operation, track_api_gateway_call,
)
from boto3.dynamodb.conditions import Key, Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BUDGETS_TABLE = os.environ.get("BUDGETS_TABLE", "SmartSpend-Budgets")
EXPENSES_TABLE = os.environ.get("EXPENSES_TABLE", "SmartSpend-Expenses")

VALID_CATEGORIES = [
    "Food", "Transport", "Shopping", "Entertainment", "Bills",
    "Health", "Education", "Travel", "Groceries", "Fuel",
    "Subscriptions", "Rent", "Other",
]


def _get_budget_status(category_budget, spent_paise):
    """Calculate budget status from spent amount and limit."""
    limit_paise = int(category_budget.get("monthlyLimitPaise", 0))
    alert_threshold = float(category_budget.get("alertThreshold", 80))

    if limit_paise <= 0:
        return None

    spent = float(spent_paise)
    limit = float(limit_paise)
    percent_used = (spent / limit) * 100 if limit > 0 else 0
    remaining_paise = max(0, limit_paise - spent_paise)

    if percent_used > 100:
        status = "over"
    elif percent_used > 90:
        status = "exceeded"
    elif percent_used > 60:
        status = "warning"
    else:
        status = "safe"

    return {
        "category": category_budget["category"],
        "monthlyLimit": limit_paise / 100,
        "spent": spent_paise / 100,
        "remaining": remaining_paise / 100,
        "percentUsed": round(percent_used, 1),
        "status": status,
        "alertThreshold": alert_threshold,
    }


def _get_month_spending(user_id, year_month):
    """Query all expenses for a user in a given month and aggregate by category."""
    start_date = f"{year_month}-01"
    # Calculate end of month
    year, month = int(year_month[:4]), int(year_month[5:7])
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"

    expenses = query_items(
        EXPENSES_TABLE,
        Key("userId").eq(user_id) & Key("date").between(start_date, end_date),
        index_name="date-index",
    )
    track_dynamodb_operation("budget_check", "read", units=max(1, len(expenses) // 4))

    # Aggregate by category
    spending = {}
    for exp in expenses:
        cat = exp.get("category", "Other")
        amount = int(exp.get("amountPaise") or exp.get("amount", 0))
        spending[cat] = spending.get(cat, 0) + amount

    return spending


def lambda_handler(event, context):
    """Handle budget management API requests."""
    start_time = time.time()

    try:
        if event.get("httpMethod") == "OPTIONS":
            return options_response()

        track_api_gateway_call("budget_check")
        user_id = get_user_id(event)
        user_email = get_user_email(event)
        http_method = event.get("httpMethod", "GET")
        path = event.get("path", "")

        # ─── GET /budgets/status ──────────────────────────────
        if http_method == "GET" and path.endswith("/status"):
            return _handle_get_status(user_id)

        # ─── GET /budgets ─────────────────────────────────────
        if http_method == "GET":
            return _handle_get_budgets(user_id)

        # ─── POST /budgets ────────────────────────────────────
        if http_method == "POST":
            return _handle_set_budget(event, user_id, user_email)

        return error("Method not allowed", status_code=405)

    except Exception as e:
        logger.error("budget_check failed: %s", str(e))
        return server_error("Internal error processing budget request")
    finally:
        track_lambda_invocation("budget_check", start_time)


def _handle_get_budgets(user_id):
    """GET /budgets — return all budget limits for the user."""
    budgets = query_by_partition(BUDGETS_TABLE, "userId", user_id)
    track_dynamodb_operation("budget_check", "read", units=max(1, len(budgets) // 4))

    result = []
    for b in budgets:
        result.append({
            "category": b["category"],
            "monthlyLimit": int(b.get("monthlyLimitPaise", 0)) / 100,
            "alertThreshold": float(b.get("alertThreshold", 80)),
            "createdAt": b.get("createdAt", ""),
            "updatedAt": b.get("updatedAt", ""),
        })

    return success({"budgets": result, "count": len(result)})


def _handle_get_status(user_id):
    """GET /budgets/status — return spending vs budget for current month."""
    # Get all budgets for user
    budgets = query_by_partition(BUDGETS_TABLE, "userId", user_id)
    track_dynamodb_operation("budget_check", "read", units=max(1, len(budgets) // 4))

    if not budgets:
        return success({"budgets": [], "month": "", "message": "No budgets set"})

    # Get current month's spending
    now = datetime.now(timezone.utc)
    year_month = now.strftime("%Y-%m")
    spending = _get_month_spending(user_id, year_month)

    result = []
    for b in budgets:
        cat = b["category"]
        spent_paise = spending.get(cat, 0)
        status = _get_budget_status(b, spent_paise)
        if status:
            result.append(status)

    # Sort by percentUsed descending (most used first)
    result.sort(key=lambda x: x["percentUsed"], reverse=True)

    return success({
        "budgets": result,
        "month": year_month,
        "totalBudgeted": sum(b["monthlyLimit"] for b in result),
        "totalSpent": sum(b["spent"] for b in result),
    })


def _handle_set_budget(event, user_id, user_email):
    """POST /budgets — set or update a monthly budget for a category."""
    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return error("Invalid JSON body")

    category = body.get("category", "").strip()
    monthly_limit = body.get("monthlyLimit")
    alert_threshold = body.get("alertThreshold", 80)

    # Validate category
    if not category:
        return error("'category' is required")
    if category not in VALID_CATEGORIES:
        return error(f"Invalid category. Must be one of: {', '.join(VALID_CATEGORIES)}")

    # Validate monthly limit
    if monthly_limit is None:
        return error("'monthlyLimit' is required (amount in rupees)")
    try:
        monthly_limit = float(monthly_limit)
        if monthly_limit <= 0:
            return error("'monthlyLimit' must be positive")
        if monthly_limit > 1000000:
            return error("'monthlyLimit' cannot exceed ₹10,00,000")
    except (TypeError, ValueError):
        return error("'monthlyLimit' must be a valid number")

    # Validate alert threshold
    try:
        alert_threshold = float(alert_threshold)
        if not (0 < alert_threshold <= 100):
            alert_threshold = 80
    except (TypeError, ValueError):
        alert_threshold = 80

    limit_paise = int(round(monthly_limit * 100))
    now = datetime.now(timezone.utc).isoformat()

    item = {
        "userId": user_id,
        "category": category,
        "monthlyLimitPaise": limit_paise,
        "alertThreshold": Decimal(str(round(alert_threshold, 1))),
        "createdAt": now,
        "updatedAt": now,
    }

    result = put_item(BUDGETS_TABLE, item)
    if not result.get("success"):
        return server_error("Failed to save budget")
    track_dynamodb_operation("budget_check", "write", units=1)

    # Check if current spending already exceeds threshold
    year_month = datetime.now(timezone.utc).strftime("%Y-%m")
    spending = _get_month_spending(user_id, year_month)
    spent_paise = spending.get(category, 0)
    percent_used = (spent_paise / limit_paise) * 100 if limit_paise > 0 else 0

    budget_alert_sent = False
    if percent_used >= alert_threshold:
        publish_budget_alert(
            user_id, user_email, category,
            spent_paise, limit_paise, percent_used,
            caller="budget_check",
        )
        budget_alert_sent = True

    logger.info(
        "Budget set: userId=%s, category=%s, limit=₹%.2f, threshold=%.0f%%",
        user_id, category, monthly_limit, alert_threshold,
    )

    return success({
        "message": f"Budget for {category} set to ₹{monthly_limit:,.2f}/month",
        "category": category,
        "monthlyLimit": monthly_limit,
        "alertThreshold": alert_threshold,
        "currentSpent": spent_paise / 100,
        "percentUsed": round(percent_used, 1),
        "alertSent": budget_alert_sent,
    }, status_code=201)
