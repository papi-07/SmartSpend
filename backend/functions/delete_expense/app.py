"""
SmartSpend — Delete Expense Lambda
====================================
Deletes an expense record. Validates ownership before deleting.
If expense has a receipt, also deletes it from S3.

Triggered by: DELETE /expenses/{expenseId} via API Gateway (Cognito-authorized)
"""

import os
import json
import time
import logging

import boto3

from auth_utils import get_user_id
from response_utils import success, error, not_found, server_error, options_response
from db_utils import get_item, delete_item
from resource_tracker import (
    track_lambda_invocation, track_dynamodb_operation,
    track_s3_operation, track_api_gateway_call,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

EXPENSES_TABLE = os.environ.get("EXPENSES_TABLE", "SmartSpend-Expenses")
RECEIPTS_BUCKET = os.environ.get("RECEIPTS_BUCKET", "")


def _delete_receipt(receipt_key):
    """Delete a receipt file from S3."""
    try:
        if not RECEIPTS_BUCKET or not receipt_key:
            return
        s3 = boto3.client("s3", region_name=os.environ.get("REGION", "us-east-1"))
        s3.delete_object(Bucket=RECEIPTS_BUCKET, Key=receipt_key)
        track_s3_operation("delete_expense", "delete")
        logger.info("Deleted receipt: s3://%s/%s", RECEIPTS_BUCKET, receipt_key)
    except Exception as e:
        logger.warning("Failed to delete receipt %s: %s", receipt_key, str(e))


def lambda_handler(event, context):
    """Handle DELETE /expenses/{expenseId} — delete an expense."""
    start_time = time.time()

    try:
        if event.get("httpMethod") == "OPTIONS":
            return options_response()

        track_api_gateway_call("delete_expense")

        user_id = get_user_id(event)

        # Get expenseId from path
        path_params = event.get("pathParameters") or {}
        expense_id = path_params.get("expenseId")
        if not expense_id:
            return error("expenseId is required in path")

        # Verify expense exists and belongs to this user
        existing = get_item(EXPENSES_TABLE, {"userId": user_id, "expenseId": expense_id})
        track_dynamodb_operation("delete_expense", "read", units=1)

        if not existing:
            return not_found("Expense not found or does not belong to you")

        # Delete receipt from S3 if present
        receipt_key = existing.get("receiptKey")
        if receipt_key:
            _delete_receipt(receipt_key)

        # Delete from DynamoDB
        result = delete_item(EXPENSES_TABLE, {"userId": user_id, "expenseId": expense_id})
        track_dynamodb_operation("delete_expense", "write", units=1)

        if not result.get("success"):
            return server_error("Failed to delete expense: " + result.get("error", "unknown"))

        return success({
            "message": "Expense deleted successfully",
            "expenseId": expense_id,
        })

    except Exception as e:
        logger.error("delete_expense failed: %s", str(e))
        return server_error("Internal error deleting expense")
    finally:
        track_lambda_invocation("delete_expense", start_time)
