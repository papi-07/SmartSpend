# SmartSpend – Claude Code Master Prompt
## A Serverless Personal Expense Tracker on AWS (Free Tier)
### BCSE408L – Cloud Computing Project

---

> **HOW TO USE THIS PROMPT:**
> Feed this entire document to Claude Code at the start of your session. Work through each Phase sequentially. Do NOT start Phase N+1 until Phase N is fully verified. After each phase, run the validation checklist before proceeding.

---

## 🧠 PROJECT OVERVIEW & CONTEXT

You are building **SmartSpend** — a fully serverless personal expense tracker deployed entirely on AWS Free Tier. This is a university cloud computing project (BCSE408L), so the code must be clean, well-commented, and architecturally sound enough to demonstrate understanding of serverless, ML integration, and cloud-native design patterns.

**The student (me) has ZERO infrastructure management responsibility** — everything runs on managed AWS services. Total AWS bill must be ₹0 (within free tier limits).

Before writing a single line of code, thoroughly read this entire prompt. Understand the full scope, then execute phase by phase.

---

## 📋 FULL FEATURE SET (Document + Extended)

### Core Features (from project proposal):
1. **Receipt Upload + OCR** — Upload receipt image → Amazon Textract extracts merchant, date, total
2. **Manual Expense Entry** — Form-based fallback when no receipt is available
3. **Auto-Categorization (ML)** — Scikit-learn model classifies expenses into categories
4. **Anomaly Detection + Email Alerts** — SNS email when spending spikes beyond threshold
5. **Dashboard with Charts** — Chart.js pie/bar charts, monthly totals, expense history table
6. **CRUD Operations** — View, edit, delete expenses stored in RDS

### Extended Features (additional imagination):
7. **Budget Goals Module** — User sets monthly budget per category; visual progress bars show burn rate
8. **Recurring Expense Detection** — System auto-identifies expenses that repeat monthly (rent, subscriptions)
9. **Export to CSV** — Download full expense history as CSV from the dashboard
10. **Multi-category Spending Heatmap** — Weekly heatmap grid showing high-spend days
11. **Smart Insights Panel** — Auto-generated text summaries like "You spent 40% more on Food this week vs last week"
12. **Search & Filter** — Filter expenses by date range, category, amount range
13. **Dark Mode Toggle** — Frontend dark/light mode persisted in localStorage

### 🆕 Resource Usage & Billing Tracker Module (Mandatory — Faculty Requirement):
14. **AWS Resource Monitor** — A dedicated module that tracks and displays actual AWS resource consumption:
    - Lambda invocation count, duration (ms), memory used per function
    - S3 storage used (bytes), GET/PUT request counts
    - RDS connection count, storage used
    - API Gateway request count
    - Textract pages analyzed (free tier: 1000 pages/month)
    - SNS notifications sent
15. **Free Tier Usage Dashboard** — Visual gauge charts showing % of free tier consumed for each service
16. **Simulated Bill Calculator** — Shows what the bill WOULD be if free tier didn't apply (for educational demonstration)
17. **Usage Logs Table** — Every Lambda invocation logs its own resource consumption to a DynamoDB table (free tier: 25GB) which feeds the billing dashboard

---

## 🏗️ COMPLETE ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER BROWSER                             │
│   React SPA (hosted on S3 Static Website)                      │
│   Pages: Dashboard | Add Expense | Budget Goals |              │
│          Resource Monitor | Search & Filter                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│              Amazon API Gateway (REST API)                       │
│  /expenses   /receipts   /budgets   /analytics   /resources     │
└────┬──────────┬──────────┬──────────┬────────────┬──────────────┘
     │          │          │          │            │
     ▼          ▼          ▼          ▼            ▼
┌─────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────────┐
│ Lambda  │ │Lambda  │ │Lambda  │ │Lambda  │ │   Lambda     │
│ CRUD    │ │Receipt │ │Budget  │ │Analytics│ │  Resource    │
│ Handler │ │Handler │ │Handler │ │Handler │ │  Monitor     │
└────┬────┘ └───┬────┘ └───┬────┘ └────────┘ └──────┬───────┘
     │          │          │                         │
     ▼          │          ▼                         ▼
┌─────────┐     │     ┌─────────┐              ┌──────────┐
│   RDS   │     │     │   RDS   │              │DynamoDB  │
│(MySQL)  │     │     │(MySQL)  │              │Usage Logs│
└─────────┘     │     └─────────┘              └──────────┘
                │
        ┌───────┼───────┐
        ▼       ▼       ▼
   ┌─────────┐ ┌──────────┐ ┌─────┐
   │   S3    │ │Textract  │ │ SNS │
   │Receipts │ │  OCR     │ │Email│
   └─────────┘ └──────────┘ └─────┘
