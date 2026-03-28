"""
SmartSpend — Get Resource Usage Lambda
=======================================
Returns aggregated AWS resource usage metrics and estimated costs from the
SmartSpend-ResourceUsage DynamoDB table. Powers the Resource Tracker dashboard
— the mandatory faculty module for BCSE408L Cloud Computing.

Triggered by: GET /resources/usage via API Gateway (Cognito-authorized)

Query params (optional):
  startDate — filter from this date (YYYY-MM-DD, default: 30 days ago)
  endDate   — filter to this date (YYYY-MM-DD, default: today)

Response shape matches what the frontend ResourceUsagePage expects:
  {
    services: {
      lambda:     { invocations, estimatedCost },
      dynamodb:   { readUnits, writeUnits, estimatedCost },
      s3:         { getRequests, putRequests, estimatedCost },
      textract:   { pagesProcessed, estimatedCost },
      sns:        { messagesPublished, estimatedCost },
      apiGateway: { requests, estimatedCost },
      cognito:    { monthlyActiveUsers, estimatedCost },
    },
    totalEstimatedCost: float,
    freeTierSavings: float,
  }
"""

import os
import time
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from collections import defaultdict

from boto3.dynamodb.conditions import Key

from auth_utils import get_user_id
from response_utils import success, error, server_error, options_response
from db_utils import query_items, scan_items
from resource_tracker import (
    track_lambda_invocation, track_dynamodb_operation, track_api_gateway_call,
    PRICING, FREE_TIER,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

RESOURCE_USAGE_TABLE = os.environ.get("RESOURCE_USAGE_TABLE", "SmartSpend-ResourceUsage")

# USD → INR approximate conversion rate
USD_TO_INR = Decimal("83.0")

# Estimated monthly cost if paying full price (no free tier)
# Used to calculate "free tier savings"
FULL_PRICE_ESTIMATES = {
    "lambda": {
        "requests": Decimal("1000000") * PRICING["lambda_per_request"],
        "compute": Decimal("400000") * PRICING["lambda_per_gb_second"],
    },
    "s3": {
        "storage": Decimal("5") * PRICING["s3_per_gb_storage"],
        "put": Decimal("2000") * PRICING["s3_per_1000_put"] / 1000,
        "get": Decimal("20000") * PRICING["s3_per_1000_get"] / 1000,
    },
    "dynamodb": {
        "read": Decimal("25") * PRICING["dynamodb_per_rcu"],
        "write": Decimal("25") * PRICING["dynamodb_per_wcu"],
    },
    "textract": {
        "pages": Decimal("1000") * PRICING["textract_per_page"],
    },
    "sns": {
        "emails": Decimal("1000") * PRICING["sns_per_email"],
    },
    "apigateway": {
        "calls": Decimal("1000000") * PRICING["apigateway_per_call"],
    },
}


def _get_date_range(params):
    """Parse startDate/endDate from query params, defaulting to last 30 days."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    thirty_ago = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")

    start_date = params.get("startDate", thirty_ago)
    end_date = params.get("endDate", today)

    # Validate
    try:
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return None, None

    return start_date, end_date


def _aggregate_usage(records):
    """
    Aggregate raw ResourceUsage DynamoDB records into the response shape
    expected by the frontend.

    Each record has: service, timestamp, functionName, metric, value, estimatedCostUsd, date
    """
    # Service-level accumulators
    lambda_invocations = 0
    lambda_cost = Decimal("0")

    dynamodb_rcu = 0
    dynamodb_wcu = 0
    dynamodb_cost = Decimal("0")

    s3_get = 0
    s3_put = 0
    s3_delete = 0
    s3_cost = Decimal("0")

    textract_pages = 0
    textract_cost = Decimal("0")

    sns_messages = 0
    sns_cost = Decimal("0")

    apigateway_requests = 0
    apigateway_cost = Decimal("0")

    # Daily usage accumulators
    daily = defaultdict(lambda: {
        "lambda": {"invocations": 0, "cost": Decimal("0")},
        "dynamodb": {"operations": 0, "cost": Decimal("0")},
        "s3": {"requests": 0, "cost": Decimal("0")},
        "textract": {"pages": 0, "cost": Decimal("0")},
        "sns": {"messages": 0, "cost": Decimal("0")},
        "apiGateway": {"requests": 0, "cost": Decimal("0")},
    })

    for record in records:
        service = record.get("service", "")
        metric = record.get("metric", "")
        value = int(float(record.get("value", 0)))
        cost_str = record.get("estimatedCostUsd", "0")
        cost = Decimal(str(cost_str)) if cost_str else Decimal("0")
        date = record.get("date", "")

        if service == "lambda":
            if metric == "invocation":
                lambda_invocations += value
                lambda_cost += cost
                if date:
                    daily[date]["lambda"]["invocations"] += value
                    daily[date]["lambda"]["cost"] += cost

        elif service == "dynamodb":
            if metric == "rcu":
                dynamodb_rcu += value
                dynamodb_cost += cost
                if date:
                    daily[date]["dynamodb"]["operations"] += value
                    daily[date]["dynamodb"]["cost"] += cost
            elif metric == "wcu":
                dynamodb_wcu += value
                dynamodb_cost += cost
                if date:
                    daily[date]["dynamodb"]["operations"] += value
                    daily[date]["dynamodb"]["cost"] += cost

        elif service == "s3":
            if metric == "get_request":
                s3_get += value
                s3_cost += cost
                if date:
                    daily[date]["s3"]["requests"] += value
                    daily[date]["s3"]["cost"] += cost
            elif metric == "put_request":
                s3_put += value
                s3_cost += cost
                if date:
                    daily[date]["s3"]["requests"] += value
                    daily[date]["s3"]["cost"] += cost
            elif metric == "delete_request":
                s3_delete += value
                s3_cost += cost
                if date:
                    daily[date]["s3"]["requests"] += value
                    daily[date]["s3"]["cost"] += cost
            elif metric == "storage_bytes":
                s3_cost += cost  # storage cost only

        elif service == "textract":
            if metric == "analyze_expense_call":
                textract_pages += value
                textract_cost += cost
                if date:
                    daily[date]["textract"]["pages"] += value
                    daily[date]["textract"]["cost"] += cost

        elif service == "sns":
            if metric == "email_sent":
                sns_messages += value
                sns_cost += cost
                if date:
                    daily[date]["sns"]["messages"] += value
                    daily[date]["sns"]["cost"] += cost

        elif service == "apigateway":
            if metric == "api_call":
                apigateway_requests += value
                apigateway_cost += cost
                if date:
                    daily[date]["apiGateway"]["requests"] += value
                    daily[date]["apiGateway"]["cost"] += cost

    # Build services response — matches frontend SERVICE_CONFIG keys exactly
    services = {
        "lambda": {
            "invocations": lambda_invocations,
            "estimatedCost": _to_float(lambda_cost),
        },
        "dynamodb": {
            "readUnits": dynamodb_rcu,
            "writeUnits": dynamodb_wcu,
            "estimatedCost": _to_float(dynamodb_cost),
        },
        "s3": {
            "getRequests": s3_get,
            "putRequests": s3_put,
            "deleteRequests": s3_delete,
            "estimatedCost": _to_float(s3_cost),
        },
        "textract": {
            "pagesProcessed": textract_pages,
            "estimatedCost": _to_float(textract_cost),
        },
        "sns": {
            "messagesPublished": sns_messages,
            "estimatedCost": _to_float(sns_cost),
        },
        "apiGateway": {
            "requests": apigateway_requests,
            "estimatedCost": _to_float(apigateway_cost),
        },
        "cognito": {
            "monthlyActiveUsers": 1,  # Static: Cognito doesn't log to ResourceUsage table
            "estimatedCost": 0.0,     # Free tier: 50K MAU
        },
    }

    total_cost = (
        lambda_cost + dynamodb_cost + s3_cost +
        textract_cost + sns_cost + apigateway_cost
    )

    # Calculate free tier savings: value of free tier limits we're benefiting from
    free_tier_value = sum(
        sum(v for v in svc.values())
        for svc in FULL_PRICE_ESTIMATES.values()
    )
    free_tier_savings_usd = max(Decimal("0"), free_tier_value - total_cost)

    # Build daily usage array (sorted by date)
    daily_usage = []
    for date_str in sorted(daily.keys()):
        day_data = daily[date_str]
        daily_usage.append({
            "date": date_str,
            "lambda": {
                "invocations": day_data["lambda"]["invocations"],
                "cost": _to_float(day_data["lambda"]["cost"]),
            },
            "s3": {
                "requests": day_data["s3"]["requests"],
                "cost": _to_float(day_data["s3"]["cost"]),
            },
            "dynamodb": {
                "operations": day_data["dynamodb"]["operations"],
                "cost": _to_float(day_data["dynamodb"]["cost"]),
            },
            "textract": {
                "pages": day_data["textract"]["pages"],
                "cost": _to_float(day_data["textract"]["cost"]),
            },
            "sns": {
                "messages": day_data["sns"]["messages"],
                "cost": _to_float(day_data["sns"]["cost"]),
            },
            "apiGateway": {
                "requests": day_data["apiGateway"]["requests"],
                "cost": _to_float(day_data["apiGateway"]["cost"]),
            },
        })

    # Build byService array (as specified in the phase 7 requirements)
    by_service = [
        {
            "service": "lambda",
            "totalInvocations": lambda_invocations,
            "totalDurationMs": 0,  # aggregated from duration_ms metric if needed
            "estimatedCostUsd": _to_float(lambda_cost),
            "freeTierLimit": "1,000,000 requests",
            "freeTierUsedPercent": round(
                (lambda_invocations / FREE_TIER["lambda_requests"]) * 100, 4
            ) if FREE_TIER["lambda_requests"] > 0 else 0,
        },
        {
            "service": "dynamodb",
            "totalReadUnits": dynamodb_rcu,
            "totalWriteUnits": dynamodb_wcu,
            "estimatedCostUsd": _to_float(dynamodb_cost),
            "freeTierLimit": "25 RCU / 25 WCU",
            "freeTierUsedPercent": round(
                max(
                    (dynamodb_rcu / FREE_TIER["dynamodb_rcu"]) * 100,
                    (dynamodb_wcu / FREE_TIER["dynamodb_wcu"]) * 100,
                ), 4
            ) if FREE_TIER["dynamodb_rcu"] > 0 else 0,
        },
        {
            "service": "s3",
            "totalGetRequests": s3_get,
            "totalPutRequests": s3_put,
            "estimatedCostUsd": _to_float(s3_cost),
            "freeTierLimit": "20,000 GET / 2,000 PUT",
            "freeTierUsedPercent": round(
                max(
                    (s3_get / FREE_TIER["s3_get_requests"]) * 100,
                    (s3_put / FREE_TIER["s3_put_requests"]) * 100,
                ), 4
            ) if FREE_TIER["s3_get_requests"] > 0 else 0,
        },
        {
            "service": "textract",
            "totalPagesProcessed": textract_pages,
            "estimatedCostUsd": _to_float(textract_cost),
            "freeTierLimit": "1,000 pages",
            "freeTierUsedPercent": round(
                (textract_pages / FREE_TIER["textract_pages"]) * 100, 4
            ) if FREE_TIER["textract_pages"] > 0 else 0,
        },
        {
            "service": "sns",
            "totalMessagesPublished": sns_messages,
            "estimatedCostUsd": _to_float(sns_cost),
            "freeTierLimit": "1,000 emails",
            "freeTierUsedPercent": round(
                (sns_messages / FREE_TIER["sns_emails"]) * 100, 4
            ) if FREE_TIER["sns_emails"] > 0 else 0,
        },
        {
            "service": "apigateway",
            "totalRequests": apigateway_requests,
            "estimatedCostUsd": _to_float(apigateway_cost),
            "freeTierLimit": "1,000,000 requests",
            "freeTierUsedPercent": round(
                (apigateway_requests / FREE_TIER["apigateway_calls"]) * 100, 4
            ) if FREE_TIER["apigateway_calls"] > 0 else 0,
        },
    ]

    return {
        "services": services,
        "totalEstimatedCost": _to_float(total_cost),
        "freeTierSavings": _to_float(free_tier_savings_usd),
        "summary": {
            "totalEstimatedCostUsd": _to_float(total_cost),
            "totalEstimatedCostInr": _to_float(total_cost * USD_TO_INR),
            "freeTierSavingsInr": _to_float(free_tier_savings_usd * USD_TO_INR),
        },
        "byService": by_service,
        "dailyUsage": daily_usage,
    }


def _to_float(d):
    """Safely convert Decimal to float for JSON serialization."""
    try:
        return round(float(d), 10)
    except (TypeError, ValueError):
        return 0.0


def _query_all_services(start_date, end_date):
    """
    Query the ResourceUsage table for all services within the date range.

    Uses the date-service-index GSI to efficiently scan by date.
    Queries each date in the range to gather all service data.
    """
    all_records = []

    # Use scan with filter — ResourceUsage table is small enough (within free tier)
    # and we need ALL services. The date-service-index GSI has date as HASH,
    # so we'd need to query each date individually. A filtered scan is simpler
    # and fine for the expected volume (<10K records/month).
    try:
        from boto3.dynamodb.conditions import Attr
        records = scan_items(
            RESOURCE_USAGE_TABLE,
            filter_expression=Attr("date").between(start_date, end_date),
        )
        track_dynamodb_operation("get_resource_usage", "read",
                                units=max(1, len(records) // 4))
        all_records = records
    except Exception as e:
        logger.warning("Scan failed, trying per-service query: %s", str(e))
        # Fallback: query each service partition directly
        services = ["lambda", "dynamodb", "s3", "textract", "sns", "apigateway"]
        for svc in services:
            try:
                # Use primary key: service (HASH), timestamp (RANGE)
                # Filter by date attribute
                from boto3.dynamodb.conditions import Attr as A
                records = query_items(
                    RESOURCE_USAGE_TABLE,
                    Key("service").eq(svc),
                    filter_expression=A("date").between(start_date, end_date),
                )
                track_dynamodb_operation("get_resource_usage", "read",
                                        units=max(1, len(records) // 4))
                all_records.extend(records)
            except Exception as svc_err:
                logger.warning("Query for service %s failed: %s", svc, str(svc_err))

    return all_records


def lambda_handler(event, context):
    """Handle GET /resources/usage — return aggregated resource usage metrics."""
    start_time = time.time()

    try:
        if event.get("httpMethod") == "OPTIONS":
            return options_response()

        track_api_gateway_call("get_resource_usage")

        # Auth — get user ID (validates the Cognito token)
        user_id = get_user_id(event)

        params = event.get("queryStringParameters") or {}
        start_date, end_date = _get_date_range(params)

        if start_date is None:
            return error("Dates must be in YYYY-MM-DD format")

        logger.info(
            "GetResourceUsage: user=%s, range=%s to %s",
            user_id, start_date, end_date,
        )

        # Query all resource usage records in the date range
        records = _query_all_services(start_date, end_date)

        logger.info("GetResourceUsage: found %d records", len(records))

        # Aggregate into the response shape the frontend expects
        result = _aggregate_usage(records)

        return success(result)

    except Exception as e:
        logger.error("get_resource_usage failed: %s", str(e))
        return server_error("Internal error retrieving resource usage")
    finally:
        track_lambda_invocation("get_resource_usage", start_time)
