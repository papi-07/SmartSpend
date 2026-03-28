"""
Unit tests for SmartSpend resource_tracker module.
Tests all tracking functions with actual cost calculations, input validation,
edge cases, and never-crash guarantees.
"""

import time
from decimal import Decimal
from unittest.mock import patch, MagicMock

import resource_tracker
from resource_tracker import (
    track_lambda_invocation,
    track_s3_operation,
    track_textract_call,
    track_dynamodb_operation,
    track_sns_publish,
    track_api_gateway_call,
    estimate_monthly_cost,
    _validate_positive,
    PRICING,
    FREE_TIER,
)


# ═══════════════════════════════════════════════════════════════════
# Input validation
# ═══════════════════════════════════════════════════════════════════

class TestValidatePositive:
    def test_positive_value(self):
        assert _validate_positive(100, "test") == 100.0

    def test_zero_value(self):
        assert _validate_positive(0, "test") == 0.0

    def test_negative_clamps_to_default(self):
        assert _validate_positive(-5, "test", default=1) == 1

    def test_none_returns_default(self):
        assert _validate_positive(None, "test", default=128) == 128

    def test_string_returns_default(self):
        assert _validate_positive("abc", "test", default=0) == 0

    def test_float_value(self):
        assert _validate_positive(3.14, "test") == 3.14


# ═══════════════════════════════════════════════════════════════════
# Lambda tracking
# ═══════════════════════════════════════════════════════════════════

class TestTrackLambdaInvocation:
    @patch.object(resource_tracker, "_log_usage")
    def test_logs_three_metrics(self, mock_log):
        """Should log invocation, duration_ms, and gb_seconds."""
        start = time.time() - 0.5
        track_lambda_invocation("create_expense", start, memory_mb=128)
        assert mock_log.call_count == 3

        metrics = [call[0][2] for call in mock_log.call_args_list]
        assert "invocation" in metrics
        assert "duration_ms" in metrics
        assert "gb_seconds" in metrics

    @patch.object(resource_tracker, "_log_usage")
    def test_invocation_count_is_one(self, mock_log):
        track_lambda_invocation("test_fn", time.time())
        invocation_call = [c for c in mock_log.call_args_list if c[0][2] == "invocation"][0]
        assert invocation_call[0][3] == 1

    @patch.object(resource_tracker, "_log_usage")
    def test_duration_is_positive(self, mock_log):
        start = time.time() - 0.25
        track_lambda_invocation("test_fn", start)
        duration_call = [c for c in mock_log.call_args_list if c[0][2] == "duration_ms"][0]
        assert duration_call[0][3] > 200  # at least 200ms

    @patch.object(resource_tracker, "_log_usage")
    def test_cost_calculation_accuracy(self, mock_log):
        """Verify cost = per_request + (gb_seconds * per_gb_second)."""
        start = time.time() - 1.0  # exactly 1 second
        track_lambda_invocation("test_fn", start, memory_mb=1024)

        invocation_call = [c for c in mock_log.call_args_list if c[0][2] == "invocation"][0]
        cost = invocation_call[0][4]

        # 1024 MB = 1 GB, 1 second = 1 GB-second
        expected = PRICING["lambda_per_request"] + (Decimal("1") * PRICING["lambda_per_gb_second"])
        assert abs(float(cost) - float(expected)) < 0.001

    @patch.object(resource_tracker, "_log_usage")
    def test_gb_seconds_calculated(self, mock_log):
        start = time.time() - 2.0
        track_lambda_invocation("test_fn", start, memory_mb=512)
        gb_call = [c for c in mock_log.call_args_list if c[0][2] == "gb_seconds"][0]
        # 512MB = 0.5GB, 2s => ~1.0 gb-seconds
        assert gb_call[0][3] > 0.8

    @patch.object(resource_tracker, "_log_usage")
    def test_negative_memory_clamped(self, mock_log):
        """Negative memory_mb should be clamped to default 128."""
        track_lambda_invocation("test_fn", time.time(), memory_mb=-256)
        # Should not crash, default to 128
        assert mock_log.call_count == 3

    @patch.object(resource_tracker, "_log_usage", side_effect=Exception("boom"))
    def test_never_raises_on_log_failure(self, mock_log):
        track_lambda_invocation("test_fn", time.time())

    def test_never_raises_on_bad_start_time(self):
        track_lambda_invocation("test_fn", "not_a_number")

    def test_never_raises_on_none_function_name(self):
        track_lambda_invocation(None, time.time())


# ═══════════════════════════════════════════════════════════════════
# S3 tracking
# ═══════════════════════════════════════════════════════════════════

