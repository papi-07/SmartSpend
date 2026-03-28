"""
SmartSpend — Resource Usage Tracking Utility (Module 9)
=======================================================
Logs AWS resource consumption to the SmartSpend-ResourceUsage DynamoDB table.
Every Lambda function calls the appropriate track_* function at the end of
each invocation to record what resources were consumed.

This data powers the Cloud Resource Usage & Cost Tracker dashboard — the
mandatory faculty requirement for demonstrating cloud billing awareness.

CRITICAL: All tracking functions are wrapped in try/except. Resource tracking
must NEVER crash or slow down the main Lambda function. It is best-effort.

AWS Pricing Constants (us-east-1, as of 2026):
  Lambda:     $0.20 per 1M requests + $0.0000166667 per GB-second
  S3:         $0.023/GB storage + $0.005/1K PUT + $0.0004/1K GET + $0.005/1K DELETE
  Textract:   $1.50 per 1000 pages (AnalyzeExpense)
  DynamoDB:   $0.00065/WCU + $0.00013/RCU (on-demand)
  SNS:        $2.00 per 100K email notifications
  API GW:     $3.50 per 1M API calls

Used by all Lambda functions via the shared CommonLayer.
"""

import os
import time
import logging
from datetime import datetime, timezone
from decimal import Decimal

import boto3

logger = logging.getLogger(__name__)

# Module-level DynamoDB resource — reused across warm invocations
_dynamodb = None
_table = None

# AWS pricing constants (us-east-1)
PRICING = {
    "lambda_per_request": Decimal("0.0000002"),          # $0.20 / 1M
    "lambda_per_gb_second": Decimal("0.0000166667"),
    "s3_per_gb_storage": Decimal("0.023"),
    "s3_per_1000_put": Decimal("0.005"),
    "s3_per_1000_get": Decimal("0.0004"),
    "s3_per_1000_delete": Decimal("0.005"),
    "textract_per_page": Decimal("0.0015"),              # $1.50 / 1000
    "dynamodb_per_wcu": Decimal("0.00065"),              # on-demand
    "dynamodb_per_rcu": Decimal("0.00013"),
    "sns_per_email": Decimal("0.00002"),                  # $2 / 100K
    "apigateway_per_call": Decimal("0.0000035"),          # $3.50 / 1M
}

# Free tier limits (monthly)
FREE_TIER = {
    "lambda_requests": 1_000_000,
    "lambda_gb_seconds": 400_000,
    "s3_storage_gb": 5,
    "s3_put_requests": 2_000,
    "s3_get_requests": 20_000,
    "textract_pages": 1_000,
    "dynamodb_wcu": 25,
    "dynamodb_rcu": 25,
    "sns_emails": 1_000,
    "apigateway_calls": 1_000_000,
}


def _get_table():
    """Get or create a cached DynamoDB Table reference for ResourceUsage."""
    global _dynamodb, _table
    try:
        if _table is None:
            _dynamodb = boto3.resource(
                "dynamodb",
                region_name=os.environ.get("REGION", "us-east-1"),
            )
            table_name = os.environ.get("RESOURCE_USAGE_TABLE", "SmartSpend-ResourceUsage")
            _table = _dynamodb.Table(table_name)
        return _table
    except Exception as e:
        logger.warning("ResourceTracker._get_table failed: %s", str(e))
        return None


def _log_usage(service, function_name, metric, value, estimated_cost):
    """
    Internal: write one usage record to the ResourceUsage DynamoDB table.

    Each record has a unique timestamp (ISO 8601 with microseconds) as the
    sort key, ensuring no collisions even under concurrent invocations.

    Never raises — all exceptions are caught and logged.
    """
    try:
        table = _get_table()
        if table is None:
            return

        now = datetime.now(timezone.utc)

        # Normalize value for DynamoDB (Decimal-safe)
        if isinstance(value, float):
            if value == int(value):
                value = int(value)
            else:
                value = round(value, 4)

        # Ensure estimated_cost is a string for DynamoDB Number precision
        if isinstance(estimated_cost, Decimal):
            cost_str = str(estimated_cost)
        else:
            cost_str = str(round(float(estimated_cost), 10))

        table.put_item(Item={
            "service": service,
            "timestamp": now.isoformat(),
            "functionName": function_name,
            "metric": metric,
            "value": value,
            "estimatedCostUsd": cost_str,
            "date": now.strftime("%Y-%m-%d"),
        })
    except Exception as e:
        # Best-effort — never crash the caller
        logger.warning("ResourceTracker._log_usage failed: %s", str(e))