```

---

## ☁️ AWS SERVICES & FREE TIER LIMITS (MUST RESPECT)

| Service | What We Use | Free Tier Limit | Hard Limit Strategy |
|---|---|---|---|
| **AWS Lambda** | All backend logic | 1M requests/month, 400,000 GB-seconds | Warn in Resource Monitor when >80% |
| **API Gateway** | REST endpoints | 1M calls/month (12 months) | Log every call |
| **S3** | Receipt images + static site | 5GB storage, 20K GET, 2K PUT/month | Compress images before upload |
| **RDS (MySQL)** | Expense data | db.t3.micro, 20GB, 750 hrs/month | Single-AZ, stop when not in use |
| **Amazon Textract** | Receipt OCR | 1000 pages/month (12 months) | Track in DynamoDB, warn at 800 |
| **Amazon SNS** | Email alerts | 1000 email notifications/month | Throttle to 1 per hour per user |
| **DynamoDB** | Resource usage logs | 25GB storage, 25 RCU/WCU | TTL = 90 days on log entries |
| **CloudWatch** | Metrics collection | 10 custom metrics, 5GB logs | Pull metrics via SDK in Lambda |

---

## 📁 REPOSITORY STRUCTURE

Before writing any code, create this exact folder structure:

```
smartspend/
├── README.md
├── .env.example
├── .gitignore
├── infrastructure/
│   ├── setup.md              ← Manual AWS setup instructions
│   └── schema.sql            ← RDS database schema
├── backend/
│   ├── requirements.txt
│   ├── shared/
│   │   ├── db.py             ← RDS connection helper
│   │   ├── usage_tracker.py  ← Resource usage logging utility
│   │   └── categorizer/
│   │       ├── train_model.py
│   │       ├── model.pkl     ← Pre-trained Scikit-learn model
│   │       └── training_data.csv
│   └── lambdas/
│       ├── expense_crud/
│       │   └── handler.py
│       ├── receipt_processor/
│       │   └── handler.py
│       ├── budget_manager/
│       │   └── handler.py
│       ├── analytics_engine/
│       │   └── handler.py
│       └── resource_monitor/
│           └── handler.py
├── frontend/
│   ├── index.html
│   ├── css/
│   │   └── styles.css
│   ├── js/
│   │   ├── app.js            ← Main router/state
│   │   ├── api.js            ← All fetch() calls to API Gateway
│   │   ├── dashboard.js
│   │   ├── addExpense.js
│   │   ├── budgets.js
│   │   ├── resourceMonitor.js
│   │   └── charts.js
│   └── assets/
│       └── logo.svg
└── tests/
    ├── test_crud.py
    ├── test_categorizer.py
    ├── test_receipt_processor.py
    └── test_resource_monitor.py
```

---

## 🗄️ DATABASE SCHEMA

Design and create all tables before writing Lambda code. Use MySQL on RDS.

```sql
-- infrastructure/schema.sql

CREATE DATABASE IF NOT EXISTS smartspend;
USE smartspend;

-- Core expense table
CREATE TABLE expenses (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     VARCHAR(50)    NOT NULL DEFAULT 'default_user',
    merchant    VARCHAR(255),
    amount      DECIMAL(10, 2) NOT NULL,
    category    VARCHAR(100)   NOT NULL,
    date        DATE           NOT NULL,
    note        TEXT,
    receipt_url VARCHAR(500),
    is_recurring BOOLEAN       DEFAULT FALSE,
    created_at  TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_date (user_id, date),
    INDEX idx_category (category)
);

-- Budget goals table
CREATE TABLE budgets (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     VARCHAR(50)    NOT NULL DEFAULT 'default_user',
    category    VARCHAR(100)   NOT NULL,
    monthly_limit DECIMAL(10, 2) NOT NULL,
    month       VARCHAR(7)     NOT NULL,  -- Format: YYYY-MM
    created_at  TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_budget (user_id, category, month)
);

-- Anomaly detection history
CREATE TABLE anomaly_log (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     VARCHAR(50)    NOT NULL DEFAULT 'default_user',
    category    VARCHAR(100)   NOT NULL,
    amount      DECIMAL(10, 2) NOT NULL,
    average     DECIMAL(10, 2) NOT NULL,
    triggered_at TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);
```

For DynamoDB (resource usage logs) — define the table schema in code:
```
Table: smartspend-usage-logs
  PK: service (String)     ← e.g., "lambda", "s3", "textract"
  SK: timestamp (String)   ← ISO 8601
  Attributes: function_name, invocations, duration_ms, memory_mb, request_count, storage_bytes
  TTL attribute: expires_at (Unix epoch, 90 days from now)
```

---

## 🐍 BACKEND SPECIFICATIONS

### Shared Utility: `shared/usage_tracker.py`
Every Lambda function MUST call this at the start and end of execution. It must:
- Accept: service name, function name, start time, memory allocated, additional metadata
- Calculate: execution duration, memory used estimate
- Write a log entry to DynamoDB `smartspend-usage-logs` table
- Be completely non-blocking (use try/except so it never breaks the main function)
- Increment a per-service invocation counter stored in DynamoDB

```python
# Interface contract:
import usage_tracker

