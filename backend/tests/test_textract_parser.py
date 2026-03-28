"""
Unit tests for SmartSpend textract_parser module.
Tests currency parsing, date parsing, and full Textract response parsing
with multiple formats and edge cases.
"""

from textract_parser import parse_currency, parse_date, parse_textract_expense


# ═══════════════════════════════════════════════════════════════════
# Currency Parsing
# ═══════════════════════════════════════════════════════════════════

class TestParseCurrency:
    def test_plain_number(self):
        assert parse_currency("150") == 150.0

    def test_with_decimal(self):
        assert parse_currency("150.50") == 150.50

    def test_rupee_symbol(self):
        assert parse_currency("₹150") == 150.0

    def test_rupee_symbol_with_space(self):
        assert parse_currency("₹ 150") == 150.0

    def test_rs_prefix(self):
        assert parse_currency("Rs. 150") == 150.0

    def test_rs_no_dot(self):
        assert parse_currency("Rs150") == 150.0

    def test_rs_space(self):
        assert parse_currency("Rs 150") == 150.0

    def test_inr_prefix(self):
        assert parse_currency("INR 150") == 150.0

    def test_indian_comma_format(self):
        assert parse_currency("₹1,500.50") == 1500.50

    def test_large_indian_format(self):
        assert parse_currency("₹1,23,456.78") == 123456.78

    def test_western_comma_format(self):
        assert parse_currency("1,000.00") == 1000.0

    def test_trailing_slash(self):
        assert parse_currency("₹150/-") == 150.0

    def test_none_input(self):
        assert parse_currency(None) is None

    def test_empty_string(self):
        assert parse_currency("") is None

    def test_non_string(self):
        assert parse_currency(123) is None

    def test_text_only(self):
        assert parse_currency("no numbers here") is None

    def test_zero(self):
        assert parse_currency("0.00") == 0.0

    def test_large_amount(self):
        assert parse_currency("99999.99") == 99999.99


class TestParseDate:
    def test_iso_format(self):
        assert parse_date("2026-03-15") == "2026-03-15"

    def test_dd_mm_yyyy_slash(self):
        assert parse_date("15/03/2026") == "2026-03-15"

    def test_dd_mm_yyyy_dash(self):
        assert parse_date("15-03-2026") == "2026-03-15"

    def test_dd_mon_yyyy(self):
        assert parse_date("15 Mar 2026") == "2026-03-15"

    def test_dd_month_yyyy(self):
        assert parse_date("15 March 2026") == "2026-03-15"

    def test_mon_dd_comma_yyyy(self):
        assert parse_date("Mar 15, 2026") == "2026-03-15"

    def test_mon_dd_yyyy(self):
        assert parse_date("Mar 15 2026") == "2026-03-15"

    def test_dd_mm_yy_slash(self):
        assert parse_date("15/03/26") == "2026-03-15"

    def test_dd_mm_yy_dash(self):
        assert parse_date("15-03-26") == "2026-03-15"

    def test_dd_mm_yyyy_dot(self):
        assert parse_date("15.03.2026") == "2026-03-15"

    def test_none_input(self):
        assert parse_date(None) is None

    def test_empty_string(self):
        assert parse_date("") is None

    def test_garbage(self):
        assert parse_date("not a date") is None

    def test_non_string(self):
        assert parse_date(12345) is None


# ═══════════════════════════════════════════════════════════════════
# Full Textract Response Parsing
# ═══════════════════════════════════════════════════════════════════

def _make_field(type_text, value_text, type_conf=99.0, value_conf=99.0):
    """Helper to create a Textract summary field."""
    return {
        "Type": {"Text": type_text, "Confidence": type_conf},
        "ValueDetection": {"Text": value_text, "Confidence": value_conf},
    }


def _make_response(summary_fields=None, line_items=None):
    """Helper to create a minimal Textract AnalyzeExpense response."""
    doc = {"SummaryFields": summary_fields or []}
    if line_items:
        doc["LineItemGroups"] = [{
            "LineItems": [
                {"LineItemExpenseFields": li} for li in line_items
            ]
        }]
    return {"ExpenseDocuments": [doc]}


