"""
SmartSpend — Get Expenses Lambda
=================================
Retrieves expenses with filtering, search, and pagination.
Generates pre-signed S3 URLs for expenses with receipts.

Triggered by: GET /expenses via API Gateway (Cognito-authorized)

Query params:
  startDate, endDate  — date range filter (YYYY-MM-DD)
  category            — filter by category
  search              — search merchant/notes
  tags                — filter by tag
  limit               — max results (default 50, max 100)
  lastKey             — pagination token (base64-encoded JSON)
"""

import os
import json
import time
import base64
import logging
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key, Attr

from auth_utils import get_user_id
from response_utils import success, error, server_error, options_response
from db_utils import query_items
from resource_tracker import (
    track_lambda_invocation, track_dynamodb_operation,
    track_s3_operation, track_api_gateway_call,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

EXPENSES_TABLE = os.environ.get("EXPENSES_TABLE", "SmartSpend-Expenses")
RECEIPTS_BUCKET = os.environ.get("RECEIPTS_BUCKET", "")
PRESIGNED_URL_EXPIRY = 3600  # 1 hour


def _generate_presigned_url(receipt_key):
    """Generate a pre-signed S3 GET URL for a receipt."""
    try:
        if not RECEIPTS_BUCKET or not receipt_key:
            return None
        s3 = boto3.client("s3", region_name=os.environ.get("REGION", "us-east-1"))
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": RECEIPTS_BUCKET, "Key": receipt_key},
            ExpiresIn=PRESIGNED_URL_EXPIRY,
        )
        track_s3_operation("get_expenses", "get")
        return url
    except Exception as e:
        logger.warning("Failed to generate presigned URL for %s: %s", receipt_key, str(e))
        return None


def _paise_to_rupees(item):
    """Convert amountPaise to amount (rupees) for response."""
    result = dict(item)
    amount_paise = item.get("amountPaise") or item.get("amount", 0)
    result["amount"] = float(Decimal(str(amount_paise)) / Decimal("100"))
    result["amountPaise"] = int(amount_paise)
    return result


def lambda_handler(event, context):
    """Handle GET /expenses — list expenses with filters and pagination."""
    start_time = time.time()

    try:
        if event.get("httpMethod") == "OPTIONS":
            return options_response()

        track_api_gateway_call("get_expenses")

        user_id = get_user_id(event)
        params = event.get("queryStringParameters") or {}

        start_date = params.get("startDate")
        end_date = params.get("endDate")
        category_filter = params.get("category")
        search_term = params.get("search", "").lower()
        tag_filter = params.get("tags")

        limit = min(int(params.get("limit", 50)), 100)

        # Decode pagination token
        last_key = None
        last_key_param = params.get("lastKey")
        if last_key_param:
            try:
                last_key = json.loads(base64.b64decode(last_key_param))
            except Exception:
                return error("Invalid pagination token")

        # Build query — use date-index GSI if date range provided
        if start_date and end_date:
            key_condition = Key("userId").eq(user_id) & Key("date").between(start_date, end_date)
            index_name = "date-index"
        elif start_date:
            key_condition = Key("userId").eq(user_id) & Key("date").gte(start_date)
            index_name = "date-index"
        elif end_date:
            key_condition = Key("userId").eq(user_id) & Key("date").lte(end_date)
            index_name = "date-index"
        else:
            key_condition = Key("userId").eq(user_id)
            index_name = None

        # Build filter expression
        filter_expr = None
        if category_filter:
            filter_expr = Attr("category").eq(category_filter)
        if tag_filter:
            tag_expr = Attr("tags").contains(tag_filter)
            filter_expr = filter_expr & tag_expr if filter_expr else tag_expr

        # Query DynamoDB
        raw_items = query_items(
            EXPENSES_TABLE,
            key_condition,
            index_name=index_name,
            filter_expression=filter_expr,
            scan_forward=False,
        )
        track_dynamodb_operation("get_expenses", "read", units=max(1, len(raw_items) // 4))

        # Apply search filter (DynamoDB can't do contains on multiple fields efficiently)
        if search_term:
            raw_items = [
                item for item in raw_items
                if search_term in item.get("merchant", "").lower()
                or search_term in item.get("notes", "").lower()
            ]

        # Manual pagination
        total_count = len(raw_items)

        # Find start position if lastKey provided
        start_idx = 0
        if last_key:
            last_expense_id = last_key.get("expenseId")
            for i, item in enumerate(raw_items):
                if item.get("expenseId") == last_expense_id:
                    start_idx = i + 1
                    break

        paginated_items = raw_items[start_idx:start_idx + limit]

        # Build response items
        expenses = []
        for item in paginated_items:
            expense = _paise_to_rupees(item)

            # Generate presigned URL for receipts
            receipt_key = item.get("receiptKey")
            if receipt_key:
                expense["receiptUrl"] = _generate_presigned_url(receipt_key)

            expense.pop("userId", None)
            expenses.append(expense)

        # Build next page token
        next_key = None
        if start_idx + limit < total_count:
            last_item = paginated_items[-1]
            token_data = {
                "expenseId": last_item["expenseId"],
                "date": last_item.get("date", ""),
            }
            next_key = base64.b64encode(json.dumps(token_data).encode()).decode()

        return success({
            "expenses": expenses,
            "count": len(expenses),
            "totalCount": total_count,
            "nextKey": next_key,
        })

    except Exception as e:
        logger.error("get_expenses failed: %s", str(e))
        return server_error("Internal error retrieving expenses")
    finally:
        track_lambda_invocation("get_expenses", start_time)