tracker = usage_tracker.start("lambda", "expense_crud")
# ... main function logic ...
tracker.finish(extra={"records_affected": 3})
```

### Shared Utility: `shared/db.py`
- Use PyMySQL for RDS connections
- Implement connection pooling pattern for Lambda (reuse connection across warm invocations)
- Wrap all queries in try/except with proper rollback on failure
- Log all slow queries (>100ms) to CloudWatch

### Lambda 1: `expense_crud/handler.py`
Handle all CRUD operations on the `expenses` table.

**Routes it handles:**
- `GET /expenses` → list all expenses for a user (with optional filters: ?category=Food&from=2025-01-01&to=2025-12-31&search=swiggy&min_amount=100&max_amount=1000)
- `POST /expenses` → create new expense (manual entry)
- `PUT /expenses/{id}` → update expense
- `DELETE /expenses/{id}` → delete expense
- `GET /expenses/export` → return CSV of all expenses

**Categorization:** On every POST/PUT, call the Scikit-learn model from `shared/categorizer/` to auto-categorize.

**Anomaly Check:** After saving, calculate user's average for that category over last 30 days. If new expense > 3× average AND > ₹200 minimum threshold, publish to SNS topic.

**Recurring Detection:** If the same merchant appears 2+ times in previous months on similar dates (±3 days), mark `is_recurring = TRUE`.

**Response format (always):**
```json
{
  "success": true,
  "data": {...},
  "meta": {
    "execution_time_ms": 45,
    "lambda_request_id": "abc-123"
  }
}
```

### Lambda 2: `receipt_processor/handler.py`
**Route:** `POST /receipts/upload`

**Flow:**
1. Accept base64-encoded image from frontend
2. Decode and upload to S3 bucket `smartspend-receipts/YYYY/MM/DD/{uuid}.jpg`
3. Call `textract.analyze_expense()` on the S3 object
4. Parse Textract response: extract `VENDOR`, `INVOICE_RECEIPT_DATE`, `TOTAL`
5. Increment Textract usage counter in DynamoDB
6. Check if Textract usage > 800 this month → add a warning in response
7. Return extracted data to frontend (merchant, date, amount)
8. Frontend then calls `POST /expenses` with this pre-filled data

**Error handling:**
- Image too large (>5MB): return 400 with clear message
- Textract confidence <60%: return extracted data with `"low_confidence": true` flag
- Non-receipt image: return helpful error with suggestion to use manual entry

### Lambda 3: `budget_manager/handler.py`
**Routes:**
- `GET /budgets?month=2025-06` → get all budget goals for a month with current spend
- `POST /budgets` → create/update a budget goal
- `DELETE /budgets/{id}` → remove a budget goal
- `GET /budgets/summary` → return all categories with limit, spent, remaining, % used

**Logic:** Join budgets table with expenses table to calculate current spend vs limit in real time.

### Lambda 4: `analytics_engine/handler.py`
**Routes:**
- `GET /analytics/monthly?months=6` → monthly totals for last N months
- `GET /analytics/categories?month=2025-06` → category breakdown for a month
- `GET /analytics/heatmap?month=2025-06` → daily spend amounts (7×5 grid for weekly heatmap)
- `GET /analytics/insights` → auto-generated text insights array
- `GET /analytics/recurring` → list of detected recurring expenses

**Insights logic (hardcode these patterns):**
- "You spent X% more on [category] this week vs last week"
- "Your highest spend day was [weekday]"
- "You have [N] recurring expenses totaling ₹[amount]/month"
- "You're on track to exceed your [category] budget by ₹[amount]"
- "No receipt uploaded for [N] expenses — consider reviewing them"

### Lambda 5: `resource_monitor/handler.py`
**Routes:**
- `GET /resources/usage` → aggregated usage stats per service
- `GET /resources/freetier` → % of free tier consumed per service
- `GET /resources/bill` → simulated bill if free tier didn't apply
- `GET /resources/logs?service=lambda&limit=50` → raw usage log entries from DynamoDB

**What it does:**
1. Pull CloudWatch metrics via boto3 SDK:
   - Lambda: `Invocations`, `Duration`, `Errors` per function (last 30 days)
   - API Gateway: `Count` metric (last 30 days)
2. Pull from DynamoDB usage-logs table for S3 and Textract counts (since CloudWatch doesn't easily give those for free tier)
3. Calculate free tier % for each service
4. Calculate simulated bill using AWS public pricing:
   - Lambda: $0.0000166667 per GB-second + $0.20 per 1M requests (after free tier)
   - API Gateway: $3.50 per million requests
   - S3: $0.023/GB storage + $0.0004/1000 PUT + $0.00004/1000 GET
   - Textract: $1.50 per 1000 pages (AnalyzeExpense)
   - SNS: $2.00 per 100,000 email notifications
   - DynamoDB: $0.25/GB-month + $0.00013/RCU + $0.00065/WCU

**Response structure:**
```json
{
  "services": {
    "lambda": {
      "invocations": 1240,
      "free_tier_limit": 1000000,
      "percent_used": 0.12,
      "total_duration_gb_seconds": 18.4,
      "simulated_cost_usd": 0.00
    },
    "textract": {
      "pages_analyzed": 23,
      "free_tier_limit": 1000,
      "percent_used": 2.3,
      "simulated_cost_usd": 0.00,
      "warning": null
    }
  },
  "total_simulated_bill_usd": 0.00,
  "total_simulated_bill_inr": 0.00,
  "generated_at": "2025-06-15T10:30:00Z"
}
```

---

## 🤖 ML MODEL: EXPENSE CATEGORIZER

### Training Data (`shared/categorizer/training_data.csv`)
Create a CSV with at least 150 rows mapping merchant names to categories. Include:

**Categories:** Food, Transport, Shopping, Utilities, Entertainment, Healthcare, Education, Travel, Personal Care, Others

**Sample rows (create 15+ per category):**
```
merchant,category
Swiggy,Food
Zomato,Food
McDonald's,Food
Domino's,Food
Starbucks,Food
Ola,Transport
Uber,Transport
Rapido,Transport
IRCTC,Transport
IndiGo,Travel
Flipkart,Shopping
Amazon,Shopping
Myntra,Shopping
Reliance Digital,Shopping
Netflix,Entertainment
Spotify,Entertainment
BookMyShow,Entertainment
PVR Cinemas,Entertainment
Airtel,Utilities
Jio,Utilities
TNEB,Utilities
Apollo Pharmacy,Healthcare
MedPlus,Healthcare
Udemy,Education
Coursera,Education
Decathlon,Personal Care
Nykaa,Personal Care
```

### Model Training (`shared/categorizer/train_model.py`)
```python
# Use TF-IDF vectorizer on merchant names + Random Forest classifier
# Pipeline: TfidfVectorizer(ngram_range=(1,2), lowercase=True) → RandomForestClassifier(n_estimators=100)
# Add fuzzy matching fallback using difflib for unknown merchants
# Save as model.pkl using joblib
# Print classification report and confusion matrix
# Target accuracy: >85% on test split
```

The trained `model.pkl` must be checked into the repo so Lambda can load it without retraining.

---

## 🎨 FRONTEND SPECIFICATIONS

### Technology: Vanilla HTML/CSS/JavaScript (NO frameworks — keeps it simple and S3-hostable)

### Pages / Views (Single Page Application with hash routing):
1. `#/dashboard` — Main view (default)
2. `#/add` — Add expense (manual + receipt upload)
3. `#/budgets` — Budget goals manager
4. `#/analytics` — Detailed analytics view
5. `#/resources` — Resource usage & billing dashboard (NEW)
6. `#/search` — Search & filter expenses

