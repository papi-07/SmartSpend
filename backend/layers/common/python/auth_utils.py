"""
SmartSpend — Cognito Auth Utilities
====================================
Extracts the authenticated user's identity from API Gateway events.

When a Cognito Authorizer is attached to API Gateway, user claims are
injected into: event['requestContext']['authorizer']['claims']

For local testing without Cognito, falls back to X-User-Id header.

Used by all API-facing Lambda functions via the shared CommonLayer.
"""

import logging

logger = logging.getLogger(__name__)


def get_user_id(event):
    """
    Extract the authenticated user's ID (Cognito 'sub') from the API Gateway event.

    Priority:
    1. Cognito claims from API Gateway authorizer (production)
    2. X-User-Id header fallback (local testing / sam local invoke)

    Args:
        event: API Gateway Lambda proxy event dict.

    Returns:
        str: The user ID, or 'anonymous' if not found.
    """
    # 1. Try Cognito authorizer claims
    try:
        claims = event["requestContext"]["authorizer"]["claims"]
        user_id = claims.get("sub")
        if user_id:
            return user_id
    except (KeyError, TypeError):
        pass

    # 2. Fallback to X-User-Id header (local testing)
    try:
        headers = event.get("headers") or {}
        # API Gateway lowercases headers
        user_id = headers.get("X-User-Id") or headers.get("x-user-id")
        if user_id:
            logger.info("Using X-User-Id header fallback: %s", user_id)
            return user_id
    except (KeyError, TypeError):
        pass

    return "anonymous"


def get_user_email(event):
    """
    Extract the authenticated user's email from the API Gateway event claims.

    Args:
        event: API Gateway Lambda proxy event dict.

    Returns:
        str or None: The user's email, or None if not found.
    """
    try:
        claims = event["requestContext"]["authorizer"]["claims"]
        return claims.get("email")
    except (KeyError, TypeError):
        return None
