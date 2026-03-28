# SmartSpend — Serverless Personal Expense Tracker

**BCSE408L Cloud Computing Project — VIT**

SmartSpend is a **fully serverless** personal expense tracker deployed entirely on **AWS Free Tier**. It lets users track daily expenses via receipt photo uploads (auto-extracted with Amazon Textract OCR) or manual entry, with auto-categorization, anomaly detection, email alerts, analytics dashboards, and a **Cloud Resource Usage & Cost Tracker** module.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     USER BROWSER                         │
│     React 19 + Vite 8 + Tailwind CSS v4 + Recharts      │
│       (Hosted on S3 Static Website Hosting)              │
└────────────────────────┬────────────────────────────────┘
                         │ HTTPS
                         ▼
┌─────────────────────────────────────────────────────────┐
│           Amazon API Gateway (REST API)                  │
│   Cognito Authorizer — all routes require JWT token      │
│                                                          │
│   /expenses (CRUD)    /receipts/upload    /budgets        │
│   /expenses/export    /dashboard/stats                   │
│   /budgets/status     /resources/usage                   │
└─────┬──────┬──────┬──────┬──────┬──────┬────────────────┘
      │      │      │      │      │      │
      ▼      ▼      ▼      ▼      ▼      ▼
 ┌──────────────────────────────────────────────┐
 │          AWS Lambda Functions (Python 3.12)   │
 │   12 functions, each single-responsibility    │
 │   Shared CommonLayer (7 utility modules)      │
 ├──────────────────────────────────────────────┤
 │  create_expense    │  get_expenses            │
 │  update_expense    │  delete_expense           │
 │  upload_receipt    │  process_receipt (S3 evt)  │
 │  anomaly_detector  │  budget_check             │
 │  weekly_summary    │  export_csv               │
 │  get_resource_usage│  get_dashboard_stats      │
 └──────┬───────┬───────┬───────┬───────┬────────┘
        │       │       │       │       │
        ▼       ▼       ▼       ▼       ▼
   ┌────────┐ ┌───┐ ┌────────┐ ┌───┐ ┌──────────┐
   │DynamoDB│ │S3 │ │Textract│ │SNS│ │EventBridge│
   │4 tables│ │   │ │  OCR   │ │   │ │  (cron)   │
   └────────┘ └───┘ └────────┘ └───┘ └──────────┘
```

> See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed Mermaid diagrams and component descriptions.

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | React 19, Vite 8, Tailwind CSS v4 | SPA with dark mode, code splitting |
| **Charts** | Recharts | Pie, Area, Bar, Line charts |
| **Auth** | Amazon Cognito + JWT | Secure user authentication |
| **API** | API Gateway (REST) | HTTPS endpoints with CORS |
| **Compute** | AWS Lambda (Python 3.12) | 12 serverless functions |
| **Database** | DynamoDB (4 tables) | NoSQL, on-demand billing |
| **Storage** | Amazon S3 | Receipt images + frontend hosting |
| **AI/ML** | Amazon Textract | Receipt OCR (AnalyzeExpense) |
| **Notifications** | Amazon SNS | Email alerts (anomaly, budget) |
| **Scheduling** | EventBridge | Weekly summary cron job |
| **IaC** | AWS SAM | Infrastructure as Code |

## AWS Services — Free Tier Usage

| Service | Free Tier Limit | Our Usage | Cost |
|---------|----------------|-----------|------|
| Lambda | 1M requests/month | ~500 | **$0.00** |
| API Gateway | 1M calls/month | ~500 | **$0.00** |
| DynamoDB | 25 RCU/WCU (on-demand) | Minimal | **$0.00** |
| S3 | 5GB storage, 20K GET | <100MB | **$0.00** |
| Textract | 1,000 pages/month | <50 | **$0.00** |
| Cognito | 50,000 MAU | 1-5 users | **$0.00** |
| SNS | 1,000 emails/month | <20 | **$0.00** |
| EventBridge | Free | 4/month | **$0.00** |
| **Total** | | | **$0.00** |

## Features

- **Receipt Upload + OCR** — Upload receipt photos, Textract extracts merchant/date/amount automatically
- **Manual Expense Entry** — Form-based entry with auto-categorization (rule-based keyword matching)
- **13 Categories** — Food, Transport, Shopping, Groceries, Bills, Health, Entertainment, Education, Travel, Subscriptions, Fuel, Rent, Other
- **Anomaly Detection** — Statistical alerts when spending exceeds 2.5× rolling 30-day average or 3× median
- **Budget Management** — Set monthly budgets per category with threshold alerts (80%, 100%)
- **Email Alerts** — SNS notifications for anomalies and budget breaches
- **Dashboard** — Spending stats, category pie chart, monthly trends, top merchants
- **Export CSV** — Download expenses for any date range
- **Dark Mode** — Toggle light/dark theme with system preference detection
- **Weekly Digest** — Automated Sunday email summary via EventBridge cron
- **Cloud Resource Tracker** — Real-time AWS usage monitoring with cost estimation and free tier progress bars
- **Mobile Responsive** — Full responsive design with sidebar navigation

## Quick Start

### Prerequisites
- AWS CLI v2 configured (`aws configure`)
- AWS SAM CLI (`sam --version`)
- Python 3.12, Node.js 18+, npm
- AWS account with Free Tier

### Deploy

```bash
# 1. Clone and deploy backend
git clone <repo-url> && cd SmartSpend
sam build && sam deploy --guided --stack-name smartspend

# 2. Note outputs: ApiUrl, UserPoolId, UserPoolClientId