### `js/api.js` — Centralized API Client
All fetch calls go here. Never call fetch() directly from other JS files.
- Base URL read from `window.API_BASE_URL` (set in a `<script>` tag in index.html)
- Every request automatically adds `user_id: 'default_user'` header
- Centralized error handling — toast notification on failure
- Loading spinner management

### Dashboard Page (`#/dashboard`)
Must show:
- KPI cards: Total this month | Highest category | Expenses logged today | Budget health (red/green)
- Doughnut chart: Category-wise spending (Chart.js)
- Bar chart: Last 6 months spending
- Recent expenses table (last 10): merchant, amount, category badge, date, receipt icon if available, edit/delete buttons
- Weekly heatmap (CSS grid, no library): 7 columns × 5 rows, color intensity = spend amount
- Smart Insights panel: 3–5 auto-generated insight cards with icons
- Export CSV button

### Add Expense Page (`#/add`)
Two tabs: "Upload Receipt" | "Manual Entry"

**Receipt Upload tab:**
- Drag-and-drop image area + file picker
- Image preview before upload
- Loading state while Textract processes (animated spinner + "Reading your receipt…" text)
- Pre-filled form after OCR with ability to edit fields
- Confidence warning badge if Textract confidence <60%
- Textract usage indicator: "X/1000 free scans used this month"

**Manual Entry tab:**
- Fields: Merchant Name | Amount (₹) | Date | Category (dropdown) | Note (optional)
- "Auto-categorize" button that calls the ML model
- Submit button with loading state

### Budget Goals Page (`#/budgets`)
- For each category: horizontal progress bar (green→yellow→red based on % used)
- Shows: Budget limit | Amount spent | Remaining | % used
- Edit budget limit inline
- Add new budget goal form

### Resource Monitor Page (`#/resources`) — Faculty Requirement
This is the most important page for the project grade. Make it look professional.

**Layout:**
- Header: "AWS Resource Dashboard — Free Tier Monitor"
- Service cards (one per AWS service used):
  - Service icon/badge
  - Circular gauge chart showing % of free tier used
  - Current usage vs limit
  - Color: Green (<50%), Yellow (50–80%), Red (>80%)
- "Simulated Monthly Bill" card:
  - Table: Service | Usage | Free Tier | Overage | Cost (USD) | Cost (INR)
  - Total row at bottom: "₹0.00 (100% within Free Tier)" shown in green
  - Note: "Prices calculated using AWS public pricing as of 2025"
- Usage Logs table:
  - Recent Lambda invocations: function name, timestamp, duration, memory
  - Paginated (show 20 at a time)
- Auto-refresh toggle (refresh every 30 seconds)

### Dark Mode
- CSS custom properties (variables) for all colors
- Toggle button in navbar
- State persisted in `localStorage`
- Smooth transition: `transition: background-color 0.3s ease`

---

## 🧪 TESTING REQUIREMENTS

After each phase, run automated tests before proceeding.

### `tests/test_crud.py`
Test all CRUD Lambda handler functions with mock boto3/PyMySQL. Cover:
- Create expense → returns 201 with correct structure
- Create expense with missing required fields → returns 400
- Get expenses with various filter combinations
- Update expense → category re-runs through ML model
- Delete expense → confirm removed
- Export → valid CSV format

### `tests/test_categorizer.py`
- Known merchants return correct category (test 20 merchants)
- Unknown merchant returns "Others" (not an error)
- Model loads from `model.pkl` without error
- Prediction time <50ms per merchant

### `tests/test_receipt_processor.py`
- Valid receipt image → correctly parses Textract mock response
- Confidence <60% → sets low_confidence flag
- Textract usage count increments in DynamoDB
- S3 upload path follows correct format `YYYY/MM/DD/{uuid}.jpg`

### `tests/test_resource_monitor.py`
- All 5 service metrics return non-null values
- Free tier % is between 0–100
- Simulated bill for 0 usage returns $0.00
- DynamoDB log entries have correct TTL

Use `pytest` with `unittest.mock` for all AWS SDK calls. Coverage target: >80%.

---

## 📦 DEPLOYMENT PACKAGE STRUCTURE

Each Lambda function must be deployable as a ZIP. Create a `build.sh` script:

```bash
#!/bin/bash
# build.sh — creates deployment zips for each Lambda

mkdir -p dist

build_lambda() {
  FUNC=$1
  echo "Building $FUNC..."
  rm -rf /tmp/lambda_build
  mkdir -p /tmp/lambda_build
  pip install -r backend/requirements.txt -t /tmp/lambda_build/ --quiet
  cp -r backend/shared /tmp/lambda_build/
  cp -r backend/lambdas/$FUNC/handler.py /tmp/lambda_build/
  cd /tmp/lambda_build && zip -r9 /path/to/smartspend/dist/${FUNC}.zip . --quiet
  cd - > /dev/null
  echo "  → dist/${FUNC}.zip created"
}

build_lambda expense_crud
build_lambda receipt_processor
build_lambda budget_manager
build_lambda analytics_engine
build_lambda resource_monitor

echo "All Lambda packages built successfully."
```

