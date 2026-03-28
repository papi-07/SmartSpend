"""
Unit tests for SmartSpend anomaly_utils — enhanced anomaly detection.
Tests mean+2.5σ, 3×median, absolute threshold, and alert publishing.
"""

import math
from decimal import Decimal
from unittest.mock import patch, MagicMock

from anomaly_utils import (
    check_anomaly, check_budget, publish_anomaly_alert, publish_budget_alert,
    _compute_stats, ABSOLUTE_THRESHOLD_PAISE,
)


MOD = "anomaly_utils"


# ═══════════════════════════════════════════════════════════════════
# _compute_stats tests
# ═══════════════════════════════════════════════════════════════════

class TestComputeStats:
    def test_empty_list(self):
        mean, std, median = _compute_stats([])
        assert mean == 0.0
        assert std == 0.0
        assert median == 0.0

    def test_single_value(self):
        mean, std, median = _compute_stats([100.0])
        assert mean == 100.0
        assert std == 0.0
        assert median == 100.0

    def test_two_values(self):
        mean, std, median = _compute_stats([100.0, 200.0])
        assert mean == 150.0
        assert median == 150.0
        assert std > 0

    def test_odd_count_median(self):
        mean, std, median = _compute_stats([10, 20, 30])
        assert median == 20

    def test_even_count_median(self):
        mean, std, median = _compute_stats([10, 20, 30, 40])
        assert median == 25.0

    def test_known_std_dev(self):
        # Values: [2, 4, 4, 4, 5, 5, 7, 9] → sample std ≈ 2.138
        values = [2, 4, 4, 4, 5, 5, 7, 9]
        mean, std, median = _compute_stats(values)
        assert mean == 5.0
        assert abs(std - math.sqrt(32 / 7)) < 0.01
        assert median == 4.5

    def test_uniform_values(self):
        mean, std, median = _compute_stats([200, 200, 200, 200])
        assert mean == 200
        assert std == 0.0
        assert median == 200


# ═══════════════════════════════════════════════════════════════════
# check_anomaly tests
# ═══════════════════════════════════════════════════════════════════