# 3. Configure and deploy frontend
cd frontend
cp .env.example .env
# Edit .env with your API URL and Cognito IDs
npm install && npm run build
aws s3 sync dist/ s3://smartspend-frontend-<ACCOUNT_ID>-<REGION>/

# 4. Create test user
aws cognito-idp sign-up --client-id <CLIENT_ID> \
  --username you@email.com --password "YourPass123!" \
  --user-attributes Name=email,Value=you@email.com
aws cognito-idp admin-confirm-sign-up \
  --user-pool-id <POOL_ID> --username you@email.com

# 5. Load sample data (optional)
pip3 install boto3
python3 scripts/seed_data.py

# 6. Run E2E tests
python3 scripts/e2e_test.py
```

> See [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) for detailed step-by-step instructions.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/expenses` | Create expense |
| GET | `/expenses` | List/filter/search expenses |
| PUT | `/expenses/{id}` | Update expense |
| DELETE | `/expenses/{id}` | Delete expense |
| GET | `/expenses/export` | Export CSV |
| POST | `/receipts/upload` | Upload receipt for OCR |
| GET | `/dashboard/stats` | Dashboard statistics |
| GET/POST | `/budgets` | Get/set budgets |
| GET | `/budgets/status` | Budget vs spending status |
| GET | `/resources/usage` | AWS resource usage metrics |

> See [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md) for full request/response examples.

## Resource Usage Tracking

The **Cloud Resource Usage & Cost Tracker** is the faculty-graded module. Every Lambda function logs its AWS resource consumption:

- **Lambda** — Invocations, duration, GB-seconds
- **DynamoDB** — Read/write capacity units
- **S3** — GET/PUT/DELETE operations, storage bytes
- **Textract** — Pages processed
- **SNS** — Email notifications published
- **API Gateway** — API call count

All data is aggregated and displayed on the Resource Usage dashboard with:
- Service usage cards with real metrics
- Cost distribution donut chart
- Free tier progress bars (with color-coded warnings)
- Detailed cost estimation table
- Cumulative usage timeline

## Project Structure

```
SmartSpend/
├── template.yaml              # SAM template — all AWS resources
├── backend/
│   ├── layers/common/python/  # Shared Lambda layer
│   │   ├── db_utils.py        # DynamoDB CRUD helpers
│   │   ├── response_utils.py  # Standardized API responses
│   │   ├── auth_utils.py      # Cognito JWT parsing
│   │   ├── resource_tracker.py# AWS usage tracking
│   │   ├── categorizer.py     # Rule-based categorization
│   │   ├── anomaly_utils.py   # Anomaly detection + budget alerts
│   │   └── textract_parser.py # Textract response parser
│   ├── functions/             # 12 Lambda function handlers
│   │   ├── create_expense/
│   │   ├── get_expenses/
│   │   ├── update_expense/
│   │   ├── delete_expense/
│   │   ├── upload_receipt/
│   │   ├── process_receipt/
│   │   ├── budget_check/
│   │   ├── anomaly_detector/
│   │   ├── weekly_summary/
│   │   ├── export_csv/
│   │   ├── get_dashboard_stats/
│   │   └── get_resource_usage/
│   └── tests/                 # pytest unit tests
├── frontend/                  # React 19 + Vite 8 + Tailwind CSS v4
│   ├── src/
│   │   ├── components/        # Layout, Auth, Common components
│   │   ├── contexts/          # AuthContext, ThemeContext
│   │   ├── pages/             # 8 page components (lazy-loaded)
│   │   └── utils/             # api.js, format.js
│   └── .env                   # Environment variables (not committed)
├── scripts/
│   ├── e2e_test.py            # End-to-end test suite
│   ├── seed_data.py           # Sample data generator (100 expenses)
│   ├── deploy.sh              # Backend deployment script
│   └── cleanup.sh             # Resource cleanup script
└── docs/
    ├── API_DOCUMENTATION.md   # Full REST API docs
    ├── ARCHITECTURE.md        # System architecture with diagrams
    └── DEPLOYMENT_GUIDE.md    # Step-by-step deployment guide
```

## Development Phases

| Phase | Description | Status |
|-------|------------|--------|
| 1 | Project Scaffolding & Infrastructure (SAM, DynamoDB, S3, Cognito) | ✅ |
| 2 | Shared Lambda Layer & CRUD Functions | ✅ |
| 3 | Receipt Upload & Textract OCR Processing | ✅ |
| 4 | Anomaly Detection, Budget Alerts & Weekly Summary | ✅ |
| 5 | Bug Fixes — Alert spam, batch delete, pagination safety | ✅ |
| 6 | Full React Frontend — All pages, auth, dark mode, responsive | ✅ |
| 7 | Resource Usage Backend — Real API endpoint, Lambda audit | ✅ |
| 8 | E2E Testing, Seed Data, Documentation, Final Deploy | ✅ |

## Cost Analysis — What This Would Cost Outside Free Tier

With typical student usage (~500 API calls/month, ~50 expenses, ~10 receipts):

| Service | Monthly Usage | Monthly Cost |
|---------|-------------|-------------|
| Lambda | 500 invocations × 200ms | $0.0001 |
| API Gateway | 500 calls | $0.00175 |
| DynamoDB | ~2500 RCU, ~100 WCU | $0.39 |
| S3 | 50MB storage, 500 requests | $0.002 |
| Textract | 10 pages | $0.015 |
| SNS | 20 emails | $0.0004 |
| Cognito | 1 MAU | $0.00 |
| **Total** | | **~$0.41/month** |

With AWS Free Tier: **$0.00/month**

## License

Academic project — BCSE408L Cloud Computing, VIT Vellore.