### `backend/requirements.txt`
```
pymysql==1.1.0
boto3==1.34.0
scikit-learn==1.4.0
joblib==1.3.2
Pillow==10.2.0
```

---

## ⚙️ ENVIRONMENT VARIABLES (for all Lambdas)

```
DB_HOST         = <RDS endpoint>
DB_NAME         = smartspend
DB_USER         = admin
DB_PASSWORD     = <password>
S3_RECEIPTS_BUCKET = smartspend-receipts-<account-id>
SNS_TOPIC_ARN   = <SNS topic ARN>
DYNAMODB_USAGE_TABLE = smartspend-usage-logs
TEXTRACT_MONTHLY_LIMIT = 1000
ALERT_EMAIL     = <user's email>
```

Never hardcode these — always use `os.environ.get()` with a safe default.

---

## 🚀 PHASE-BY-PHASE DEVELOPMENT PLAN

---

### ✅ PHASE 0: Repository & Documentation Setup
**Goal:** Clean, organized repo before any code is written.

**Tasks:**
1. Create the full folder structure exactly as specified above
2. Create `README.md` with:
   - Project overview, architecture diagram (ASCII art)
   - Setup instructions (Prerequisites, AWS services to create, env vars)
   - How to run locally (mock mode), how to deploy
   - Phase-wise development log
3. Create `.gitignore` (exclude: `*.pyc`, `__pycache__`, `.env`, `dist/`, `model.pkl` can stay)
4. Create `.env.example` with all required environment variables (empty values)
5. Create `infrastructure/setup.md` with step-by-step AWS Console instructions:
   - Create S3 bucket (receipts + static site — two separate buckets)
   - Create RDS MySQL instance (db.t3.micro, enable free tier, disable Multi-AZ)
   - Create DynamoDB table with correct schema and TTL enabled
   - Create SNS topic + email subscription
   - Create API Gateway (REST API, not HTTP API — for free tier compatibility)
   - Create IAM role for Lambda with permissions: S3, Textract, RDS, DynamoDB, SNS, CloudWatch
6. Create `infrastructure/schema.sql` with all tables as specified

**Verification Checklist Phase 0:**
- [ ] All folders exist
- [ ] README.md has all sections
- [ ] setup.md has complete AWS console steps
- [ ] schema.sql runs without error in MySQL
- [ ] .env.example has all required variables
- [ ] `tree smartspend/` output matches the structure spec

---

### ✅ PHASE 1: ML Model Training & Validation
**Goal:** Working `model.pkl` that accurately categorizes expenses.

**Tasks:**
1. Create `training_data.csv` with 150+ merchant-category mappings (10 categories, 15+ per category)
2. Write `train_model.py`:
   - Load CSV
   - Train TF-IDF + Random Forest pipeline
   - Print classification report (must show >80% accuracy)
   - Save `model.pkl` with joblib
3. Write a wrapper function `predict_category(merchant_name: str) -> str` that:
   - Loads model (cached in module scope for Lambda warmth)
   - Falls back to "Others" for any exception
   - Returns category string

**Run and validate locally:**
```bash
cd backend/shared/categorizer
python train_model.py
# Expected output: Classification Report with >80% accuracy
python -c "from categorizer import predict_category; print(predict_category('Swiggy'))"
# Expected: Food
```

4. Write `tests/test_categorizer.py` and run `pytest tests/test_categorizer.py -v`
5. All tests must pass before Phase 2

**Verification Checklist Phase 1:**
- [ ] `model.pkl` exists in `shared/categorizer/`
- [ ] Accuracy >80% printed in training output
- [ ] `predict_category("Swiggy")` returns `"Food"`
- [ ] `predict_category("Unknown Merchant XYZ")` returns `"Others"` (not an exception)
- [ ] All tests in `test_categorizer.py` pass

---

### ✅ PHASE 2: Database Layer & Shared Utilities
**Goal:** `db.py` and `usage_tracker.py` working with mocked AWS.

**Tasks:**
1. Write `shared/db.py`:
   - Connection function with environment variable config
   - `execute_query(sql, params, fetch=True/False)` helper
   - Proper connection reuse across warm Lambda invocations (store connection in module-level variable, reconnect on failure)
   - All queries parameterized (no f-string SQL — SQL injection prevention)
2. Write `shared/usage_tracker.py`:
   - `UsageTracker` class with `start(service, function_name)` and `finish(extra={})` methods
   - Writes to DynamoDB `smartspend-usage-logs` on `finish()`
   - Calculates `duration_ms = (datetime.now() - start_time).total_seconds() * 1000`
   - TTL = current Unix time + (90 * 24 * 3600)
   - Catches ALL exceptions silently (never breaks caller)
3. Write a local mock test:
```python
# In shared/usage_tracker.py, add a __main__ block:
if __name__ == "__main__":
    # Uses mock DynamoDB or prints to stdout
    tracker = UsageTracker.start("test", "test_function")
    import time; time.sleep(0.1)
    tracker.finish(extra={"test_key": "test_value"})
    print("UsageTracker smoke test passed")
```

**Verification Checklist Phase 2:**
- [ ] `db.py` connects to RDS when env vars set (or mocks cleanly)
- [ ] `execute_query()` returns list of dicts for SELECT
- [ ] `execute_query()` returns `None` for INSERT/UPDATE/DELETE
- [ ] `usage_tracker.py` smoke test prints "passed" without exceptions
- [ ] No hardcoded credentials anywhere

---

