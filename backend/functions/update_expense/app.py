"""
SmartSpend — Update Expense Lambda
====================================
Updates an existing expense record. Validates ownership before modifying.
Uses DynamoDB UpdateExpression for partial updates.

Triggered by: PUT /expenses/{expenseId} via API Gateway (Cognito-authorized)
"""

import os
import json
import time
import logging
from datetime import datetime, timezone
from decimal import Decimal

from auth_utils import get_user_id
from response_utils import success, error, not_found, server_error, options_response
from db_utils import get_item, update_item
from categorizer import categorize_expense
from resource_tracker import (
    track_lambda_invocation, track_dynamodb_operation, track_api_gateway_call,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

EXPENSES_TABLE = os.environ.get("EXPENSES_TABLE", "SmartSpend-Expenses")

# Fields that can be updated
UPDATABLE_FIELDS = {
    "amount", "merchant", "category", "date", "notes",
    "tags", "isRecurring", "recurringFrequency",
}


def lambda_handler(event, context):
    """Handle PUT /expenses/{expenseId} — update an expense."""
    start_time = time.time()

    try:
        if event.get("httpMethod") == "OPTIONS":
            return options_response()

        track_api_gateway_call("update_expense")

        user_id = get_user_id(event)

        # Get expenseId from path
        path_params = event.get("pathParameters") or {}
        expense_id = path_params.get("expenseId")
        if not expense_id:
            return error("expenseId is required in path")

        # Parse body
        try:
            body = json.loads(event.get("body") or "{}")
        except (json.JSONDecodeError, TypeError):
            return error("Invalid JSON in request body")

        if not body:
            return error("Request body cannot be empty")

        # Verify expense exists and belongs to this user
        existing = get_item(EXPENSES_TABLE, {"userId": user_id, "expenseId": expense_id})
        track_dynamodb_operation("update_expense", "read", units=1)

        if not existing:
            return not_found("Expense not found or does not belong to you")

        # Build update expression
        update_parts = []
        expr_values = {}
        expr_names = {}

        for field in UPDATABLE_FIELDS:
            if field in body:
                value = body[field]

                # Special handling for amount → convert to paise
                if field == "amount":
                    try:
                        amount_float = float(value)
                        if amount_float <= 0:
                            return error("'amount' must be positive")
                        amount_paise = int(round(amount_float * 100))
                        update_parts.append("#amount = :amount")
                        expr_values[":amount"] = amount_paise
                        expr_names["#amount"] = "amount"

                        update_parts.append("amountPaise = :amountPaise")
                        expr_values[":amountPaise"] = amount_paise
                    except (ValueError, TypeError):
                        return error("'amount' must be a number")
                    continue

                # Special handling for date validation
                if field == "date":
                    try:
                        datetime.strptime(value, "%Y-%m-%d")
                    except ValueError:
                        return error("'date' must be in YYYY-MM-DD format")

                # Use expression attribute names for reserved words
                placeholder = f"#{field}"
                value_key = f":{field}"
                update_parts.append(f"{placeholder} = {value_key}")
                expr_names[placeholder] = field
                expr_values[value_key] = value

        # If merchant updated but category not provided, re-categorize
        if "merchant" in body and "category" not in body:
            cat, conf = categorize_expense(body["merchant"], body.get("notes", ""))
            update_parts.append("#category = :category")
            expr_names["#category"] = "category"
            expr_values[":category"] = cat

            update_parts.append("categoryConfidence = :categoryConfidence")
            expr_values[":categoryConfidence"] = Decimal(str(round(conf, 2)))

        if not update_parts:
            return error("No valid fields to update")

        # Always update timestamp
        update_parts.append("updatedAt = :updatedAt")
        expr_values[":updatedAt"] = datetime.now(timezone.utc).isoformat()

        update_expression = "SET " + ", ".join(update_parts)

        result = update_item(
            EXPENSES_TABLE,
            {"userId": user_id, "expenseId": expense_id},
            update_expression,
            expr_values,
            expr_names if expr_names else None,
        )
        track_dynamodb_operation("update_expense", "write", units=1)

        if result is None:
            return server_error("Failed to update expense")

        # Convert paise back to rupees for response
        response_item = dict(result)
        amount_paise = result.get("amountPaise") or result.get("amount", 0)
        response_item["amount"] = float(Decimal(str(amount_paise)) / Decimal("100"))
        response_item["amountPaise"] = int(amount_paise)
        response_item.pop("userId", None)

        return success(response_item)

    except Exception as e:
        logger.error("update_expense failed: %s", str(e))
        return server_error("Internal error updating expense")
    finally:
        track_lambda_invocation("update_expense", start_time)