class TestCheckAnomaly:
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items", return_value=[])
    def test_no_history_below_threshold(self, mock_query, mock_track):
        """No expense history + amount below ₹5000 → not anomalous."""
        is_anomaly, avg, msg = check_anomaly("user-1", "Food", 20000)
        assert is_anomaly is False
        assert avg == Decimal("0")

    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items", return_value=[])
    def test_no_history_above_threshold(self, mock_query, mock_track):
        """No expense history + amount above ₹5000 → anomalous."""
        is_anomaly, avg, msg = check_anomaly("user-1", "Food", 600000)
        assert is_anomaly is True
        assert "threshold" in msg.lower()
        assert "no spending history" in msg.lower()

    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items")
    def test_fewer_than_3_expenses_below_threshold(self, mock_query, mock_track):
        """Only 2 expenses in history + amount < ₹5000 → not anomalous."""
        mock_query.return_value = [
            {"date": "2026-03-20", "amountPaise": 20000, "category": "Food"},
            {"date": "2026-03-22", "amountPaise": 25000, "category": "Food"},
        ]
        is_anomaly, avg, msg = check_anomaly("user-1", "Food", 40000)
        assert is_anomaly is False

    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items")
    def test_fewer_than_3_expenses_above_threshold(self, mock_query, mock_track):
        """Only 2 expenses in history + amount > ₹5000 → anomalous."""
        mock_query.return_value = [
            {"date": "2026-03-20", "amountPaise": 20000, "category": "Food"},
            {"date": "2026-03-22", "amountPaise": 25000, "category": "Food"},
        ]
        is_anomaly, avg, msg = check_anomaly("user-1", "Food", 600000)
        assert is_anomaly is True
        assert "only 2 expense(s)" in msg.lower()

    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items")
    def test_normal_spending_not_anomalous(self, mock_query, mock_track):
        """Normal amount within expected range → not anomalous."""
        # 10 expenses of ~₹200 each (20000 paise)
        mock_query.return_value = [
            {"date": f"2026-03-{10+i}", "amountPaise": 20000, "category": "Food"}
            for i in range(10)
        ]
        # ₹250 — well within normal range
        is_anomaly, avg, msg = check_anomaly("user-1", "Food", 25000)
        assert is_anomaly is False

    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items")
    def test_stddev_anomaly(self, mock_query, mock_track):
        """Amount > mean + 2.5σ → anomalous (std dev check)."""
        # Create expenses with some variation
        amounts = [20000, 22000, 18000, 21000, 19000,
                   20500, 21500, 19500, 20000, 22000]
        mock_query.return_value = [
            {"date": f"2026-03-{10+i}", "amountPaise": a, "category": "Food"}
            for i, a in enumerate(amounts)
        ]
        # ₹2000 (200000 paise) — way above mean + 2.5σ
        is_anomaly, avg, msg = check_anomaly("user-1", "Food", 200000)
        assert is_anomaly is True
        assert "mean + 2.5σ" in msg

    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items")
    def test_median_anomaly(self, mock_query, mock_track):
        """Amount > 3× median → anomalous (median check)."""
        # Mix of expenses with one outlier in history (high std dev)
        # so mean+2.5σ might not catch it, but 3×median will
        amounts = [10000, 10000, 10000, 10000, 10000, 10000, 10000, 10000, 10000, 90000]
        mock_query.return_value = [
            {"date": f"2026-03-{10+i}", "amountPaise": a, "category": "Food"}
            for i, a in enumerate(amounts)
        ]
        # Median = 10000, 3×median = 30000
        # Mean = 19000, std ~25298, mean+2.5σ ≈ 82245
        # Amount = 35000 → above 3×median but below mean+2.5σ
        is_anomaly, avg, msg = check_anomaly("user-1", "Food", 35000)
        assert is_anomaly is True
        assert "median" in msg.lower()

    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items")
    def test_uniform_spending_anomaly(self, mock_query, mock_track):
        """All expenses same amount (std=0), amount > 2.5× mean → anomalous."""
        mock_query.return_value = [
            {"date": f"2026-03-{10+i}", "amountPaise": 20000, "category": "Food"}
            for i in range(10)
        ]
        # 2.5 × 20000 = 50000, try 55000
        is_anomaly, avg, msg = check_anomaly("user-1", "Food", 55000)
        assert is_anomaly is True
        assert "average" in msg.lower()

    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items")
    def test_uniform_spending_within_range(self, mock_query, mock_track):
        """All expenses same amount (std=0), amount < 2.5× mean → not anomalous."""
        mock_query.return_value = [
            {"date": f"2026-03-{10+i}", "amountPaise": 20000, "category": "Food"}
            for i in range(10)
        ]
        # 2.5 × 20000 = 50000, try 45000 (below threshold)
        is_anomaly, avg, msg = check_anomaly("user-1", "Food", 45000)
        assert is_anomaly is False

    def test_empty_user_id(self):
        is_anomaly, avg, msg = check_anomaly("", "Food", 20000)
        assert is_anomaly is False

    def test_empty_category(self):
        is_anomaly, avg, msg = check_anomaly("user-1", "", 20000)
        assert is_anomaly is False

    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items", side_effect=Exception("DB Error"))
    def test_exception_returns_not_anomalous(self, mock_query, mock_track):
        """Exceptions should be caught — return not anomalous."""
        is_anomaly, avg, msg = check_anomaly("user-1", "Food", 200000)
        assert is_anomaly is False
        assert avg == Decimal("0")

    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.query_items")
    def test_old_expenses_filtered_out(self, mock_query, mock_track):
        """Expenses older than 30 days should be excluded."""
        mock_query.return_value = [
            {"date": "2026-01-01", "amountPaise": 20000, "category": "Food"},
            {"date": "2026-01-05", "amountPaise": 20000, "category": "Food"},
        ]
        # Only old data → treated as "no recent history"
        is_anomaly, avg, msg = check_anomaly("user-1", "Food", 30000)
        assert is_anomaly is False


# ═══════════════════════════════════════════════════════════════════
# publish_anomaly_alert tests
# ═══════════════════════════════════════════════════════════════════