### ✅ PHASE 3: Core CRUD Lambda
**Goal:** Working expense create/read/update/delete with categorization and anomaly detection.

**Tasks:**
1. Write `lambdas/expense_crud/handler.py` — implement `lambda_handler(event, context)`:
   - Parse HTTP method and path from `event`
   - Route to correct internal function: `handle_list`, `handle_create`, `handle_update`, `handle_delete`, `handle_export`
   - Wrap every response with `{"success": true/false, "data": ..., "meta": {...}}`
   - CORS headers on every response: `Access-Control-Allow-Origin: *`
2. Implement `handle_create(body)`:
   - Validate required fields: `amount`, `date` (return 400 if missing)
   - Call `predict_category(merchant)` from model
   - Run anomaly check: query average amount for category in last 30 days, compare with 3× threshold
   - If anomaly: publish SNS message with details
   - Detect recurring: check if merchant appeared in 2+ previous months
   - Insert into RDS, return created expense
3. Implement `handle_list(query_params)`:
   - Build dynamic WHERE clause from optional filters (category, from_date, to_date, search, min_amount, max_amount)
   - Return paginated results (default 50, max 100)
4. Implement `handle_export(user_id)`:
   - Query all expenses
   - Return CSV string with proper Content-Type: text/csv header
5. Wrap entire handler with `UsageTracker`
6. Write `tests/test_crud.py` using `unittest.mock` to mock PyMySQL and boto3
7. Run all tests: `pytest tests/test_crud.py -v`

**Verification Checklist Phase 3:**
- [ ] `POST /expenses` with valid body returns 201 and expense object
- [ ] `POST /expenses` with missing `amount` returns 400
- [ ] `GET /expenses?category=Food` filters correctly
- [ ] `GET /expenses/export` returns valid CSV
- [ ] SNS publish is called when anomaly detected (verify in test mock)
- [ ] `is_recurring` is set correctly for repeat merchants
- [ ] All 10+ tests pass in `test_crud.py`

---

### ✅ PHASE 4: Receipt Processor Lambda
**Goal:** Working S3 upload + Textract OCR pipeline.

**Tasks:**
1. Write `lambdas/receipt_processor/handler.py`:
   - Accept `multipart/form-data` or base64-encoded body from API Gateway
   - Validate file type (accept only JPEG, PNG, PDF) and size (<5MB)
   - Generate unique S3 key: `receipts/YYYY/MM/DD/{uuid}.{ext}`
   - Upload to S3 with `ContentType` set correctly
   - Call `textract.analyze_expense(Document={'S3Object': {'Bucket': ..., 'Name': ...}})`
   - Parse response: extract `VENDOR`, `INVOICE_RECEIPT_DATE`, `TOTAL`
   - Extract confidence score from Textract response
   - Log Textract usage to DynamoDB
   - Return: `{merchant, date, amount, receipt_url, confidence, low_confidence: bool, textract_warning: str|null}`
2. Handle Textract failures gracefully (return partial data with warning)
3. Write `tests/test_receipt_processor.py` with a mock Textract response fixture
4. Run: `pytest tests/test_receipt_processor.py -v`

**Sample Textract mock response fixture** (create in tests/):
```python
MOCK_TEXTRACT_RESPONSE = {
    "ExpenseDocuments": [{
        "SummaryFields": [
            {"Type": {"Text": "VENDOR"}, "ValueDetection": {"Text": "Swiggy", "Confidence": 95.2}},
            {"Type": {"Text": "INVOICE_RECEIPT_DATE"}, "ValueDetection": {"Text": "2025-06-01", "Confidence": 88.1}},
            {"Type": {"Text": "TOTAL"}, "ValueDetection": {"Text": "349.00", "Confidence": 92.4}}
        ]
    }]
}
```

**Verification Checklist Phase 4:**
- [ ] Valid image → returns merchant, date, amount
- [ ] S3 key format is `receipts/YYYY/MM/DD/{uuid}.ext`
- [ ] Textract count increments in DynamoDB after each call
- [ ] Image >5MB returns 400 with clear message
- [ ] `low_confidence: true` when confidence <60%
- [ ] All tests pass

---

### ✅ PHASE 5: Budget Manager & Analytics Lambdas
**Goal:** Budget tracking with real-time spend calculation + analytics data.

**Tasks:**
1. Write `lambdas/budget_manager/handler.py`:
   - `GET /budgets/summary` joins budgets + expenses to compute spend vs limit
   - `POST /budgets` upserts a budget goal (INSERT … ON DUPLICATE KEY UPDATE)
   - Wrap with UsageTracker
2. Write `lambdas/analytics_engine/handler.py`:
   - `GET /analytics/monthly` → GROUP BY MONTH, last N months
   - `GET /analytics/categories` → GROUP BY category for a given month
   - `GET /analytics/heatmap` → daily totals for a month (return array of {date, amount})
   - `GET /analytics/insights` → compute and return 3–5 insight strings
   - `GET /analytics/recurring` → expenses with `is_recurring = TRUE`
   - Wrap with UsageTracker
3. Write unit tests for both lambdas

**Verification Checklist Phase 5:**
- [ ] Budget summary correctly shows 0 spent when no expenses exist
- [ ] Budget summary correctly aggregates expenses for the current month
- [ ] Monthly analytics returns correct number of months
- [ ] Heatmap returns 28–31 entries for any given month
- [ ] Insights array contains at least 3 items (even with empty data)
- [ ] All tests pass

---

### ✅ PHASE 6: Resource Monitor Lambda
**Goal:** Real-time AWS resource usage tracking and simulated billing.