def _validate_positive(value, name, default=0):
    """Validate that a numeric value is non-negative. Returns clamped value."""
    try:
        val = float(value)
        if val < 0:
            logger.warning("ResourceTracker: %s was negative (%s), clamping to %s", name, val, default)
            return default
        return val
    except (TypeError, ValueError):
        logger.warning("ResourceTracker: %s was invalid (%s), using default %s", name, value, default)
        return default


def track_lambda_invocation(function_name, start_time, memory_mb=128):
    """
    Track a Lambda invocation, duration, and GB-seconds consumed.
    Call at the END of every handler.

    Args:
        function_name: Name of the Lambda function (e.g., "create_expense").
        start_time: Value from time.time() captured at the start of the handler.
        memory_mb: Memory allocated to the Lambda (default 128 MB).
    """
    try:
        memory_mb = _validate_positive(memory_mb, "memory_mb", default=128)

        elapsed = time.time() - start_time
        duration_ms = max(0, elapsed * 1000)
        gb_seconds = Decimal(str(memory_mb / 1024)) * Decimal(str(duration_ms / 1000))

        request_cost = PRICING["lambda_per_request"]
        compute_cost = gb_seconds * PRICING["lambda_per_gb_second"]
        total_cost = request_cost + compute_cost

        _log_usage("lambda", function_name, "invocation", 1, total_cost)
        _log_usage("lambda", function_name, "duration_ms", round(duration_ms, 2), Decimal("0"))
        _log_usage("lambda", function_name, "gb_seconds", float(round(gb_seconds, 6)), compute_cost)
    except Exception as e:
        logger.warning("track_lambda_invocation failed: %s", str(e))


def track_s3_operation(function_name, operation, size_bytes=0):
    """
    Track an S3 PUT, GET, or DELETE operation.

    Args:
        function_name: Name of the calling Lambda function.
        operation: "put", "get", or "delete".
        size_bytes: Size of the object in bytes (for storage cost on PUT).
    """
    try:
        operation = str(operation).lower().strip()
        size_bytes = _validate_positive(size_bytes, "size_bytes", default=0)

        if operation == "put":
            cost = PRICING["s3_per_1000_put"] / 1000
            _log_usage("s3", function_name, "put_request", 1, cost)
            if size_bytes > 0:
                gb = Decimal(str(size_bytes)) / Decimal(str(1024 ** 3))
                storage_cost = gb * PRICING["s3_per_gb_storage"]
                _log_usage("s3", function_name, "storage_bytes", int(size_bytes), storage_cost)

        elif operation == "get":
            cost = PRICING["s3_per_1000_get"] / 1000
            _log_usage("s3", function_name, "get_request", 1, cost)

        elif operation == "delete":
            cost = PRICING["s3_per_1000_delete"] / 1000
            _log_usage("s3", function_name, "delete_request", 1, cost)

        else:
            logger.warning("track_s3_operation: unknown operation '%s'", operation)

    except Exception as e:
        logger.warning("track_s3_operation failed: %s", str(e))


def track_textract_call(function_name, pages=1):
    """
    Track an Amazon Textract AnalyzeExpense API call.

    Args:
        function_name: Name of the calling Lambda function.
        pages: Number of pages analyzed (default 1).
    """
    try:
        pages = int(_validate_positive(pages, "pages", default=1))
        if pages < 1:
            pages = 1

        cost = Decimal(str(pages)) * PRICING["textract_per_page"]
        _log_usage("textract", function_name, "analyze_expense_call", pages, cost)
    except Exception as e:
        logger.warning("track_textract_call failed: %s", str(e))


