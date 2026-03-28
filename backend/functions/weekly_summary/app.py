"""
SmartSpend — Weekly Summary Lambda
====================================
Sends a weekly spending digest email via SNS every Sunday at 9 AM IST.
Triggered by: EventBridge scheduled rule (cron).

For each user with expenses in the past week:
  - Query this week's expenses
  - Calculate total spent, category breakdown, top merchants
  - Compare with last week
  - Send SNS email with formatted summary
"""

import os
import json
import time
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from collections import defaultdict

import boto3
from boto3.dynamodb.conditions import Key, Attr

from db_utils import query_items, scan_items, query_by_partition
from resource_tracker import (
    track_lambda_invocation, track_dynamodb_operation, track_sns_publish,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

EXPENSES_TABLE = os.environ.get("EXPENSES_TABLE", "SmartSpend-Expenses")
USER_SETTINGS_TABLE = os.environ.get("USER_SETTINGS_TABLE", "SmartSpend-UserSettings")
BUDGETS_TABLE = os.environ.get("BUDGETS_TABLE", "SmartSpend-Budgets")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")


def _get_week_range(reference_date=None):
    """Get start (Monday) and end (Sunday) dates for the week containing reference_date."""
    if reference_date is None:
        reference_date = datetime.now(timezone.utc).date()

    # Go back to Monday of this week
    days_since_monday = reference_date.weekday()
    monday = reference_date - timedelta(days=days_since_monday)
    sunday = monday + timedelta(days=6)

    return monday.isoformat(), sunday.isoformat()


def _get_expenses_in_range(user_id, start_date, end_date):
    """Query expenses for a user within a date range."""
    expenses = query_items(
        EXPENSES_TABLE,
        Key("userId").eq(user_id) & Key("date").between(start_date, end_date),
        index_name="date-index",
    )
    return expenses


def _build_summary(expenses):
    """Build weekly summary statistics from a list of expenses."""
    if not expenses:
        return {
            "totalSpent": 0,
            "expenseCount": 0,
            "categoryBreakdown": {},
            "topMerchants": [],
            "dailyTotals": {},
        }

    total_paise = 0
    category_totals = defaultdict(int)
    merchant_totals = defaultdict(int)
    daily_totals = defaultdict(int)

    for exp in expenses:
        amount = int(exp.get("amountPaise") or exp.get("amount", 0))
        total_paise += amount
        category_totals[exp.get("category", "Other")] += amount
        merchant_totals[exp.get("merchant", "Unknown")] += amount
        daily_totals[exp.get("date", "unknown")] += amount

    # Sort categories by amount descending
    sorted_categories = dict(
        sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
    )

    # Top 5 merchants
    top_merchants = sorted(
        merchant_totals.items(), key=lambda x: x[1], reverse=True
    )[:5]

    return {
        "totalSpent": total_paise,
        "expenseCount": len(expenses),
        "categoryBreakdown": sorted_categories,
        "topMerchants": top_merchants,
        "dailyTotals": dict(sorted(daily_totals.items())),
    }


def _format_email(user_id, this_week, last_week, start_date, end_date, budgets=None):
    """Format the weekly summary email body."""
    total_rupees = this_week["totalSpent"] / 100
    last_total_rupees = last_week["totalSpent"] / 100

    lines = [
        f"Hi,",
        f"",
        f"Here's your SmartSpend weekly spending summary for {start_date} to {end_date}.",
        f"",
        f"═══ WEEKLY OVERVIEW ═══",
        f"Total Spent: ₹{total_rupees:,.2f}",
        f"Expenses: {this_week['expenseCount']}",
    ]

    # Week-over-week comparison
    if last_week["totalSpent"] > 0:
        change = total_rupees - last_total_rupees
        pct_change = (change / last_total_rupees) * 100
        direction = "▲" if change > 0 else "▼" if change < 0 else "─"
        lines.append(
            f"vs Last Week: {direction} ₹{abs(change):,.2f} ({abs(pct_change):.1f}% {'more' if change > 0 else 'less'})"
        )
    elif this_week["totalSpent"] > 0:
        lines.append("vs Last Week: No data from last week")

    # Category breakdown
    if this_week["categoryBreakdown"]:
        lines.extend(["", "═══ BY CATEGORY ═══"])
        for cat, amount_paise in this_week["categoryBreakdown"].items():
            pct = (amount_paise / this_week["totalSpent"]) * 100 if this_week["totalSpent"] > 0 else 0
            lines.append(f"  {cat}: ₹{amount_paise / 100:,.2f} ({pct:.0f}%)")

    # Top merchants
    if this_week["topMerchants"]:
        lines.extend(["", "═══ TOP MERCHANTS ═══"])
        for merchant, amount_paise in this_week["topMerchants"]:
            lines.append(f"  {merchant}: ₹{amount_paise / 100:,.2f}")

    # Budget status
    if budgets:
        lines.extend(["", "═══ BUDGET STATUS ═══"])
        now = datetime.now(timezone.utc)
        year_month = now.strftime("%Y-%m")
        for b in budgets:
            cat = b["category"]
            limit_paise = int(b.get("monthlyLimitPaise", 0))
            if limit_paise <= 0:
                continue
            # We need monthly spending, not just weekly
            # For simplicity, show the budget info we have
            limit_rupees = limit_paise / 100
            lines.append(f"  {cat}: Budget ₹{limit_rupees:,.2f}/month")

    # Daily breakdown
    if this_week["dailyTotals"]:
        lines.extend(["", "═══ DAILY BREAKDOWN ═══"])
        for date, amount_paise in this_week["dailyTotals"].items():
            lines.append(f"  {date}: ₹{amount_paise / 100:,.2f}")

    lines.extend([
        "",
        "Review your expenses at the SmartSpend dashboard.",
        "",
        f"— SmartSpend",
    ])

    return "\n".join(lines)


def _get_active_users():
    """
    Get users to send weekly summary to.

    Uses Scan on UserSettings table — acceptable because:
      1. UserSettings is a small table (one row per user, ~100 bytes each)
      2. This runs ONCE per week (Sunday cron), not on hot path
      3. UserSettings has userId as HASH key only — no way to Query "all users"
         without a GSI, which isn't worth the cost for a weekly batch job
      4. Even with 1000 users, a single Scan uses <1 RCU
    """
    users = scan_items(USER_SETTINGS_TABLE)
    track_dynamodb_operation("weekly_summary", "read", units=max(1, len(users) // 4))

    active_users = []
    for u in users:
        # Default: digest enabled unless explicitly disabled
        if u.get("weeklyDigestEnabled", True):
            active_users.append({
                "userId": u["userId"],
                "email": u.get("email", ""),
                "name": u.get("name", ""),
            })

    if active_users:
        return active_users

    # Fallback: get distinct users from recent expenses
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # We can't easily get distinct users without a scan, so return empty
    # The weekly summary will be triggered per-user when we have UserSettings entries
    logger.info("No users found in UserSettings — skipping weekly summary")
    return []


def lambda_handler(event, context):
    """Handle EventBridge scheduled event — send weekly summaries."""
    start_time = time.time()

    try:
        logger.info("WeeklySummary triggered: %s", json.dumps(event))

        if not SNS_TOPIC_ARN:
            logger.warning("SNS_TOPIC_ARN not set — cannot send weekly summaries")
            return {"statusCode": 200, "body": "SNS not configured"}

        # Get date ranges
        now = datetime.now(timezone.utc).date()
        this_start, this_end = _get_week_range(now)
        last_week_date = now - timedelta(days=7)
        last_start, last_end = _get_week_range(last_week_date)

        # Get active users
        users = _get_active_users()
        if not users:
            logger.info("No active users for weekly summary")
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "No users to send summary to"}),
            }

        sns = boto3.client("sns", region_name=os.environ.get("REGION", "us-east-1"))
        summaries_sent = 0

        for user in users:
            try:
                user_id = user["userId"]

                # Get this week's expenses
                this_expenses = _get_expenses_in_range(user_id, this_start, this_end)
                track_dynamodb_operation("weekly_summary", "read",
                                        units=max(1, len(this_expenses) // 4))

                # Skip users with no activity this week
                if not this_expenses:
                    continue

                # Get last week's expenses for comparison
                last_expenses = _get_expenses_in_range(user_id, last_start, last_end)
                track_dynamodb_operation("weekly_summary", "read",
                                        units=max(1, len(last_expenses) // 4))

                # Get budget data
                budgets = query_by_partition(BUDGETS_TABLE, "userId", user_id)
                track_dynamodb_operation("weekly_summary", "read",
                                        units=max(1, len(budgets) // 4))

                # Build summaries
                this_summary = _build_summary(this_expenses)
                last_summary = _build_summary(last_expenses)

                # Format email
                email_body = _format_email(
                    user_id, this_summary, last_summary,
                    this_start, this_end, budgets,
                )

                # Send via SNS
                sns.publish(
                    TopicArn=SNS_TOPIC_ARN,
                    Subject=f"📊 SmartSpend — Weekly Summary ({this_start} to {this_end})",
                    Message=email_body,
                )
                track_sns_publish("weekly_summary")
                summaries_sent += 1

                logger.info(
                    "Weekly summary sent: user=%s, expenses=%d, total=₹%.2f",
                    user_id, this_summary["expenseCount"],
                    this_summary["totalSpent"] / 100,
                )

            except Exception as e:
                logger.error("Failed to send summary for %s: %s", user.get("userId"), str(e))

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": f"Weekly summaries sent to {summaries_sent} user(s)",
                "userCount": len(users),
                "summariesSent": summaries_sent,
                "weekRange": f"{this_start} to {this_end}",
            }),
        }

    except Exception as e:
        logger.error("weekly_summary failed: %s", str(e))
        return {"statusCode": 500, "body": f"Internal error: {str(e)}"}
    finally:
        track_lambda_invocation("weekly_summary", start_time)