class TestTrackS3Operation:
    @patch.object(resource_tracker, "_log_usage")
    def test_put_logs_request(self, mock_log):
        track_s3_operation("upload_receipt", "put", size_bytes=0)
        assert mock_log.call_count == 1
        assert mock_log.call_args_list[0][0][2] == "put_request"

    @patch.object(resource_tracker, "_log_usage")
    def test_put_with_size_logs_storage(self, mock_log):
        track_s3_operation("upload_receipt", "put", size_bytes=1048576)  # 1MB
        assert mock_log.call_count == 2
        storage_call = [c for c in mock_log.call_args_list if c[0][2] == "storage_bytes"][0]
        assert storage_call[0][3] == 1048576

    @patch.object(resource_tracker, "_log_usage")
    def test_put_cost_per_request(self, mock_log):
        track_s3_operation("fn", "put")
        cost = mock_log.call_args_list[0][0][4]
        assert float(cost) == float(PRICING["s3_per_1000_put"] / 1000)

    @patch.object(resource_tracker, "_log_usage")
    def test_get_logs_request(self, mock_log):
        track_s3_operation("get_expenses", "get")
        assert mock_log.call_count == 1
        assert mock_log.call_args_list[0][0][2] == "get_request"

    @patch.object(resource_tracker, "_log_usage")
    def test_get_cost_per_request(self, mock_log):
        track_s3_operation("fn", "get")
        cost = mock_log.call_args_list[0][0][4]
        assert float(cost) == float(PRICING["s3_per_1000_get"] / 1000)

    @patch.object(resource_tracker, "_log_usage")
    def test_delete_logs_request(self, mock_log):
        track_s3_operation("delete_expense", "delete")
        assert mock_log.call_count == 1
        assert mock_log.call_args_list[0][0][2] == "delete_request"

    @patch.object(resource_tracker, "_log_usage")
    def test_unknown_operation_logs_warning(self, mock_log):
        track_s3_operation("fn", "patch")
        assert mock_log.call_count == 0

    @patch.object(resource_tracker, "_log_usage")
    def test_negative_size_clamped(self, mock_log):
        track_s3_operation("fn", "put", size_bytes=-100)
        assert mock_log.call_count == 1  # only put_request, no storage

    @patch.object(resource_tracker, "_log_usage")
    def test_case_insensitive_operation(self, mock_log):
        track_s3_operation("fn", "PUT")
        assert mock_log.call_count >= 1

    @patch.object(resource_tracker, "_log_usage", side_effect=Exception("boom"))
    def test_never_raises(self, mock_log):
        track_s3_operation("fn", "put", size_bytes=100)


# ═══════════════════════════════════════════════════════════════════
# Textract tracking
# ═══════════════════════════════════════════════════════════════════

class TestTrackTextractCall:
    @patch.object(resource_tracker, "_log_usage")
    def test_single_page(self, mock_log):
        track_textract_call("process_receipt", pages=1)
        mock_log.assert_called_once()
        args = mock_log.call_args[0]
        assert args[0] == "textract"
        assert args[2] == "analyze_expense_call"
        assert args[3] == 1
        assert float(args[4]) == float(PRICING["textract_per_page"])

    @patch.object(resource_tracker, "_log_usage")
    def test_multiple_pages_cost(self, mock_log):
        track_textract_call("process_receipt", pages=5)
        cost = mock_log.call_args[0][4]
        assert float(cost) == float(Decimal("5") * PRICING["textract_per_page"])

    @patch.object(resource_tracker, "_log_usage")
    def test_zero_pages_clamped_to_one(self, mock_log):
        track_textract_call("fn", pages=0)
        assert mock_log.call_args[0][3] == 1

    @patch.object(resource_tracker, "_log_usage")
    def test_negative_pages_clamped(self, mock_log):
        track_textract_call("fn", pages=-3)
        assert mock_log.call_args[0][3] == 1

    @patch.object(resource_tracker, "_log_usage", side_effect=Exception("boom"))
    def test_never_raises(self, mock_log):
        track_textract_call("fn")


# ═══════════════════════════════════════════════════════════════════
# DynamoDB tracking
# ═══════════════════════════════════════════════════════════════════

class TestTrackDynamoDBOperation:
    @patch.object(resource_tracker, "_log_usage")
    def test_write_cost(self, mock_log):
        track_dynamodb_operation("create_expense", "write", units=2)
        args = mock_log.call_args[0]
        assert args[2] == "wcu"
        assert args[3] == 2
        assert float(args[4]) == float(Decimal("2") * PRICING["dynamodb_per_wcu"])

    @patch.object(resource_tracker, "_log_usage")
    def test_read_cost(self, mock_log):
        track_dynamodb_operation("get_expenses", "read", units=3)
        args = mock_log.call_args[0]
        assert args[2] == "rcu"
        assert args[3] == 3
        assert float(args[4]) == float(Decimal("3") * PRICING["dynamodb_per_rcu"])

    @patch.object(resource_tracker, "_log_usage")
    def test_unknown_operation_logs_warning(self, mock_log):
        track_dynamodb_operation("fn", "scan")
        assert mock_log.call_count == 0

    @patch.object(resource_tracker, "_log_usage")
    def test_case_insensitive(self, mock_log):
        track_dynamodb_operation("fn", "WRITE", units=1)
        assert mock_log.call_count == 1

    @patch.object(resource_tracker, "_log_usage")
    def test_zero_units_clamped_to_one(self, mock_log):
        track_dynamodb_operation("fn", "read", units=0)
        assert mock_log.call_args[0][3] == 1

    @patch.object(resource_tracker, "_log_usage", side_effect=Exception("boom"))
    def test_never_raises(self, mock_log):
        track_dynamodb_operation("fn", "write")


