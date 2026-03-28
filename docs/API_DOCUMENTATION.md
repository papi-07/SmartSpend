# SmartSpend API Documentation

**Base URL:** `https://<api-id>.execute-api.<region>.amazonaws.com/prod/`
**Authentication:** All endpoints require a valid Cognito JWT token in the `Authorization: Bearer <token>` header.
**Content-Type:** `application/json`

---

## Expenses

### POST /expenses — Create Expense
Creates a new expense record. Auto-categorizes if category not provided.

**Request Body:**
```json
{
  "amount": 250.00,
  "merchant": "Swiggy",
  "date": "2026-03-15",
  "category": "Food",
  "notes": "Dinner order",
  "tags": ["delivery"],
  "isRecurring": false,
  "recurringFrequency": ""
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| amount | number | ✅ | Amount in rupees (positive) |
| merchant | string | ✅ | Merchant/vendor name |
| date | string | ✅ | Date in YYYY-MM-DD format |
| category | string | ❌ | Auto-detected if omitted |
| notes | string | ❌ | Optional notes |
| tags | string[] | ❌ | Optional tags |
| isRecurring | boolean | ❌ | Default: false |
| recurringFrequency | string | ❌ | "weekly", "monthly", etc. |

**Response (201):**
```json
{
  "expenseId": "a1b2c3d4-...",
  "amount": 250.00,
  "amountPaise": 25000,
  "merchant": "Swiggy",
  "category": "Food",
  "categoryConfidence": 0.95,
  "date": "2026-03-15",
  "notes": "Dinner order",
  "tags": ["delivery"],
  "source": "manual",
  "createdAt": "2026-03-15T10:30:00+00:00",
  "anomalyAlert": null,
  "budgetAlert": null
}
```

---

### GET /expenses — List Expenses
Retrieves expenses with optional filtering, search, and pagination.

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| startDate | string | Filter from date (YYYY-MM-DD) |
| endDate | string | Filter to date (YYYY-MM-DD) |
| category | string | Filter by category |
| search | string | Search merchant/notes |
| tags | string | Filter by tag |
| limit | int | Max results (default 50, max 100) |
| lastKey | string | Pagination token (base64) |

**Response (200):**
```json
{
  "expenses": [
    {
      "expenseId": "a1b2c3d4-...",
      "amount": 250.00,
      "merchant": "Swiggy",
      "category": "Food",
      "date": "2026-03-15",
      "receiptUrl": "https://s3-presigned-url..."
    }
  ],
  "count": 10,
  "totalCount": 45,
  "nextKey": "eyJ..."
}
```

---

### PUT /expenses/{expenseId} — Update Expense
Updates an existing expense. Only sends changed fields.

**Request Body:**
```json
{
  "amount": 300.00,
  "notes": "Updated notes"
}
```

**Response (200):** Updated expense object.

---

### DELETE /expenses/{expenseId} — Delete Expense
Deletes an expense and its associated receipt from S3 (if any).

**Response (200):**
```json
{
  "message": "Expense deleted successfully",
  "expenseId": "a1b2c3d4-..."
}
```

---

### GET /expenses/export — Export CSV
Exports expenses as a CSV file.

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| startDate | string | Start date (default: 30 days ago) |
| endDate | string | End date (default: today) |

**Response (200):** Binary CSV file (base64-encoded via API Gateway).

---

## Receipts

### POST /receipts/upload — Upload Receipt
Uploads a receipt image for OCR processing.

**Request Body:**
```json
{
  "image": "<base64-encoded image data>",
  "filename": "receipt.jpg",
  "contentType": "image/jpeg"
}
```

**Response (201):**
```json
{
  "receiptKey": "receipts/user-id/uuid.jpg",
  "receiptId": "uuid",
  "previewUrl": "https://s3-presigned-url...",
  "fileSize": 245760,
  "contentType": "image/jpeg",
  "message": "Receipt uploaded. OCR processing will begin automatically."
}
```

> **Note:** OCR processing is triggered automatically via S3 event. The expense will appear after Textract processes the receipt (usually 2-5 seconds).

---

## Dashboard

### GET /dashboard/stats — Dashboard Statistics
Returns aggregated spending stats for a given month.

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| month | string | Month in YYYY-MM format (default: current) |

**Response (200):**
```json
{
  "month": "2026-03",
  "totalSpent": 15250.00,
  "expenseCount": 42,
  "categoryBreakdown": [
    { "category": "Food", "amount": 5200.00, "count": 15 }
  ],
  "dailyTotals": [
    { "date": "2026-03-01", "amount": 450.00 }
  ],
  "topMerchants": [
    { "merchant": "Swiggy", "amount": 3200.00, "count": 8 }
  ],
  "comparisonWithLastMonth": {
    "currentMonth": 15250.00,
    "lastMonth": 12800.00,
    "changePercent": 19.1
  }
}
```

---

## Budgets

### POST /budgets — Set Budget
Sets or updates a monthly budget for a category.

**Request Body:**
```json
{
  "category": "Food",
  "monthlyLimit": 5000,
  "alertThreshold": 80
}
```

**Valid Categories:** Food, Transport, Shopping, Entertainment, Bills, Health, Education, Travel, Groceries, Fuel, Subscriptions, Rent, Other

**Response (201):**
```json
{
  "message": "Budget for Food set to ₹5,000.00/month",
  "category": "Food",
  "monthlyLimit": 5000,
  "alertThreshold": 80,
  "currentSpent": 3200.00,
  "percentUsed": 64.0,
  "alertSent": false
}
```

---

### GET /budgets — List Budgets
Returns all budget limits for the authenticated user.

**Response (200):**
```json
{
  "budgets": [
    {
      "category": "Food",
      "monthlyLimit": 5000,
      "alertThreshold": 80,
      "createdAt": "2026-03-01T...",
      "updatedAt": "2026-03-01T..."
    }
  ],
  "count": 3
}
```

---

### GET /budgets/status — Budget Status
Returns spending vs budget for the current month.

**Response (200):**
```json
{
  "budgets": [
    {
      "category": "Food",
      "monthlyLimit": 5000,
      "spent": 3200.00,
      "remaining": 1800.00,
      "percentUsed": 64.0,
      "status": "warning",
      "alertThreshold": 80
    }
  ],
  "month": "2026-03",
  "totalBudgeted": 15000,
  "totalSpent": 8500
}
```

**Status values:** `safe` (<60%), `warning` (60-90%), `exceeded` (90-100%), `over` (>100%)

---

## Resource Usage

### GET /resources/usage — AWS Resource Usage
Returns aggregated AWS resource consumption and cost estimates.

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| startDate | string | Start date (default: 30 days ago) |
| endDate | string | End date (default: today) |

**Response (200):**
```json
{
  "services": {
    "lambda": { "invocations": 320, "estimatedCost": 0.0006 },
    "dynamodb": { "readUnits": 2429, "writeUnits": 37, "estimatedCost": 0.34 },
    "s3": { "getRequests": 483, "putRequests": 3, "estimatedCost": 0.0002 },
    "textract": { "pagesProcessed": 3, "estimatedCost": 0.0045 },
    "sns": { "messagesPublished": 8, "estimatedCost": 0.0002 },
    "apiGateway": { "requests": 317, "estimatedCost": 0.0011 },
    "cognito": { "monthlyActiveUsers": 1, "estimatedCost": 0.0 }
  },
  "totalEstimatedCost": 0.35,
  "freeTierSavings": 11.69,
  "summary": {
    "totalEstimatedCostUsd": 0.35,
    "totalEstimatedCostInr": 29.05,
    "freeTierSavingsInr": 970.27
  },
  "byService": [ ... ],
  "dailyUsage": [ ... ]
}
```

---

## Error Responses

All errors follow this format:
```json
{
  "error": "Descriptive error message"
}
```

| Status Code | Meaning |
|------------|---------|
| 400 | Bad request — missing or invalid parameters |
| 401 | Unauthorized — missing or expired JWT token |
| 404 | Resource not found |
| 405 | Method not allowed |
| 500 | Internal server error |

---

## CORS

All responses include these headers:
```
Access-Control-Allow-Origin: *
Access-Control-Allow-Headers: Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token
Access-Control-Allow-Methods: GET,POST,PUT,DELETE,OPTIONS
```

OPTIONS preflight requests return 200 with empty body.