class TestPublishAnomalyAlert:
    @patch(f"{MOD}.track_sns_publish")
    @patch(f"{MOD}.boto3")
    @patch(f"{MOD}.SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123:topic")
    def test_publishes_email(self, mock_boto, mock_track):
        mock_sns = MagicMock()
        mock_boto.client.return_value = mock_sns

        publish_anomaly_alert("user-1", "test@example.com", "Test anomaly")

        mock_sns.publish.assert_called_once()
        call_kwargs = mock_sns.publish.call_args[1]
        assert "Unusual Spending" in call_kwargs["Subject"]
        assert "test@example.com" in call_kwargs["Message"]
        assert "Test anomaly" in call_kwargs["Message"]

    @patch(f"{MOD}.SNS_TOPIC_ARN", "")
    def test_skips_when_no_topic(self):
        """Should not crash when SNS_TOPIC_ARN is not set."""
        publish_anomaly_alert("user-1", "", "Test")  # Should not raise


# ═══════════════════════════════════════════════════════════════════
# publish_budget_alert tests
# ═══════════════════════════════════════════════════════════════════

class TestPublishBudgetAlert:
    @patch(f"{MOD}.track_sns_publish")
    @patch(f"{MOD}.boto3")
    @patch(f"{MOD}.SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123:topic")
    def test_publishes_budget_email(self, mock_boto, mock_track):
        mock_sns = MagicMock()
        mock_boto.client.return_value = mock_sns

        publish_budget_alert(
            "user-1", "test@example.com", "Food",
            spent_paise=450000, limit_paise=500000, percent_used=90.0,
        )

        mock_sns.publish.assert_called_once()
        call_kwargs = mock_sns.publish.call_args[1]
        assert "Budget Alert" in call_kwargs["Subject"]
        assert "Food" in call_kwargs["Subject"]
        assert "90%" in call_kwargs["Message"]
        assert "₹4,500.00" in call_kwargs["Message"]

    @patch(f"{MOD}.SNS_TOPIC_ARN", "")
    def test_skips_when_no_topic(self):
        publish_budget_alert("user-1", "", "Food", 0, 0, 0)  # Should not raise


# ═══════════════════════════════════════════════════════════════════
# check_budget tests — alert only when crossing threshold
# ═══════════════════════════════════════════════════════════════════

