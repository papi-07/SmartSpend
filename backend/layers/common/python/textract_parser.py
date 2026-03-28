"""
SmartSpend — Textract Response Parser (Shared Layer)
=====================================================
Parses Amazon Textract AnalyzeExpense API responses to extract:
  - merchant_name (from VENDOR_NAME)
  - total_amount (from TOTAL, handling ₹/Rs/INR formats)
  - date (from INVOICE_RECEIPT_DATE, handling multiple date formats)
  - line_items (individual items if available)
  - confidence (average confidence score)

Handles missing fields gracefully and flags low-confidence extractions.
"""

import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Confidence threshold — below this we flag for user review
LOW_CONFIDENCE_THRESHOLD = 0.70

# ─── Currency parsing ──────────────────────────────────────────────
# Handles: ₹150, Rs. 150, Rs150, 150.00, INR 150, Rs 1,500.50, ₹ 1,23,456.78
_CURRENCY_PATTERN = re.compile(
    r"(?:₹|Rs\.?|INR|USD|\$)?\s*"      # optional currency prefix
    r"([0-9]{1,2}(?:,[0-9]{2})*(?:,[0-9]{3})*"  # Indian/Western grouping
    r"(?:\.[0-9]{1,2})?|"               # decimal part
    r"[0-9]+(?:\.[0-9]{1,2})?)"         # plain number
)

# ─── Date parsing ──────────────────────────────────────────────────
_DATE_FORMATS = [
    "%Y-%m-%d",         # 2026-03-15
    "%d/%m/%Y",         # 15/03/2026
    "%d-%m-%Y",         # 15-03-2026
    "%m/%d/%Y",         # 03/15/2026
    "%d %b %Y",         # 15 Mar 2026
    "%d %B %Y",         # 15 March 2026
    "%b %d, %Y",        # Mar 15, 2026
    "%b %d %Y",         # Mar 15 2026
    "%B %d, %Y",        # March 15, 2026
    "%d.%m.%Y",         # 15.03.2026
    "%d/%m/%y",         # 15/03/26
    "%d-%m-%y",         # 15-03-26
]


def parse_currency(text):
    """
    Parse a currency string into a float amount.

    Handles: ₹150, Rs. 150, Rs150, 150.00, INR 150,
             Rs 1,500.50, ₹ 1,23,456.78

    Returns:
        float or None if unparseable.
    """
    if not text or not isinstance(text, str):
        return None

    text = text.strip()

    # Remove currency symbols/prefixes
    cleaned = re.sub(r"^(?:₹|Rs\.?\s*|INR\s*|USD\s*|\$\s*)", "", text).strip()

    # Remove commas (Indian/Western grouping)
    cleaned = cleaned.replace(",", "")

    # Remove trailing non-numeric (e.g., "/-" in "₹150/-")
    cleaned = re.sub(r"[^\d.]+$", "", cleaned)

    # Extract the number
    match = re.match(r"^(\d+(?:\.\d{1,2})?)$", cleaned)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass

    return None


def parse_date(text):
    """
    Parse a date string in various formats into ISO 8601 (YYYY-MM-DD).

    Returns:
        str (YYYY-MM-DD) or None if unparseable.
    """
    if not text or not isinstance(text, str):
        return None

    text = text.strip()

    # Try each known format
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            # Sanity check: year should be reasonable
            if 2000 <= dt.year <= 2099:
                return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Last resort: try to find a date-like pattern in the string
    date_match = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", text)
    if date_match:
        d, m, y = date_match.groups()
        if len(y) == 2:
            y = "20" + y
        try:
            dt = datetime(int(y), int(m), int(d))
            if 2000 <= dt.year <= 2099:
                return dt.strftime("%Y-%m-%d")
        except ValueError:
            # Try swapped day/month
            try:
                dt = datetime(int(y), int(d), int(m))
                if 2000 <= dt.year <= 2099:
                    return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

    return None


def parse_textract_expense(response):
    """
    Parse a Textract AnalyzeExpense API response.

    Args:
        response: dict — raw Textract AnalyzeExpense response.

    Returns:
        dict with keys:
            merchant_name: str or None
            total_amount: float or None (in rupees)
            date: str or None (YYYY-MM-DD)
            line_items: list of dicts [{name, price, quantity}]
            confidence: float (0.0–1.0 average)
            raw_fields: dict of all extracted summary fields
            low_confidence_fields: list of field names below threshold
    """
    result = {
        "merchant_name": None,
        "total_amount": None,
        "date": None,
        "line_items": [],
        "confidence": 0.0,
        "raw_fields": {},
        "low_confidence_fields": [],
    }

    if not response or not isinstance(response, dict):
        return result

    expense_documents = response.get("ExpenseDocuments", [])
    if not expense_documents:
        return result

    doc = expense_documents[0]
    confidences = []

    # ─── Extract summary fields ────────────────────────────────
    summary_fields = doc.get("SummaryFields", [])
    for field in summary_fields:
        field_type = field.get("Type", {})
        type_text = field_type.get("Text", "")
        type_confidence = field_type.get("Confidence", 0.0) / 100.0

        value_detection = field.get("ValueDetection", {})
        value_text = value_detection.get("Text", "")
        value_confidence = (value_detection.get("Confidence", 0.0)) / 100.0

        avg_conf = (type_confidence + value_confidence) / 2.0
        confidences.append(avg_conf)

        result["raw_fields"][type_text] = {
            "value": value_text,
            "confidence": round(avg_conf, 3),
        }

        if avg_conf < LOW_CONFIDENCE_THRESHOLD:
            result["low_confidence_fields"].append(type_text)

        # Map Textract fields to our schema
        if type_text == "VENDOR_NAME":
            result["merchant_name"] = value_text.strip() if value_text else None

        elif type_text == "TOTAL":
            result["total_amount"] = parse_currency(value_text)

        elif type_text == "SUBTOTAL" and result["total_amount"] is None:
            # Fallback: use subtotal if total not found
            result["total_amount"] = parse_currency(value_text)

        elif type_text in ("INVOICE_RECEIPT_DATE", "ORDER_DATE"):
            if result["date"] is None:
                result["date"] = parse_date(value_text)

    # ─── Extract line items ────────────────────────────────────
    line_item_groups = doc.get("LineItemGroups", [])
    for group in line_item_groups:
        for line_item in group.get("LineItems", []):
            item = {"name": None, "price": None, "quantity": None}
            for expense_field in line_item.get("LineItemExpenseFields", []):
                ft = expense_field.get("Type", {}).get("Text", "")
                fv = expense_field.get("ValueDetection", {}).get("Text", "")
                fc = expense_field.get("ValueDetection", {}).get("Confidence", 0.0) / 100.0
                confidences.append(fc)

                if ft == "ITEM":
                    item["name"] = fv
                elif ft == "PRICE":
                    item["price"] = parse_currency(fv)
                elif ft == "QUANTITY":
                    try:
                        item["quantity"] = int(float(fv))
                    except (ValueError, TypeError):
                        item["quantity"] = 1

            if item["name"] or item["price"]:
                result["line_items"].append(item)

    # ─── Compute average confidence ───────────────────────────
    if confidences:
        result["confidence"] = round(sum(confidences) / len(confidences), 3)

    return result
