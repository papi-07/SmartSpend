#!/usr/bin/env python3
"""
SmartSpend — Seed Data Script
==============================
Generates 100 realistic sample expenses spread over the last 3 months.
Uses Indian merchants, INR amounts, and realistic spending patterns.
Includes some anomalous entries for demo purposes.

Usage:
  python3 scripts/seed_data.py

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
import random
import urllib.request
import urllib.error
import ssl
from datetime import datetime, timedelta

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

# ─── Indian Merchant Data ────────────────────────────────────────────────────

MERCHANTS = {
    "Food": [
        ("Swiggy", 150, 800, "Online food delivery"),
        ("Zomato", 200, 900, "Restaurant order"),
        ("Domino's Pizza", 300, 700, "Pizza night"),
        ("Starbucks", 250, 650, "Coffee & snacks"),
        ("Haldiram's", 100, 500, "Sweets & namkeen"),
        ("McDonald's", 150, 450, "Quick meal"),
        ("Chai Point", 50, 200, "Evening chai"),
        ("Barbeque Nation", 800, 2000, "Dinner buffet"),
    ],
    "Transport": [
        ("Ola", 80, 500, "Cab ride"),
        ("Uber", 100, 600, "City commute"),
        ("Rapido", 30, 150, "Bike taxi"),
        ("Metro Card Recharge", 200, 500, "Monthly metro"),
        ("Indian Oil Fuel", 500, 3000, "Petrol fill-up"),
        ("IRCTC", 300, 2500, "Train ticket"),
    ],
    "Shopping": [
        ("Amazon India", 200, 5000, "Online shopping"),
        ("Flipkart", 150, 4000, "E-commerce purchase"),
        ("Myntra", 500, 3000, "Fashion & apparel"),
        ("Reliance Digital", 1000, 15000, "Electronics"),
        ("Croma", 500, 8000, "Gadgets"),
        ("Decathlon", 300, 3000, "Sports gear"),
    ],
    "Groceries": [
        ("DMart", 500, 4000, "Weekly groceries"),
        ("Big Bazaar", 300, 3500, "Household supplies"),
        ("BigBasket", 400, 3000, "Online grocery"),
        ("Zepto", 100, 800, "Quick delivery"),
        ("Blinkit", 80, 600, "Instant grocery"),
        ("Nature's Basket", 300, 2000, "Organic produce"),
    ],
    "Bills": [
        ("Jio Recharge", 200, 900, "Mobile recharge"),
        ("Airtel", 300, 1200, "Broadband bill"),
        ("Electricity Bill", 500, 3000, "Monthly electricity"),
        ("Water Bill", 100, 500, "Municipal water"),
        ("Gas Cylinder", 800, 1100, "LPG refill"),
    ],
    "Health": [
        ("Apollo Pharmacy", 100, 1500, "Medicines"),
        ("Practo", 300, 800, "Doctor consultation"),
        ("1mg", 150, 1000, "Online pharmacy"),
        ("Cult.fit", 500, 2000, "Gym membership"),
    ],
    "Entertainment": [
        ("BookMyShow", 200, 800, "Movie tickets"),
        ("Netflix", 149, 649, "Streaming subscription"),
        ("Spotify", 59, 119, "Music subscription"),
        ("PVR Cinemas", 300, 900, "Weekend movie"),
    ],
    "Education": [
        ("Udemy", 400, 3000, "Online course"),
        ("Amazon Kindle", 100, 500, "E-books"),
        ("Coursera", 2000, 5000, "Professional course"),
    ],
    "Subscriptions": [
        ("Netflix", 149, 649, "Monthly subscription"),
        ("Amazon Prime", 179, 1499, "Annual membership"),
        ("Spotify", 59, 119, "Music plan"),
        ("YouTube Premium", 129, 189, "Ad-free streaming"),
        ("iCloud Storage", 75, 250, "Cloud storage"),
    ],
    "Travel": [
        ("MakeMyTrip", 1500, 15000, "Flight/hotel booking"),
        ("IRCTC", 500, 5000, "Train tickets"),
        ("OYO Rooms", 800, 3000, "Hotel stay"),
        ("RedBus", 300, 2000, "Bus tickets"),
        ("Cleartrip", 2000, 10000, "Travel package"),
    ],
}

# Budgets to set
BUDGETS = [
    {"category": "Food", "monthlyLimit": 8000, "alertThreshold": 80},
    {"category": "Transport", "monthlyLimit": 5000, "alertThreshold": 75},
    {"category": "Shopping", "monthlyLimit": 10000, "alertThreshold": 85},
    {"category": "Groceries", "monthlyLimit": 6000, "alertThreshold": 80},
    {"category": "Bills", "monthlyLimit": 5000, "alertThreshold": 90},
    {"category": "Entertainment", "monthlyLimit": 3000, "alertThreshold": 80},
]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def api_call(method, path, body=None, token=None):
    """Make an API call and return parsed JSON."""
    url = f"{API_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_error": True, "_status": e.code, "_body": e.read().decode()[:200]}
    except Exception as e:
        return {"_error": True, "_body": str(e)}


def get_token():
    """Get Cognito auth token."""
    import boto3
    client = boto3.client("cognito-idp", region_name=COGNITO_REGION)
    resp = client.initiate_auth(
        ClientId=COGNITO_CLIENT_ID,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": TEST_EMAIL, "PASSWORD": TEST_PASSWORD},
    )
    return resp["AuthenticationResult"]["IdToken"]


def random_date(days_back=90):
    """Generate a random date within the last N days."""
    delta = random.randint(0, days_back)
    d = datetime.now() - timedelta(days=delta)
    return d.strftime("%Y-%m-%d")


def generate_expenses(count=100):
    """Generate realistic expense data."""
    expenses = []
    categories = list(MERCHANTS.keys())

    # Weight categories by typical spending frequency
    weights = {
        "Food": 25, "Transport": 15, "Shopping": 10, "Groceries": 12,
        "Bills": 8, "Health": 5, "Entertainment": 8, "Education": 3,
        "Subscriptions": 7, "Travel": 7,
    }

    weighted_categories = []
    for cat in categories:
        weighted_categories.extend([cat] * weights.get(cat, 5))

    for i in range(count):
        category = random.choice(weighted_categories)
        merchants = MERCHANTS[category]
        merchant_name, min_amt, max_amt, note_template = random.choice(merchants)

        # Most expenses are normal; ~5% are anomalous (3-5× normal)
        is_anomaly = random.random() < 0.05
        if is_anomaly:
            amount = round(random.uniform(max_amt * 3, max_amt * 5), 2)
            notes = f"[ANOMALY] {note_template} — unusually high"
        else:
            amount = round(random.uniform(min_amt, max_amt), 2)
            notes = note_template

        # Add some tags
        tags = []
        if is_anomaly:
            tags.append("anomaly")
        if category in ("Subscriptions", "Bills"):
            tags.append("recurring")
        if random.random() < 0.2:
            tags.append("important")

        expenses.append({
            "amount": amount,
            "merchant": merchant_name,
            "date": random_date(90),
            "category": category,
            "notes": notes,
            "tags": tags,
            "isRecurring": category in ("Subscriptions",),
        })

    # Sort by date for nice output
    expenses.sort(key=lambda x: x["date"])
    return expenses


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  SmartSpend — Seed Data Generator")
    print(f"  API: {API_URL}")
    print(f"  User: {TEST_EMAIL}")
    print("=" * 60)

    # Authenticate
    print("\n🔐 Authenticating...")
    token = get_token()
    print("  ✅ Token obtained")

    # Set budgets
    print(f"\n📊 Setting {len(BUDGETS)} budgets...")
    for b in BUDGETS:
        r = api_call("POST", "/budgets", b, token)
        status = "✅" if not r.get("_error") else "❌"
        print(f"  {status} {b['category']}: ₹{b['monthlyLimit']}/month "
              f"(alert at {b['alertThreshold']}%)")

    # Generate and create expenses
    print("\n💰 Generating 100 realistic expenses...")
    expenses = generate_expenses(100)

    created = 0
    anomalies = 0
    total_amount = 0

    for i, exp in enumerate(expenses):
        r = api_call("POST", "/expenses", exp, token)
        if r.get("expenseId"):
            created += 1
            total_amount += exp["amount"]
            if "[ANOMALY]" in exp.get("notes", ""):
                anomalies += 1

            # Progress indicator
            if (i + 1) % 10 == 0:
                print(f"  📝 Created {i + 1}/100 expenses...")

        else:
            print(f"  ⚠️  Failed #{i+1} ({exp['merchant']}): {str(r)[:80]}")

        # Small delay to avoid throttling
        if (i + 1) % 20 == 0:
            time.sleep(0.5)

    # Category breakdown
    cat_totals = {}
    for exp in expenses[:created]:
        cat = exp["category"]
        cat_totals[cat] = cat_totals.get(cat, 0) + exp["amount"]

    print(f"\n{'=' * 60}")
    print(f"  Seed Data Summary")
    print(f"{'=' * 60}")
    print(f"  Total created:    {created}/100 expenses")
    print(f"  Total amount:     ₹{total_amount:,.2f}")
    print(f"  Anomalies:        {anomalies}")
    print(f"  Date range:       {expenses[0]['date']} → {expenses[-1]['date']}")
    print(f"\n  Category breakdown:")
    for cat, amt in sorted(cat_totals.items(), key=lambda x: -x[1]):
        print(f"    {cat:20s}  ₹{amt:>10,.2f}")

    print(f"\n✅ Seed data loaded successfully!")
    print(f"   Login to the dashboard to see the data.\n")


if __name__ == "__main__":
    main()