def track_dynamodb_operation(function_name, operation, units=1):
    """
    Track DynamoDB read or write capacity unit consumption.

    Args:
        function_name: Name of the calling Lambda function.
        operation: "read" or "write".
        units: Number of capacity units consumed (default 1).
    """
    try:
        operation = str(operation).lower().strip()
        units = int(_validate_positive(units, "units", default=1))
        if units < 1:
            units = 1

        if operation == "write":
            cost = Decimal(str(units)) * PRICING["dynamodb_per_wcu"]
            _log_usage("dynamodb", function_name, "wcu", units, cost)
        elif operation == "read":
            cost = Decimal(str(units)) * PRICING["dynamodb_per_rcu"]
            _log_usage("dynamodb", function_name, "rcu", units, cost)
        else:
            logger.warning("track_dynamodb_operation: unknown operation '%s'", operation)

    except Exception as e:
        logger.warning("track_dynamodb_operation failed: %s", str(e))


def track_sns_publish(function_name, count=1):
    """
    Track SNS email notification publish(es).

    Args:
        function_name: Name of the calling Lambda function.
        count: Number of emails published (default 1).
    """
    try:
        count = int(_validate_positive(count, "count", default=1))
        if count < 1:
            count = 1

        cost = Decimal(str(count)) * PRICING["sns_per_email"]
        _log_usage("sns", function_name, "email_sent", count, cost)
    except Exception as e:
        logger.warning("track_sns_publish failed: %s", str(e))


def track_api_gateway_call(function_name):
    """
    Track an API Gateway invocation.

    Args:
        function_name: Name of the calling Lambda function.
    """
    try:
        cost = PRICING["apigateway_per_call"]
        _log_usage("apigateway", function_name, "api_call", 1, cost)
    except Exception as e:
        logger.warning("track_api_gateway_call failed: %s", str(e))


def estimate_monthly_cost(service_usage):
    """
    Estimate monthly cost from a dict of service usage counts.

    Args:
        service_usage: Dict like {"lambda_requests": 5000, "s3_put_requests": 200, ...}

    Returns:
        dict: {"total_usd": float, "breakdown": {service: cost_usd}}
    """
    try:
        breakdown = {}
        mapping = {
            "lambda_requests": ("Lambda Requests", PRICING["lambda_per_request"]),
            "lambda_gb_seconds": ("Lambda Compute", PRICING["lambda_per_gb_second"]),
            "s3_put_requests": ("S3 PUT", PRICING["s3_per_1000_put"] / 1000),
            "s3_get_requests": ("S3 GET", PRICING["s3_per_1000_get"] / 1000),
            "s3_storage_gb": ("S3 Storage", PRICING["s3_per_gb_storage"]),
            "textract_pages": ("Textract", PRICING["textract_per_page"]),
            "dynamodb_wcu": ("DynamoDB Write", PRICING["dynamodb_per_wcu"]),
            "dynamodb_rcu": ("DynamoDB Read", PRICING["dynamodb_per_rcu"]),
            "sns_emails": ("SNS Email", PRICING["sns_per_email"]),
            "apigateway_calls": ("API Gateway", PRICING["apigateway_per_call"]),
        }

        total = Decimal("0")
        for key, (label, unit_cost) in mapping.items():
            usage = Decimal(str(service_usage.get(key, 0)))
            free = Decimal(str(FREE_TIER.get(key, 0)))
            billable = max(Decimal("0"), usage - free)
            cost = billable * unit_cost
            breakdown[label] = float(cost)
            total += cost

        return {"total_usd": float(total), "breakdown": breakdown}
    except Exception as e:
        logger.warning("estimate_monthly_cost failed: %s", str(e))
        return {"total_usd": 0.0, "breakdown": {}}
