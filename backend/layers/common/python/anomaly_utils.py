"""
SmartSpend — Anomaly Detection Utility (Shared Layer)
=====================================================
Single source of truth for anomaly detection logic.
Called from create_expense and process_receipt Lambdas.

Algorithm:
  1. Query last 30 days of expenses for this user+category
  2. Calculate mean and standard deviation
  3. If amount > mean + 2.5 * std_dev → anomaly
  4. Also check: if amount > 3× the median → anomaly
  5. Special case: if fewer than 3 expenses exist, use absolute threshold (₹5000)
"""

import os
import math
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key, Attr

from db_utils import query_items, get_item, query_by_partition
from resource_tracker import track_dynamodb_operation, track_sns_publish

logger = logging.getLogger(__name__)

EXPENSES_TABLE = os.environ.get("EXPENSES_TABLE", "SmartSpend-Expenses")
BUDGETS_TABLE = os.environ.get("BUDGETS_TABLE", "SmartSpend-Budgets")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
ANOMALY_THRESHOLD = Decimal("2.5")
MEDIAN_MULTIPLIER = 3.0
ABSOLUTE_THRESHOLD_PAISE = 500000  # ₹5,000 in paise


def _compute_stats(amounts):
    """Compute mean, standard deviation, and median for a list of amounts."""
    n = len(amounts)
    if n == 0:
        return 0.0, 0.0, 0.0

    mean = sum(amounts) / n

    if n == 1:
        std_dev = 0.0
    else:
        variance = sum((x - mean) ** 2 for x in amounts) / (n - 1)
        std_dev = math.sqrt(variance)

    sorted_amounts = sorted(amounts)
    if n % 2 == 1:
        median = sorted_amounts[n // 2]
    else:
        median = (sorted_amounts[n // 2 - 1] + sorted_amounts[n // 2]) / 2

    return mean, std_dev, median


def check_anomaly(user_id, category, amount_paise, caller="unknown"):
    """
    Check if an expense is anomalous using statistical analysis.

    Algorithm:
      1. Query last 30 days of expenses for this user+category
      2. If fewer than 3 expenses → use absolute threshold (₹5,000)
      3. If amount > mean + 2.5 × std_dev → anomaly
      4. If amount > 3 × median → anomaly

    Args:
        user_id:      The user's ID (partition key).
        category:     The expense category to compare against.
        amount_paise: The expense amount in paise (integer).
        caller:       Name of the calling function (for resource tracking).

    Returns:
        tuple: (is_anomaly: bool, avg_paise: Decimal, message: str)
               message is empty if not anomalous.
    """
    try:
        if not user_id or not category:
            return False, Decimal("0"), ""

        thirty_days_ago = (
            datetime.now(timezone.utc) - timedelta(days=30)
        ).strftime("%Y-%m-%d")

        # Query user's expenses (all dates) then filter in-memory
        expenses = query_items(
            EXPENSES_TABLE,
            Key("userId").eq(user_id),
            index_name="date-index",
            filter_expression=Attr("category").eq(category),
        )
        track_dynamodb_operation(caller, "read", units=max(1, len(expenses) // 4))

        if not expenses:
            # No history — use absolute threshold
            if amount_paise > ABSOLUTE_THRESHOLD_PAISE:
                return (
                    True,
                    Decimal("0"),
                    f"Anomaly detected: ₹{amount_paise / 100:.2f} in {category} "
                    f"exceeds ₹{ABSOLUTE_THRESHOLD_PAISE / 100:.0f} threshold "
                    f"(no spending history in this category)",
                )
            return False, Decimal("0"), ""

        # Filter to last 30 days
        recent = [e for e in expenses if e.get("date", "") >= thirty_days_ago]
        if not recent:
            # No recent history — use absolute threshold
            if amount_paise > ABSOLUTE_THRESHOLD_PAISE:
                return (
                    True,
                    Decimal("0"),
                    f"Anomaly detected: ₹{amount_paise / 100:.2f} in {category} "
                    f"exceeds ₹{ABSOLUTE_THRESHOLD_PAISE / 100:.0f} threshold "
                    f"(no recent spending in this category)",
                )
            return False, Decimal("0"), ""

        # Extract amounts in paise
        amounts = [
            float(e.get("amountPaise") or e.get("amount", 0))
            for e in recent
        ]
        amounts = [a for a in amounts if a > 0]

        if not amounts:
            return False, Decimal("0"), ""

        amount = float(amount_paise)
        mean, std_dev, median = _compute_stats(amounts)
        avg_decimal = Decimal(str(round(mean, 2)))

        # Special case: fewer than 3 expenses → use absolute threshold
        if len(amounts) < 3:
            if amount > ABSOLUTE_THRESHOLD_PAISE:
                multiplier = amount / mean if mean > 0 else 0
                return (
                    True,
                    avg_decimal,
                    f"Anomaly detected: ₹{amount / 100:.2f} in {category} "
                    f"exceeds ₹{ABSOLUTE_THRESHOLD_PAISE / 100:.0f} threshold "
                    f"(only {len(amounts)} expense(s) in history, "
                    f"avg ₹{mean / 100:.2f})",
                )
            return False, avg_decimal, ""

        # Check 1: amount > mean + 2.5 × std_dev
        threshold_stddev = mean + 2.5 * std_dev
        if std_dev > 0 and amount > threshold_stddev:
            multiplier = amount / mean if mean > 0 else 0
            return (
                True,
                avg_decimal,
                f"Anomaly detected: ₹{amount / 100:.2f} in {category} "
                f"is {multiplier:.1f}× the 30-day average of ₹{mean / 100:.2f} "
                f"(exceeds mean + 2.5σ threshold of ₹{threshold_stddev / 100:.2f})",
            )

        # Check 2: amount > 3 × median
        if median > 0 and amount > MEDIAN_MULTIPLIER * median:
            multiplier = amount / median
            return (
                True,
                avg_decimal,
                f"Anomaly detected: ₹{amount / 100:.2f} in {category} "
                f"is {multiplier:.1f}× the 30-day median of ₹{median / 100:.2f} "
                f"(exceeds 3× median threshold)",
            )

        # Check 3: fallback for zero std_dev (all same amount) — use 2.5× mean
        if std_dev == 0 and mean > 0 and amount > float(ANOMALY_THRESHOLD) * mean:
            multiplier = amount / mean
            return (
                True,
                avg_decimal,
                f"Anomaly detected: ₹{amount / 100:.2f} in {category} "
                f"is {multiplier:.1f}× the 30-day average of ₹{mean / 100:.2f}",
            )

        return False, avg_decimal, ""

    except Exception as e:
        logger.warning("Anomaly check failed (%s): %s", caller, str(e))
        return False, Decimal("0"), ""


def publish_anomaly_alert(user_id, user_email, message, caller="unknown"):
    """
    Publish an anomaly alert to the SNS topic with rich formatted email.

    Args:
        user_id:    User identifier (fallback if no email).
        user_email: User's email address (optional).
        message:    The anomaly alert message body.
        caller:     Name of the calling function (for resource tracking).
    """
    try:
        if not SNS_TOPIC_ARN:
            logger.warning("SNS_TOPIC_ARN not set — skipping anomaly alert")
            return

        sns = boto3.client("sns", region_name=os.environ.get("REGION", "us-east-1"))

        subject = "⚠️ SmartSpend Alert — Unusual Spending Detected"
        body = (
            f"Hi,\n\n"
            f"We detected unusual spending on your account.\n\n"
            f"{message}\n\n"
            f"If this is expected, no action needed. "
            f"Otherwise, review your expenses in the SmartSpend dashboard.\n\n"
            f"User: {user_email or user_id}\n\n"
            f"— SmartSpend"
        )

        sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=body)
        track_sns_publish(caller)
        logger.info("Anomaly alert published for %s", user_email or user_id)

    except Exception as e:
        logger.warning("Failed to publish anomaly alert (%s): %s", caller, str(e))


def publish_budget_alert(user_id, user_email, category, spent_paise,
                         limit_paise, percent_used, caller="unknown"):
    """
    Publish a budget threshold alert to the SNS topic.

    Args:
        user_id:      User identifier.
        user_email:   User's email address (optional).
        category:     Budget category.
        spent_paise:  Amount spent in paise.
        limit_paise:  Budget limit in paise.
        percent_used: Percentage of budget used.
        caller:       Name of the calling function.
    """
    try:
        if not SNS_TOPIC_ARN:
            logger.warning("SNS_TOPIC_ARN not set — skipping budget alert")
            return

        sns = boto3.client("sns", region_name=os.environ.get("REGION", "us-east-1"))

        spent_rupees = spent_paise / 100
        limit_rupees = limit_paise / 100
        remaining_rupees = max(0, (limit_paise - spent_paise)) / 100

        subject = f"📊 SmartSpend — Budget Alert for {category}"
        body = (
            f"Hi,\n\n"
            f"You've used {percent_used:.0f}% of your monthly {category} budget.\n\n"
            f"Spent: ₹{spent_rupees:,.2f} / ₹{limit_rupees:,.2f}\n"
            f"Remaining: ₹{remaining_rupees:,.2f}\n\n"
            f"User: {user_email or user_id}\n\n"
            f"— SmartSpend"
        )

        sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=body)
        track_sns_publish(caller)
        logger.info("Budget alert published for %s — %s at %.0f%%",
                     user_email or user_id, category, percent_used)

    except Exception as e:
        logger.warning("Failed to publish budget alert (%s): %s", caller, str(e))


def check_budget(user_id, user_email, category, caller="unknown",
                  current_amount_paise=0):
    """
    Check if the user's spending in a category has crossed a budget threshold.
    Called AFTER an expense is saved to DynamoDB — queries current month
    spending and compares against the budget alert threshold.

    Only sends an alert when spending crosses exactly two thresholds:
      1. The configured alertThreshold (default 80%)
      2. The 100% mark (budget fully used)
    No alerts at any other percentage — avoids spam.

    Args:
        user_id:              User identifier.
        user_email:           User's email (optional).
        category:             Expense category.
        caller:               Name of the calling function.
        current_amount_paise: Amount of the expense just created (in paise).
                              Used to calculate previous spending accurately
                              instead of relying on query ordering.

    Returns:
        dict or None: Budget alert info if threshold crossed, None otherwise.
    """
    try:
        if not user_id or not category:
            return None

        # Look up budget for this user + category
        budget = get_item(BUDGETS_TABLE, {"userId": user_id, "category": category})
        track_dynamodb_operation(caller, "read", units=1)

        if not budget:
            return None  # No budget set for this category

        limit_paise = int(budget.get("monthlyLimitPaise", 0))
        alert_threshold = float(budget.get("alertThreshold", 80))

        if limit_paise <= 0:
            return None

        # Query current month spending for this category
        now = datetime.now(timezone.utc)
        year_month = now.strftime("%Y-%m")
        start_date = f"{year_month}-01"
        year, month = now.year, now.month
        if month == 12:
            end_date = f"{year + 1}-01-01"
        else:
            end_date = f"{year}-{month + 1:02d}-01"

        from boto3.dynamodb.conditions import Attr as A
        expenses = query_items(
            EXPENSES_TABLE,
            Key("userId").eq(user_id) & Key("date").between(start_date, end_date),
            index_name="date-index",
            filter_expression=A("category").eq(category),
        )
        track_dynamodb_operation(caller, "read", units=max(1, len(expenses) // 4))

        spent_paise = sum(
            int(e.get("amountPaise") or e.get("amount", 0))
            for e in expenses
        )

        percent_used = (spent_paise / limit_paise) * 100 if limit_paise > 0 else 0

        if percent_used >= alert_threshold:
            # Calculate previous spending by subtracting the current expense amount.
            # This is reliable because current_amount_paise is passed explicitly —
            # no dependency on query ordering or which expense is "last".
            previous_paise = max(0, spent_paise - int(current_amount_paise))
            previous_pct = (previous_paise / limit_paise) * 100 if limit_paise > 0 else 0

            # Only alert at exactly two thresholds:
            #   1. Configured alertThreshold (e.g. 80%)
            #   2. 100% — budget fully used
            crossed_threshold = previous_pct < alert_threshold <= percent_used
            crossed_100 = previous_pct < 100 <= percent_used

            if crossed_threshold or crossed_100:
                publish_budget_alert(
                    user_id, user_email, category,
                    spent_paise, limit_paise, percent_used,
                    caller=caller,
                )
                return {
                    "category": category,
                    "spent": spent_paise / 100,
                    "limit": limit_paise / 100,
                    "percentUsed": round(percent_used, 1),
                    "alertSent": True,
                }

            # Already past threshold but not crossing a new band — no alert
            return {
                "category": category,
                "spent": spent_paise / 100,
                "limit": limit_paise / 100,
                "percentUsed": round(percent_used, 1),
                "alertSent": False,
            }

        return None

    except Exception as e:
        logger.warning("Budget check failed (%s): %s", caller, str(e))
        return None
