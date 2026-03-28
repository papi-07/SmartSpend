"""
Unit tests for SmartSpend response_utils module.
Verifies CORS headers, JSON formatting, status codes, Decimal encoding,
and edge cases.
"""

import json
from decimal import Decimal

from response_utils import (
    success, error, created, not_found, server_error, options_response,
    CORS_HEADERS, DecimalEncoder,
)


# ═══════════════════════════════════════════════════════════════════
# success()
# ═══════════════════════════════════════════════════════════════════

class TestSuccessResponse:
    def test_status_code(self):
        resp = success({"message": "ok"})
        assert resp["statusCode"] == 200

    def test_custom_status_code(self):
        resp = success({"message": "ok"}, status_code=202)
        assert resp["statusCode"] == 202

    def test_cors_headers_present(self):
        resp = success({})
        for key, value in CORS_HEADERS.items():
            assert resp["headers"][key] == value

    def test_body_is_json_string(self):
        resp = success({"key": "value"})
        body = json.loads(resp["body"])
        assert body["key"] == "value"

    def test_list_body(self):
        resp = success([1, 2, 3])
        body = json.loads(resp["body"])
        assert body == [1, 2, 3]

    def test_empty_dict_body(self):
        resp = success({})
        body = json.loads(resp["body"])
        assert body == {}

    def test_nested_body(self):
        data = {"items": [{"id": 1, "nested": {"deep": True}}]}
        resp = success(data)
        body = json.loads(resp["body"])
        assert body["items"][0]["nested"]["deep"] is True

    def test_unicode_body(self):
        resp = success({"name": "résumé café"})
        body = json.loads(resp["body"])
        assert body["name"] == "résumé café"

    def test_large_body(self):
        data = {"items": [{"id": i} for i in range(1000)]}
        resp = success(data)
        body = json.loads(resp["body"])
        assert len(body["items"]) == 1000


# ═══════════════════════════════════════════════════════════════════
# error()
# ═══════════════════════════════════════════════════════════════════

class TestErrorResponse:
    def test_default_status_code(self):
        resp = error("bad request")
        assert resp["statusCode"] == 400

    def test_custom_status_code(self):
        resp = error("forbidden", status_code=403)
        assert resp["statusCode"] == 403

    def test_error_body_format(self):
        resp = error("something went wrong")
        body = json.loads(resp["body"])
        assert body["error"] == "something went wrong"

    def test_cors_headers(self):
        resp = error("err")
        assert resp["headers"]["Access-Control-Allow-Origin"] == "*"

    def test_empty_message(self):
        resp = error("")
        body = json.loads(resp["body"])
        assert body["error"] == ""

    def test_long_error_message(self):
        msg = "Error: " + "x" * 1000
        resp = error(msg)
        body = json.loads(resp["body"])
        assert body["error"] == msg


# ═══════════════════════════════════════════════════════════════════
# Convenience response functions
# ═══════════════════════════════════════════════════════════════════

class TestCreatedResponse:
    def test_status_code(self):
        assert created({"id": "abc"})["statusCode"] == 201

    def test_body(self):
        body = json.loads(created({"id": "abc"})["body"])
        assert body["id"] == "abc"

    def test_cors_headers(self):
        resp = created({})
        assert resp["headers"]["Access-Control-Allow-Origin"] == "*"


class TestNotFoundResponse:
    def test_status_code(self):
        assert not_found()["statusCode"] == 404

    def test_default_message(self):
        body = json.loads(not_found()["body"])
        assert body["error"] == "Resource not found"

    def test_custom_message(self):
        body = json.loads(not_found("Expense not found")["body"])
        assert body["error"] == "Expense not found"


class TestServerErrorResponse:
    def test_status_code(self):
        assert server_error()["statusCode"] == 500

    def test_default_message(self):
        body = json.loads(server_error()["body"])
        assert body["error"] == "Internal server error"

    def test_custom_message(self):
        body = json.loads(server_error("DB connection failed")["body"])
        assert body["error"] == "DB connection failed"


class TestOptionsResponse:
    def test_status_code(self):
        assert options_response()["statusCode"] == 200

    def test_empty_body(self):
        assert options_response()["body"] == ""

    def test_cors_headers(self):
        resp = options_response()
        assert "Access-Control-Allow-Methods" in resp["headers"]
        assert "Access-Control-Allow-Origin" in resp["headers"]


# ═══════════════════════════════════════════════════════════════════
# DecimalEncoder
# ═══════════════════════════════════════════════════════════════════

class TestDecimalEncoder:
    def test_decimal_integer(self):
        result = json.dumps({"val": Decimal("42")}, cls=DecimalEncoder)
        assert json.loads(result)["val"] == 42
        assert isinstance(json.loads(result)["val"], int)

    def test_decimal_float(self):
        result = json.dumps({"val": Decimal("3.14")}, cls=DecimalEncoder)
        assert abs(json.loads(result)["val"] - 3.14) < 0.001

    def test_decimal_zero(self):
        result = json.dumps({"val": Decimal("0")}, cls=DecimalEncoder)
        assert json.loads(result)["val"] == 0

    def test_large_decimal(self):
        result = json.dumps({"val": Decimal("999999999")}, cls=DecimalEncoder)
        assert json.loads(result)["val"] == 999999999

    def test_small_decimal(self):
        result = json.dumps({"val": Decimal("0.00001")}, cls=DecimalEncoder)
        assert json.loads(result)["val"] > 0

    def test_nested_decimals(self):
        data = {"items": [{"amount": Decimal("10.5")}, {"amount": Decimal("20")}]}
        result = json.dumps(data, cls=DecimalEncoder)
        parsed = json.loads(result)
        assert parsed["items"][0]["amount"] == 10.5
        assert parsed["items"][1]["amount"] == 20

    def test_non_decimal_passes_through(self):
        result = json.dumps({"val": "string", "num": 42}, cls=DecimalEncoder)
        parsed = json.loads(result)
        assert parsed["val"] == "string"
        assert parsed["num"] == 42


# ═══════════════════════════════════════════════════════════════════
# CORS Headers
# ═══════════════════════════════════════════════════════════════════

class TestCorsHeaders:
    def test_allow_origin_wildcard(self):
        assert CORS_HEADERS["Access-Control-Allow-Origin"] == "*"

    def test_all_methods_present(self):
        methods = CORS_HEADERS["Access-Control-Allow-Methods"]
        for m in ["GET", "POST", "PUT", "DELETE", "OPTIONS"]:
            assert m in methods

    def test_authorization_header_allowed(self):
        assert "Authorization" in CORS_HEADERS["Access-Control-Allow-Headers"]

    def test_user_id_header_allowed(self):
        assert "X-User-Id" in CORS_HEADERS["Access-Control-Allow-Headers"]

    def test_content_type_header(self):
        assert CORS_HEADERS["Content-Type"] == "application/json"

    def test_api_key_header_allowed(self):
        assert "X-Api-Key" in CORS_HEADERS["Access-Control-Allow-Headers"]
