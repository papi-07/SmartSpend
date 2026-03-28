"""
SmartSpend — Pytest configuration and shared fixtures.
Sets up paths so Lambda layer modules can be imported by all tests.
"""

import os
import sys

# Set environment variables before any Lambda code imports boto3
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["EXPENSES_TABLE"] = "SmartSpend-Expenses"
os.environ["BUDGETS_TABLE"] = "SmartSpend-Budgets"
os.environ["RESOURCE_USAGE_TABLE"] = "SmartSpend-ResourceUsage"
os.environ["USER_SETTINGS_TABLE"] = "SmartSpend-UserSettings"
os.environ["RECEIPTS_BUCKET"] = "smartspend-receipts-test"
os.environ["SNS_TOPIC_ARN"] = "arn:aws:sns:us-east-1:123456789012:SmartSpend-SpendingAlerts"
os.environ["REGION"] = "us-east-1"

# Add the common layer to sys.path so auth_utils, db_utils, response_utils,
# categorizer, resource_tracker all resolve when Lambda code imports them.
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_layer_path = os.path.join(_root, "layers", "common", "python")

if _layer_path not in sys.path:
    sys.path.insert(0, _layer_path)