class TestParseTextractExpense:
    def test_restaurant_bill(self):
        """Typical Indian restaurant receipt."""
        resp = _make_response([
            _make_field("VENDOR_NAME", "Barbeque Nation"),
            _make_field("TOTAL", "₹2,450.00"),
            _make_field("INVOICE_RECEIPT_DATE", "15/03/2026"),
        ])
        parsed = parse_textract_expense(resp)
        assert parsed["merchant_name"] == "Barbeque Nation"
        assert parsed["total_amount"] == 2450.0
        assert parsed["date"] == "2026-03-15"
        assert parsed["confidence"] > 0.9

    def test_grocery_receipt(self):
        """Grocery store receipt with Rs. format."""
        resp = _make_response([
            _make_field("VENDOR_NAME", "D-Mart"),
            _make_field("TOTAL", "Rs. 1,236.50"),
            _make_field("INVOICE_RECEIPT_DATE", "Mar 20, 2026"),
        ])
        parsed = parse_textract_expense(resp)
        assert parsed["merchant_name"] == "D-Mart"
        assert parsed["total_amount"] == 1236.50
        assert parsed["date"] == "2026-03-20"

    def test_cab_receipt(self):
        """Cab receipt with simple amount."""
        resp = _make_response([
            _make_field("VENDOR_NAME", "Uber"),
            _make_field("TOTAL", "350.00"),
            _make_field("INVOICE_RECEIPT_DATE", "2026-03-25"),
        ])
        parsed = parse_textract_expense(resp)
        assert parsed["merchant_name"] == "Uber"
        assert parsed["total_amount"] == 350.0
        assert parsed["date"] == "2026-03-25"

    def test_missing_vendor(self):
        """Receipt with no vendor name detected."""
        resp = _make_response([
            _make_field("TOTAL", "₹500"),
            _make_field("INVOICE_RECEIPT_DATE", "15-03-2026"),
        ])
        parsed = parse_textract_expense(resp)
        assert parsed["merchant_name"] is None
        assert parsed["total_amount"] == 500.0

    def test_missing_total_uses_subtotal(self):
        """Falls back to SUBTOTAL when TOTAL is missing."""
        resp = _make_response([
            _make_field("VENDOR_NAME", "Cafe Coffee Day"),
            _make_field("SUBTOTAL", "₹350"),
            _make_field("INVOICE_RECEIPT_DATE", "15/03/2026"),
        ])
        parsed = parse_textract_expense(resp)
        assert parsed["total_amount"] == 350.0

    def test_missing_date(self):
        """Receipt with no date."""
        resp = _make_response([
            _make_field("VENDOR_NAME", "Swiggy"),
            _make_field("TOTAL", "₹250"),
        ])
        parsed = parse_textract_expense(resp)
        assert parsed["date"] is None
        assert parsed["total_amount"] == 250.0

    def test_with_line_items(self):
        """Receipt with itemized line items."""
        line_items = [
            [
                {"Type": {"Text": "ITEM"}, "ValueDetection": {"Text": "Pizza", "Confidence": 95.0}},
                {"Type": {"Text": "PRICE"}, "ValueDetection": {"Text": "₹350", "Confidence": 90.0}},
                {"Type": {"Text": "QUANTITY"}, "ValueDetection": {"Text": "2", "Confidence": 95.0}},
            ],
            [
                {"Type": {"Text": "ITEM"}, "ValueDetection": {"Text": "Coke", "Confidence": 92.0}},
                {"Type": {"Text": "PRICE"}, "ValueDetection": {"Text": "₹60", "Confidence": 88.0}},
            ],
        ]
        resp = _make_response(
            [_make_field("VENDOR_NAME", "Dominos"), _make_field("TOTAL", "₹760")],
            line_items,
        )
        parsed = parse_textract_expense(resp)
        assert len(parsed["line_items"]) == 2
        assert parsed["line_items"][0]["name"] == "Pizza"
        assert parsed["line_items"][0]["price"] == 350.0
        assert parsed["line_items"][0]["quantity"] == 2
        assert parsed["line_items"][1]["name"] == "Coke"

    def test_low_confidence(self):
        """Low confidence fields should be flagged."""
        resp = _make_response([
            _make_field("VENDOR_NAME", "???", type_conf=40.0, value_conf=35.0),
            _make_field("TOTAL", "₹150", type_conf=90.0, value_conf=90.0),
        ])
        parsed = parse_textract_expense(resp)
        assert "VENDOR_NAME" in parsed["low_confidence_fields"]
        assert parsed["confidence"] < 0.9

    def test_empty_response(self):
        parsed = parse_textract_expense({})
        assert parsed["merchant_name"] is None
        assert parsed["total_amount"] is None
        assert parsed["date"] is None
        assert parsed["confidence"] == 0.0

    def test_none_response(self):
        parsed = parse_textract_expense(None)
        assert parsed["merchant_name"] is None

    def test_no_expense_documents(self):
        parsed = parse_textract_expense({"ExpenseDocuments": []})
        assert parsed["merchant_name"] is None

    def test_inr_format(self):
        """Amount with INR prefix."""
        resp = _make_response([
            _make_field("VENDOR_NAME", "IRCTC"),
            _make_field("TOTAL", "INR 1250"),
        ])
        parsed = parse_textract_expense(resp)
        assert parsed["total_amount"] == 1250.0
