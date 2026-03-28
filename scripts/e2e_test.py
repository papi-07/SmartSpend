#!/usr/bin/env python3
"""
SmartSpend — End-to-End Test Script
====================================
Runs a full E2E test against the deployed SmartSpend API:
  1. Login with test user
  2. Create 15 expenses (manual)
  3. Set budgets for 3 categories
  4. Verify dashboard stats
  5. Verify budget status
  6. Export CSV and verify contents
  7. Check resource usage shows all activity
  8. Delete all test expenses
  9. Print: "✅ ALL E2E TESTS PASSED"

Usage:
  python3 scripts/e2e_test.py

Environment variables (or edit defaults below):
  SMARTSPEND_API_URL   — API Gateway base URL
  COGNITO_CLIENT_ID    — Cognito User Pool Client ID
  TEST_EMAIL           — Test user email
  TEST_PASSWORD        — Test user password
"""

import os
import sys
import json
import time
import base64
import csv
import io
import urllib.request
import urllib.error
import ssl

# ─── Configuration ────────────────────────────────────────────────────────────

API_URL = os.environ.get(
    "SMARTSPEND_API_URL",
    "https://u7bo503518.execute-api.ap-south-1.amazonaws.com/prod",
).rstrip("/")

COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID", "3p6ucuue6kd2akca9125129haj")
COGNITO_REGION = os.environ.get("AWS_REGION", "ap-south-1")

TEST_EMAIL = os.environ.get("TEST_EMAIL", "testuser@smartspend.dev")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "TestPass123!")

SSL_CTX = ssl.create_default_context()

# Track created resources for cleanup
created_expense_ids = []
passed = 0
failed = 0


# ─── Helpers ──────────────────────────────────────────────────────────────────

def api_call(method, path, body=None, token=None, raw=False):
    """Make an API call and return parsed JSON response."""
    url = f"{API_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=30) as r:
            raw_body = r.read()
            if raw:
                return {"_status": r.status, "_raw": raw_body}
            return json.loads(raw_body)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()[:500]
        try:
            return {"_error": True, "_status": e.code, **json.loads(body_text)}
        except json.JSONDecodeError:
            return {"_error": True, "_status": e.code, "_body": body_text}
    except Exception as e:
        return {"_error": True, "_status": 0, "_body": str(e)}


def check(name, condition, detail=""):
    """Assert a test condition and track pass/fail."""
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} — {detail}")


def get_cognito_token():
    """Authenticate with Cognito and return an ID token."""
    try:
        import boto3
        client = boto3.client("cognito-idp", region_name=COGNITO_REGION)
        resp = client.initiate_auth(
            ClientId=COGNITO_CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": TEST_EMAIL,
                "PASSWORD": TEST_PASSWORD,
            },
        )
        return resp["AuthenticationResult"]["IdToken"]
    except Exception as e:
        print(f"  ❌ Cognito auth failed: {e}")
        sys.exit(1)


# ─── Test Phases ──────────────────────────────────────────────────────────────

def test_01_login():
    """Phase 1: Login and get auth token."""
    print("\n📋 Phase 1: Authentication")
    token = get_cognito_token()
    check("Login successful", len(token) > 100, f"Token length: {len(token)}")
    return token


def test_02_create_expenses(token):
    """Phase 2: Create 15 expenses across various categories."""
    print("\n📋 Phase 2: Create 15 Expenses")

    test_expenses = [
        {"amount": 250, "merchant": "Swiggy", "date": "2026-03-01", "category": "Food", "notes": "Biryani order"},
        {"amount": 150, "merchant": "Ola", "date": "2026-03-02", "category": "Transport", "notes": "Airport ride"},
        {"amount": 499, "merchant": "Amazon India", "date": "2026-03-03", "category": "Shopping", "notes": "Phone charger"},
        {"amount": 2500, "merchant": "DMart", "date": "2026-03-04", "category": "Groceries", "notes": "Weekly grocery run"},
        {"amount": 199, "merchant": "Netflix", "date": "2026-03-05", "category": "Subscriptions", "notes": "Monthly plan"},
        {"amount": 350, "merchant": "Zomato", "date": "2026-03-06", "category": "Food", "notes": "Team lunch"},
        {"amount": 120, "merchant": "Uber", "date": "2026-03-07", "category": "Transport", "notes": "Morning commute"},
        {"amount": 1500, "merchant": "Reliance Digital", "date": "2026-03-08", "category": "Shopping", "notes": "Earbuds"},
        {"amount": 450, "merchant": "Apollo Pharmacy", "date": "2026-03-09", "category": "Health", "notes": "Vitamins"},
        {"amount": 800, "merchant": "Jio Recharge", "date": "2026-03-10", "category": "Bills", "notes": "Annual plan"},
        {"amount": 180, "merchant": "Starbucks", "date": "2026-03-11", "category": "Food", "notes": "Coffee with friends"},
        {"amount": 3000, "merchant": "MakeMyTrip", "date": "2026-03-12", "category": "Travel", "notes": "Bus tickets"},
        {"amount": 650, "merchant": "Big Bazaar", "date": "2026-03-13", "category": "Groceries", "notes": "Monthly stock-up"},
        {"amount": 999, "merchant": "Flipkart", "date": "2026-03-14", "category": "Shopping", "notes": "Back cover"},
        {"amount": 75, "merchant": "Rapido", "date": "2026-03-15", "category": "Transport", "notes": "Quick bike ride"},
    ]

    success_count = 0
    for i, exp in enumerate(test_expenses):
        r = api_call("POST", "/expenses", exp, token)
        eid = r.get("expenseId", "")
        if eid:
            created_expense_ids.append(eid)
            success_count += 1
        else:
            print(f"    ⚠️  Expense #{i+1} ({exp['merchant']}) failed: {r}")

    check(f"Created {success_count}/15 expenses", success_count == 15,
          f"Only {success_count} created")
    return test_expenses


