"""
SmartSpend — Anomaly Detector Lambda
======================================
Internal-only function (no API Gateway route).
Uses the shared anomaly_utils module (single source of truth).

Can be invoked directly by other Lambda functions via boto3 invoke
for batch re-analysis of expenses.

Expects event payload:
  { "userId", "category", "amountPaise", "merchant", "expenseId", "userEmail" }
"""

import time
import logging
from decimal import Decimal

from response_utils import success, error, server_error
from anomaly_utils import check_anomaly, publish_anomaly_alert, ANOMALY_THRESHOLD
from resource_tracker import track_lambda_invocation

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Check if an expense is anomalous and publish an SNS alert if so.
    This is an internal function — not exposed via API Gateway.
    Delegates to shared anomaly_utils for the actual logic.
    """
    start_time = time.time()

    try:
        user_id = event.get("userId")
        category = event.get("category")
        amount_paise = event.get("amountPaise", 0)
        merchant = event.get("merchant", "Unknown")
        user_email = event.get("userEmail", "")

        if not user_id or not category:
            return error("userId and category are required")

        # Use shared anomaly detection — single source of truth
        is_anomaly, avg, message = check_anomaly(
            user_id, category, amount_paise, caller="anomaly_detector"
        )

        result = {
            "isAnomaly": is_anomaly,
            "amount": float(Decimal(str(amount_paise)) / 100),
            "averageForCategory": float(avg / 100) if avg else 0.0,
            "threshold": float(ANOMALY_THRESHOLD),
            "category": category,
        }

        if is_anomaly:
            result["message"] = message
            publish_anomaly_alert(
                user_id, user_email, message, caller="anomaly_detector"
            )

        return success(result)

    except Exception as e:
        logger.error("anomaly_detector failed: %s", str(e))
        return server_error("Internal error in anomaly detection")
    finally:
        track_lambda_invocation("anomaly_detector", start_time)
