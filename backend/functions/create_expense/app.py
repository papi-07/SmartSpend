"""
SmartSpend — Create Expense Lambda
===================================
Creates a new expense record in DynamoDB.
If category not provided, auto-categorizes via rule-based engine.
Runs anomaly detection via shared anomaly_utils module.
If anomaly detected, publishes alert to SNS.

Triggered by: POST /expenses via API Gateway (Cognito-authorized)
"""

import os
import json
import time
import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal

from auth_utils import get_user_id, get_user_email
from response_utils import error, created, server_error, options_response
from db_utils import put_item
from categorizer import categorize_expense
from anomaly_utils import check_anomaly, publish_anomaly_alert, check_budget
from resource_tracker import (
    track_lambda_invocation, track_dynamodb_operation, track_api_gateway_call,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

EXPENSES_TABLE = os.environ.get("EXPENSES_TABLE", "SmartSpend-Expenses")


def lambda_handler(event, context):
    """Handle POST /expenses — create a new expense."""
    start_time = time.time()

    try:
        # Handle CORS preflight
        if event.get("httpMethod") == "OPTIONS":
            return options_response()

        track_api_gateway_call("create_expense")

        user_id = get_user_id(event)
        user_email = get_user_email(event)

        # Parse request body
        try:
            body = json.loads(event.get("body") or "{}")
        except (json.JSONDecodeError, TypeError):
            return error("Invalid JSON in request body")

        # Validate required fields
        amount = body.get("amount")
        merchant = body.get("merchant")
        date = body.get("date")

        if amount is None:
            return error("'amount' is required")
        if not merchant:
            return error("'merchant' is required")
        if not date:
            return error("'date' is required (YYYY-MM-DD)")

        # Validate amount
        try:
            amount_float = float(amount)
            if amount_float <= 0:
                return error("'amount' must be positive")
        except (ValueError, TypeError):
            return error("'amount' must be a number")

        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return error("'date' must be in YYYY-MM-DD format")

        # Auto-categorize if not provided
        category = body.get("category")
        confidence = 0.0
        if not category:
            category, confidence = categorize_expense(merchant, body.get("notes", ""))

        # Generate expense ID and convert amount to paise
        expense_id = str(uuid.uuid4())
        amount_paise = int(round(amount_float * 100))
        now = datetime.now(timezone.utc).isoformat()

        # Build expense item — store amount in paise (integer)
        item = {
            "userId": user_id,
            "expenseId": expense_id,
            "amount": amount_paise,
            "amountPaise": amount_paise,
            "merchant": merchant.strip(),
            "category": category,
            "categoryConfidence": Decimal(str(round(confidence, 2))),
            "date": date,
            "notes": body.get("notes", ""),
            "tags": body.get("tags", []),
            "isRecurring": body.get("isRecurring", False),
            "recurringFrequency": body.get("recurringFrequency", ""),
            "source": "manual",
            "createdAt": now,
            "updatedAt": now,
        }

        # Save to DynamoDB
        result = put_item(EXPENSES_TABLE, item)
        if not result.get("success"):
            return server_error("Failed to save expense: " + result.get("error", "unknown"))
        track_dynamodb_operation("create_expense", "write", units=1)

        # Anomaly detection — uses shared anomaly_utils (single source of truth)
        is_anomaly, avg, anomaly_msg = check_anomaly(
            user_id, category, amount_paise, caller="create_expense"
        )

        anomaly_alert = None
        if is_anomaly:
            publish_anomaly_alert(
                user_id, user_email, anomaly_msg, caller="create_expense"
            )
            anomaly_alert = anomaly_msg

        # Budget check — alert only when threshold is crossed
        budget_alert = check_budget(
            user_id, user_email, category,
            caller="create_expense",
            current_amount_paise=amount_paise,
        )

        # Build response — convert paise back to rupees only here
        response_item = {
            "expenseId": expense_id,
            "amount": amount_float,
            "amountPaise": amount_paise,
            "merchant": item["merchant"],
            "category": category,
            "categoryConfidence": float(confidence),
            "date": date,
            "notes": item["notes"],
            "tags": item["tags"],
            "isRecurring": item["isRecurring"],
            "recurringFrequency": item["recurringFrequency"],
            "source": "manual",
            "createdAt": now,
            "updatedAt": now,
        }
        if anomaly_alert:
            response_item["anomalyAlert"] = anomaly_alert
        if budget_alert:
            response_item["budgetAlert"] = budget_alert

        return created(response_item)

    except Exception as e:
        logger.error("create_expense failed: %s", str(e))
        return server_error("Internal error creating expense")
    finally:
        track_lambda_invocation("create_expense", start_time)