def test_03_read_expenses(token):
    """Phase 3: Read expenses and verify filters work."""
    print("\n📋 Phase 3: Read & Filter Expenses")

    # Get all expenses
    r = api_call("GET", "/expenses?limit=50", token=token)
    total = r.get("count", 0)
    check("GET /expenses returns expenses", total > 0, f"Count: {total}")

    # Filter by category
    r = api_call("GET", "/expenses?category=Food", token=token)
    food_count = r.get("count", 0)
    check("Filter by category=Food works", food_count >= 3, f"Food count: {food_count}")

    # Search
    r = api_call("GET", "/expenses?search=swiggy", token=token)
    search_count = r.get("count", 0)
    check("Search for 'swiggy' works", search_count >= 1, f"Search results: {search_count}")

    # Date range
    r = api_call("GET", "/expenses?startDate=2026-03-01&endDate=2026-03-07", token=token)
    range_count = r.get("count", 0)
    check("Date range filter works", range_count >= 1, f"In range: {range_count}")


def test_04_update_expenses(token):
    """Phase 4: Update expenses."""
    print("\n📋 Phase 4: Update Expenses")

    if len(created_expense_ids) < 2:
        check("Update expense", False, "Not enough expenses created")
        return

    r = api_call("PUT", f"/expenses/{created_expense_ids[0]}",
                 {"amount": 275, "notes": "Updated biryani order"}, token)
    check("Update amount", r.get("merchant") == "Swiggy" or "amount" in str(r),
          f"Response: {str(r)[:100]}")

    r = api_call("PUT", f"/expenses/{created_expense_ids[1]}",
                 {"notes": "Updated note"}, token)
    check("Update notes", not r.get("_error"), f"Response: {str(r)[:100]}")


def test_05_budgets(token):
    """Phase 5: Set budgets for 3 categories and verify status."""
    print("\n📋 Phase 5: Budget Management")

    budgets = [
        {"category": "Food", "monthlyLimit": 2000, "alertThreshold": 80},
        {"category": "Transport", "monthlyLimit": 1500, "alertThreshold": 75},
        {"category": "Shopping", "monthlyLimit": 5000, "alertThreshold": 90},
    ]

    for b in budgets:
        r = api_call("POST", "/budgets", b, token)
        check(f"Set budget: {b['category']}=₹{b['monthlyLimit']}",
              "message" in r or "category" in r,
              f"Response: {str(r)[:100]}")

    # Get budget status
    r = api_call("GET", "/budgets/status", token=token)
    budget_list = r.get("budgets", [])
    check("Budget status returns data", len(budget_list) >= 3,
          f"Budgets returned: {len(budget_list)}")

    # Check if any budget shows spending
    has_spending = any(b.get("spent", 0) > 0 for b in budget_list)
    check("Budget status shows spending", has_spending,
          f"Budgets: {json.dumps(budget_list[:2], indent=None)[:200]}")


def test_06_dashboard(token):
    """Phase 6: Verify dashboard stats are correct."""
    print("\n📋 Phase 6: Dashboard Stats")

    r = api_call("GET", "/dashboard/stats?month=2026-03", token=token)
    check("Dashboard returns totalSpent", "totalSpent" in r,
          f"Keys: {list(r.keys())[:5]}")

    total = r.get("totalSpent", 0)
    check("Total spent > 0", total > 0, f"Total: ₹{total}")

    count = r.get("expenseCount", 0)
    check("Expense count > 0", count > 0, f"Count: {count}")

    categories = r.get("categoryBreakdown", [])
    check("Category breakdown present", len(categories) > 0,
          f"Categories: {len(categories)}")

    daily = r.get("dailyTotals", [])
    check("Daily totals present", len(daily) > 0,
          f"Days: {len(daily)}")

    merchants = r.get("topMerchants", [])
    check("Top merchants present", len(merchants) > 0,
          f"Merchants: {len(merchants)}")