**Tasks:**
1. Write `lambdas/resource_monitor/handler.py`:
   - `GET /resources/usage`:
     - Pull Lambda metrics from CloudWatch (`GetMetricStatistics`)
     - Pull API Gateway request count from CloudWatch
     - Pull Textract page count from DynamoDB usage-logs
     - Pull S3 object count + size from DynamoDB usage-logs (S3 doesn't have free CloudWatch metrics)
     - Aggregate and return
   - `GET /resources/freetier`:
     - Calculate % of free tier consumed for each service
     - Return traffic-light status: green/yellow/red
   - `GET /resources/bill`:
     - Apply AWS pricing formulas
     - Return per-service and total simulated cost in USD and INR (use fixed rate: 1 USD = 83 INR)
   - `GET /resources/logs`:
     - Query DynamoDB usage-logs table with pagination
2. Write `tests/test_resource_monitor.py` with mocked CloudWatch and DynamoDB responses
3. Run all tests

**Verification Checklist Phase 6:**
- [ ] All 4 routes respond without exceptions
- [ ] Free tier % is always 0–100 (clamp if needed)
- [ ] Simulated bill for 0 usage = $0.00
- [ ] DynamoDB logs returned are correctly formatted
- [ ] CloudWatch metric calls use correct namespace and metric names
- [ ] All tests pass

---

### ✅ PHASE 7: Frontend Development
**Goal:** Fully functional single-page application.

**Build order within this phase:**

**Step 7a: Base Layout & Routing**
1. `index.html` with navbar, main content area, footer
2. `css/styles.css` — CSS custom properties for light/dark theme, responsive grid
3. `js/app.js` — hash router: reads `window.location.hash`, loads correct page module
4. `js/api.js` — centralized API client class

**Step 7b: Dashboard Page**
1. KPI card row (4 cards)
2. Chart.js doughnut + bar charts
3. Weekly heatmap (pure CSS grid)
4. Recent expenses table with action buttons
5. Smart Insights panel

**Step 7c: Add Expense Page**
1. Tab switcher (Upload Receipt / Manual Entry)
2. Drag-and-drop zone with preview
3. Textract loading state
4. Pre-filled form from OCR result
5. Manual entry form with auto-categorize button

**Step 7d: Budgets Page**
1. Budget cards with animated progress bars
2. Inline editing
3. Add new budget form

**Step 7e: Resource Monitor Page** *(Most important for faculty demo)*
1. Service gauge cards (circular progress using SVG or CSS conic-gradient)
2. Simulated bill table with color-coded cost cells
3. Usage logs table with pagination
4. Auto-refresh toggle (30s interval)

**Step 7f: Search & Filter Page**
1. Filter sidebar: date range pickers, category checkboxes, amount range sliders
2. Results table with highlighting of search terms
3. Inline edit/delete

**Step 7g: Dark Mode & Polish**
1. Dark mode toggle in navbar
2. Toast notification system (success/error/warning)
3. Loading skeletons for data-fetching states
4. Responsive design (works on mobile)

**Verification Checklist Phase 7:**
- [ ] App loads at `index.html` with no console errors
- [ ] All 6 pages render without crashes
- [ ] API calls use `window.API_BASE_URL` (not hardcoded)
- [ ] Charts render with mock data (test with `API_BASE_URL = null` and static test data)
- [ ] Dark mode toggles correctly and persists on page refresh
- [ ] Drag-and-drop works on Chrome and Firefox
- [ ] No broken UI on mobile screen (320px width minimum)

---

### ✅ PHASE 8: API Gateway Integration
**Goal:** Connect frontend to deployed Lambdas through API Gateway.

**Tasks:**
1. Create `infrastructure/api_gateway_config.json` documenting all routes:
```json
{
  "routes": [
    {"method": "GET",    "path": "/expenses",          "lambda": "expense_crud"},
    {"method": "POST",   "path": "/expenses",          "lambda": "expense_crud"},
    {"method": "PUT",    "path": "/expenses/{id}",     "lambda": "expense_crud"},
    {"method": "DELETE", "path": "/expenses/{id}",     "lambda": "expense_crud"},
    {"method": "GET",    "path": "/expenses/export",   "lambda": "expense_crud"},
    {"method": "POST",   "path": "/receipts/upload",   "lambda": "receipt_processor"},
    {"method": "GET",    "path": "/budgets",           "lambda": "budget_manager"},
    {"method": "POST",   "path": "/budgets",           "lambda": "budget_manager"},
    {"method": "GET",    "path": "/budgets/summary",   "lambda": "budget_manager"},
    {"method": "GET",    "path": "/analytics/monthly", "lambda": "analytics_engine"},
    {"method": "GET",    "path": "/analytics/categories", "lambda": "analytics_engine"},
    {"method": "GET",    "path": "/analytics/heatmap", "lambda": "analytics_engine"},
    {"method": "GET",    "path": "/analytics/insights","lambda": "analytics_engine"},
    {"method": "GET",    "path": "/resources/usage",   "lambda": "resource_monitor"},
    {"method": "GET",    "path": "/resources/freetier","lambda": "resource_monitor"},
    {"method": "GET",    "path": "/resources/bill",    "lambda": "resource_monitor"},
    {"method": "GET",    "path": "/resources/logs",    "lambda": "resource_monitor"}
  ]
}
```
2. Enable CORS on all API Gateway routes (Allow-Origin: *, Allow-Methods: GET,POST,PUT,DELETE,OPTIONS)
3. Create a preflight OPTIONS handler in each Lambda
4. Update `js/api.js` to use the real API Gateway URL
5. Test each endpoint manually using curl:
```bash
# Test suite — run these curl commands and verify 200 responses
curl -X GET "$API_URL/expenses"
curl -X POST "$API_URL/expenses" -H "Content-Type: application/json" -d '{"merchant":"Swiggy","amount":250,"date":"2025-06-01"}'
curl -X GET "$API_URL/resources/freetier"
```

**Verification Checklist Phase 8:**
- [ ] All 17 routes return non-500 responses
- [ ] CORS headers present on all responses
- [ ] Preflight OPTIONS returns 200
- [ ] Frontend can fetch expenses from live API
- [ ] No API keys or secrets in frontend JS

---

### ✅ PHASE 9: End-to-End Testing
**Goal:** Full smoke test of every user flow.

**Test Scenarios (run all manually and document results):**

| Scenario | Steps | Expected Result |
|---|---|---|
| Manual expense entry | Fill form → Submit | Expense appears in table, category auto-filled |
| Receipt upload | Upload JPG receipt → Submit | OCR extracts merchant/amount, expense saved |
| Anomaly alert | Add expense 4× category average | Email received via SNS |
| Budget tracking | Set budget ₹500 for Food → Add ₹400 expense | Progress bar shows 80%, yellow |
| CSV export | Click Export | File downloads with correct headers and data |
| Resource monitor | Open Resource page | All service cards show % and simulated bill |
| Dark mode | Toggle dark mode | All pages switch theme, persists on refresh |
| Filter | Search "Swiggy", filter Food category | Correct filtered results |

Create `tests/e2e_checklist.md` and fill it in with PASS/FAIL for each scenario.

---

### ✅ PHASE 10: Final Polish & Submission-Ready
**Goal:** Production-quality code, documentation, and demo-ready state.

**Tasks:**
1. **Code Review:**
   - Remove all `print()` debug statements (replace with CloudWatch logging: `import logging`)
   - Ensure every function has a docstring
   - Remove any hardcoded values, ensure all config comes from env vars

2. **README.md Final Update:**
   - Add deployment steps
   - Add screenshots section (placeholder)
   - Add "How the Resource Monitor Works" section explaining billing calculation methodology

3. **Demo Data Script** (`scripts/seed_demo_data.py`):
   - Insert 3 months of realistic expense data (50+ records)
   - Cover all 10 categories
   - Include at least 5 recurring expenses
   - Include 2 anomalous expenses that should trigger alerts
   - Run against live RDS to populate demo-ready state

4. **Project Report Section: Resource Usage Analysis** (`docs/resource_analysis.md`):
   - Capture actual screenshots of the Resource Monitor dashboard
   - Document actual AWS usage stats from the billing module
   - Explain each AWS service used and its free tier impact
   - Include the simulated bill table showing ₹0 cost

5. **Final Tests:**
   - Run full test suite: `pytest tests/ -v --tb=short`
   - All tests must pass
   - Generate coverage report: `pytest --cov=backend tests/`

---

## 🚨 CRITICAL CONSTRAINTS (NEVER VIOLATE)

1. **NEVER use `t2.medium` or any non-free-tier instance** — only `db.t3.micro` for RDS
2. **NEVER store secrets in code** — use environment variables always
3. **NEVER call `textract.analyze_document()` in a loop** — it depletes free tier fast; only on explicit user upload
4. **NEVER run RDS 24/7 during development** — stop the instance when not testing (AWS Console → Stop temporarily)
5. **ALWAYS set a CloudWatch billing alarm** at $1 (one dollar) in your AWS account before starting anything
6. **NEVER enable Multi-AZ on RDS** — it doubles the cost and kills free tier
7. **ALWAYS use `us-east-1` region** — all services are reliably in free tier here
8. **ALWAYS compress images** client-side before upload — use Canvas API to resize to max 1000px before base64 encoding
9. **ALWAYS add `TTL` to DynamoDB usage logs** — prevents storage cost creep
10. **NEVER create more than 1 API Gateway** — all routes go through one API

---

## 📊 SUCCESS METRICS FOR GRADING

Your project will be evaluated on:

| Criteria | Target | Where to Demo |
|---|---|---|
| Serverless Architecture | 5 Lambda functions deployed | AWS Console → Lambda |
| ML Integration | Textract OCR + Scikit-learn categorizer | Upload a receipt |
| Anomaly Detection | Email alert triggered | Show SNS email |
| Resource Monitor | All 6 services tracked | `/resources` page |
| Simulated Billing | $0 bill shown for all services | `/resources/bill` |
| Dashboard Visualization | 3+ chart types | `/dashboard` |
| Free Tier Compliance | $0 actual AWS bill | AWS Billing Dashboard |
| Code Quality | Tests passing, no hardcoded secrets | `pytest tests/` |

---

## 💬 FINAL INSTRUCTIONS TO CLAUDE CODE

1. **Work strictly phase by phase.** After completing each phase, ask me to verify before proceeding.
2. **For every file you create**, add a docstring/header comment explaining its purpose and how it fits into the architecture.
3. **For every Lambda handler**, include sample event JSON for local testing in a comment at the top of the file.
4. **When in doubt about a design decision**, choose the simpler option that stays within free tier.
5. **After Phase 3, 4, and 6** — run the test suite and show me the pytest output before continuing.
6. **The Resource Monitor (Phase 6 + Frontend Phase 7e) is the most important module** for the faculty demo — spend extra effort making it look polished and accurate.
7. **Do not hallucinate AWS service names or API signatures** — if unsure about a boto3 API call, look it up in the code comments and note the correct API reference URL.
8. **The simulated bill page must show ₹0** — this is the educational punchline of the entire project: "We used all these services for free."

Let's begin. Start with **Phase 0: Repository & Documentation Setup**.
