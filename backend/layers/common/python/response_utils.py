"""
SmartSpend — Standardized API Response Builder
===============================================
Ensures every Lambda returns consistent JSON responses with CORS headers.
All API-facing Lambda functions must use these helpers to return responses.

Used by all Lambda functions via the shared CommonLayer.
"""

import json
from decimal import Decimal


class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder that converts Decimal types (from DynamoDB) to float/int."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super().default(obj)


CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token,X-User-Id",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
}


def success(body, status_code=200):
    """
    Return a successful API Gateway response.

    Args:
        body: Dict or list to serialize as JSON in the response body.
        status_code: HTTP status code (default 200).

    Returns:
        API Gateway response dict with CORS headers.
    """
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(body, cls=DecimalEncoder),
    }


def error(message, status_code=400):
    """
    Return an error API Gateway response.

    Args:
        message: Error message string.
        status_code: HTTP status code (default 400).

    Returns:
        API Gateway response dict with CORS headers and error body.
    """
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": message}, cls=DecimalEncoder),
    }


def created(body):
    """Return a 201 Created response."""
    return success(body, status_code=201)


def not_found(message="Resource not found"):
    """Return a 404 Not Found response."""
    return error(message, status_code=404)


def server_error(message="Internal server error"):
    """Return a 500 Internal Server Error response."""
    return error(message, status_code=500)


def options_response():
    """Return a 200 response for CORS preflight OPTIONS requests."""
    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": "",
    }