class TestCheckBudget:
    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.get_item", return_value=None)
    def test_no_budget_returns_none(self, mock_get, mock_track):
        """No budget set for category → returns None, no alert."""
        result = check_budget("user-1", "test@example.com", "Food")
        assert result is None

    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.publish_budget_alert")
    @patch(f"{MOD}.query_items")
    @patch(f"{MOD}.get_item")
    def test_below_threshold_returns_none(self, mock_get, mock_query,
                                           mock_pub, mock_track):
        """Spending below threshold → returns None."""
        mock_get.return_value = {
            "userId": "user-1", "category": "Food",
            "monthlyLimitPaise": 500000, "alertThreshold": 80,
        }
        # 3 expenses totaling ₹2000 (200000 paise) = 40% of ₹5000
        mock_query.return_value = [
            {"amountPaise": 70000, "category": "Food"},
            {"amountPaise": 60000, "category": "Food"},
            {"amountPaise": 70000, "category": "Food"},
        ]
        result = check_budget("user-1", "test@example.com", "Food",
                              current_amount_paise=70000)
        assert result is None
        mock_pub.assert_not_called()

    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.publish_budget_alert")
    @patch(f"{MOD}.query_items")
    @patch(f"{MOD}.get_item")
    def test_crossing_threshold_sends_alert(self, mock_get, mock_query,
                                             mock_pub, mock_track):
        """Spending crosses threshold with latest expense → sends alert."""
        mock_get.return_value = {
            "userId": "user-1", "category": "Food",
            "monthlyLimitPaise": 500000, "alertThreshold": 80,
        }
        # 5 expenses: 4 old ones = 350000 (70%), latest = 60000 → total 410000 (82%)
        mock_query.return_value = [
            {"amountPaise": 90000, "category": "Food"},
            {"amountPaise": 85000, "category": "Food"},
            {"amountPaise": 90000, "category": "Food"},
            {"amountPaise": 85000, "category": "Food"},
            {"amountPaise": 60000, "category": "Food"},  # latest — pushes past 80%
        ]
        result = check_budget("user-1", "test@example.com", "Food",
                              current_amount_paise=60000)
        assert result is not None
        assert result["alertSent"] is True
        assert result["percentUsed"] == 82.0
        mock_pub.assert_called_once()

    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.publish_budget_alert")
    @patch(f"{MOD}.query_items")
    @patch(f"{MOD}.get_item")
    def test_already_past_threshold_no_new_crossing(self, mock_get, mock_query,
                                                      mock_pub, mock_track):
        """Already past threshold but not crossing a new band → no alert."""
        mock_get.return_value = {
            "userId": "user-1", "category": "Food",
            "monthlyLimitPaise": 500000, "alertThreshold": 80,
        }
        # Already at 86%, adding small amount (5000 paise) stays at ~86%
        # Previous = 430000 - 5000 = 425000 (85%) — already past 80%, no new crossing
        mock_query.return_value = [
            {"amountPaise": 200000, "category": "Food"},
            {"amountPaise": 200000, "category": "Food"},
            {"amountPaise": 25000, "category": "Food"},
            {"amountPaise": 5000, "category": "Food"},  # latest
        ]
        result = check_budget("user-1", "test@example.com", "Food",
                              current_amount_paise=5000)
        assert result is not None
        assert result["alertSent"] is False  # No new threshold crossed
        mock_pub.assert_not_called()

    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.publish_budget_alert")
    @patch(f"{MOD}.query_items")
    @patch(f"{MOD}.get_item")
    def test_crossing_100_sends_alert(self, mock_get, mock_query,
                                       mock_pub, mock_track):
        """Spending crosses 100% → sends alert even if already past threshold."""
        mock_get.return_value = {
            "userId": "user-1", "category": "Food",
            "monthlyLimitPaise": 500000, "alertThreshold": 80,
        }
        # Total = 520000 (104%), current expense = 40000
        # Previous = 520000 - 40000 = 480000 (96%) — crosses 100%
        mock_query.return_value = [
            {"amountPaise": 200000, "category": "Food"},
            {"amountPaise": 200000, "category": "Food"},
            {"amountPaise": 80000, "category": "Food"},
            {"amountPaise": 40000, "category": "Food"},  # pushes past 100%
        ]
        result = check_budget("user-1", "test@example.com", "Food",
                              current_amount_paise=40000)
        assert result is not None
        assert result["alertSent"] is True
        assert result["percentUsed"] == 104.0
        mock_pub.assert_called_once()

    @patch(f"{MOD}.track_dynamodb_operation")
    @patch(f"{MOD}.publish_budget_alert")
    @patch(f"{MOD}.query_items")
    @patch(f"{MOD}.get_item")
    def test_at_90_no_spam(self, mock_get, mock_query, mock_pub, mock_track):
        """At 90% but threshold is 80% and already past it → NO alert (no spam)."""
        mock_get.return_value = {
            "userId": "user-1", "category": "Food",
            "monthlyLimitPaise": 500000, "alertThreshold": 80,
        }
        # Total = 450000 (90%), current expense = 25000
        # Previous = 450000 - 25000 = 425000 (85%) — already past 80%, not yet 100%
        mock_query.return_value = [
            {"amountPaise": 200000, "category": "Food"},
            {"amountPaise": 200000, "category": "Food"},
            {"amountPaise": 25000, "category": "Food"},
            {"amountPaise": 25000, "category": "Food"},
        ]
        result = check_budget("user-1", "test@example.com", "Food",
                              current_amount_paise=25000)
        assert result is not None
        assert result["alertSent"] is False  # 90% → no alert (not crossing 80% or 100%)
        mock_pub.assert_not_called()

    def test_empty_user_id(self):
        result = check_budget("", "", "Food")
        assert result is None

    def test_empty_category(self):
        result = check_budget("user-1", "", "")
        assert result is None