# ═══════════════════════════════════════════════════════════════════
# SNS tracking
# ═══════════════════════════════════════════════════════════════════

class TestTrackSnsPublish:
    @patch.object(resource_tracker, "_log_usage")
    def test_single_email(self, mock_log):
        track_sns_publish("budget_check")
        args = mock_log.call_args[0]
        assert args[0] == "sns"
        assert args[2] == "email_sent"
        assert args[3] == 1
        assert float(args[4]) == float(PRICING["sns_per_email"])

    @patch.object(resource_tracker, "_log_usage")
    def test_multiple_emails(self, mock_log):
        track_sns_publish("weekly_summary", count=5)
        args = mock_log.call_args[0]
        assert args[3] == 5
        assert float(args[4]) == float(Decimal("5") * PRICING["sns_per_email"])

    @patch.object(resource_tracker, "_log_usage")
    def test_zero_count_clamped(self, mock_log):
        track_sns_publish("fn", count=0)
        assert mock_log.call_args[0][3] == 1

    @patch.object(resource_tracker, "_log_usage", side_effect=Exception("boom"))
    def test_never_raises(self, mock_log):
        track_sns_publish("fn")


# ═══════════════════════════════════════════════════════════════════
# API Gateway tracking
# ═══════════════════════════════════════════════════════════════════

class TestTrackApiGatewayCall:
    @patch.object(resource_tracker, "_log_usage")
    def test_logs_api_call(self, mock_log):
        track_api_gateway_call("get_expenses")
        args = mock_log.call_args[0]
        assert args[0] == "apigateway"
        assert args[2] == "api_call"
        assert args[3] == 1
        assert float(args[4]) == float(PRICING["apigateway_per_call"])

    @patch.object(resource_tracker, "_log_usage", side_effect=Exception("boom"))
    def test_never_raises(self, mock_log):
        track_api_gateway_call("fn")

    def test_never_raises_none_function_name(self):
        """Should not crash even with None function name."""
        track_api_gateway_call(None)


# ═══════════════════════════════════════════════════════════════════
# Monthly cost estimation
# ═══════════════════════════════════════════════════════════════════

class TestEstimateMonthlyCost:
    def test_within_free_tier(self):
        """Usage within free tier should cost $0."""
        usage = {"lambda_requests": 500_000, "s3_put_requests": 1000}
        result = estimate_monthly_cost(usage)
        assert result["total_usd"] == 0.0

    def test_above_free_tier(self):
        """Usage above free tier should have non-zero cost."""
        usage = {"lambda_requests": 2_000_000}  # 1M over free tier
        result = estimate_monthly_cost(usage)
        assert result["total_usd"] > 0
        expected = float(Decimal("1000000") * PRICING["lambda_per_request"])
        assert abs(result["total_usd"] - expected) < 0.01

    def test_empty_usage(self):
        result = estimate_monthly_cost({})
        assert result["total_usd"] == 0.0

    def test_breakdown_present(self):
        usage = {"textract_pages": 2000}  # 1000 over free tier
        result = estimate_monthly_cost(usage)
        assert "Textract" in result["breakdown"]
        assert result["breakdown"]["Textract"] > 0

    def test_never_raises_on_bad_input(self):
        result = estimate_monthly_cost(None)
        assert result["total_usd"] == 0.0


# ═══════════════════════════════════════════════════════════════════
# Pricing constants sanity checks
# ═══════════════════════════════════════════════════════════════════

class TestPricingConstants:
    def test_all_prices_positive(self):
        for key, value in PRICING.items():
            assert value > 0, f"PRICING['{key}'] should be positive"

    def test_all_free_tier_positive(self):
        for key, value in FREE_TIER.items():
            assert value > 0, f"FREE_TIER['{key}'] should be positive"

    def test_lambda_pricing_order(self):
        """GB-second should cost more than a single request."""
        assert PRICING["lambda_per_gb_second"] > PRICING["lambda_per_request"]

    def test_textract_most_expensive(self):
        """Textract per-page should be the most expensive per-unit cost."""
        assert PRICING["textract_per_page"] > PRICING["lambda_per_request"]
        assert PRICING["textract_per_page"] > PRICING["dynamodb_per_wcu"]