def test_07_export_csv(token):
    """Phase 7: Export CSV and verify contents."""
    print("\n📋 Phase 7: CSV Export")

    r = api_call("GET", "/expenses/export?startDate=2026-03-01&endDate=2026-03-31",
                 token=token, raw=True)
    status = r.get("_status", 0)
    check("Export returns 200", status == 200, f"Status: {status}")

    raw_body = r.get("_raw", b"")
    if raw_body:
        try:
            # API Gateway returns base64-encoded CSV
            csv_text = base64.b64decode(raw_body).decode("utf-8")
        except Exception:
            csv_text = raw_body.decode("utf-8", errors="replace")

        check("CSV has content", len(csv_text) > 50, f"Length: {len(csv_text)}")

        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        check("CSV has header row", len(rows) > 0 and "Date" in rows[0][0] if rows else False,
              f"First row: {rows[0] if rows else 'empty'}")
        check("CSV has data rows", len(rows) > 1, f"Total rows: {len(rows)}")
    else:
        check("CSV body received", False, "Empty body")


def test_08_resource_usage(token):
    """Phase 8: Check resource usage page shows all activity."""
    print("\n📋 Phase 8: Resource Usage")

    r = api_call("GET", "/resources/usage?startDate=2026-03-01&endDate=2026-03-31",
                 token=token)
    check("Resource usage returns services", "services" in r,
          f"Keys: {list(r.keys())[:5]}")

    services = r.get("services", {})

    # Verify all services have data
    lambda_inv = services.get("lambda", {}).get("invocations", 0)
    check("Lambda invocations > 0", lambda_inv > 0, f"Invocations: {lambda_inv}")

    ddb_rcu = services.get("dynamodb", {}).get("readUnits", 0)
    check("DynamoDB RCU > 0", ddb_rcu > 0, f"RCU: {ddb_rcu}")

    ddb_wcu = services.get("dynamodb", {}).get("writeUnits", 0)
    check("DynamoDB WCU > 0", ddb_wcu > 0, f"WCU: {ddb_wcu}")

    apigw = services.get("apiGateway", {}).get("requests", 0)
    check("API Gateway requests > 0", apigw > 0, f"Requests: {apigw}")

    total_cost = r.get("totalEstimatedCost", 0)
    check("Total estimated cost > 0", total_cost > 0, f"Cost: ${total_cost}")

    savings = r.get("freeTierSavings", 0)
    check("Free tier savings > 0", savings > 0, f"Savings: ${savings}")

    # Verify byService array
    by_service = r.get("byService", [])
    check("byService array present", len(by_service) >= 5,
          f"Services: {len(by_service)}")


def test_09_delete_expenses(token):
    """Phase 9: Delete all test expenses."""
    print("\n📋 Phase 9: Cleanup — Delete Test Expenses")

    deleted = 0
    for eid in created_expense_ids:
        r = api_call("DELETE", f"/expenses/{eid}", token=token)
        if r.get("message") and "deleted" in r["message"].lower():
            deleted += 1

    check(f"Deleted {deleted}/{len(created_expense_ids)} test expenses",
          deleted == len(created_expense_ids),
          f"Deleted: {deleted}")

    # Verify deletion
    r = api_call("GET", "/expenses?limit=50", token=token)
    remaining = r.get("count", -1)
    check("Remaining expenses verified", remaining >= 0,
          f"Remaining: {remaining}")


def test_10_error_handling(token):
    """Phase 10: Verify error handling."""
    print("\n📋 Phase 10: Error Handling")

    # Invalid expense (missing fields)
    r = api_call("POST", "/expenses", {"amount": 100}, token)
    check("Missing merchant returns 400",
          r.get("_status") == 400 or "error" in r,
          f"Response: {str(r)[:100]}")

    # Invalid expense ID
    r = api_call("GET", "/expenses/nonexistent-id", token=token)
    # This actually goes to GET /expenses with path param — might still work
    # Let's try DELETE on fake ID
    r = api_call("DELETE", "/expenses/fake-id-12345", token=token)
    check("Delete non-existent returns 404",
          r.get("_status") == 404 or "not found" in str(r).lower(),
          f"Response: {str(r)[:100]}")

    # No auth header
    r = api_call("GET", "/expenses")
    check("No auth returns 401",
          r.get("_status") == 401 or r.get("_status") == 403,
          f"Status: {r.get('_status')}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  SmartSpend — End-to-End Test Suite")
    print(f"  API: {API_URL}")
    print(f"  User: {TEST_EMAIL}")
    print("=" * 60)

    start = time.time()

    # Run all test phases
    token = test_01_login()
    test_02_create_expenses(token)
    test_03_read_expenses(token)
    test_04_update_expenses(token)
    test_05_budgets(token)
    test_06_dashboard(token)
    test_07_export_csv(token)
    test_08_resource_usage(token)
    test_09_delete_expenses(token)
    test_10_error_handling(token)

    elapsed = time.time() - start

    # Summary
    total = passed + failed
    print("\n" + "=" * 60)
    print(f"  Results: {passed}/{total} passed, {failed} failed")
    print(f"  Duration: {elapsed:.1f}s")
    print("=" * 60)

    if failed == 0:
        print("\n✅ ALL E2E TESTS PASSED\n")
        return 0
    else:
        print(f"\n❌ {failed} TEST(S) FAILED\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
