"""
Unit tests for SmartSpend db_utils module.
Mocks boto3 DynamoDB to test all CRUD operations including edge cases,
pagination, batch writes, and the query_by_partition convenience helper.
"""

from unittest.mock import patch, MagicMock, call
from botocore.exceptions import ClientError

import db_utils
from db_utils import (
    put_item, get_item, query_items, update_item, delete_item,
    scan_items, query_by_partition, batch_write_items, batch_delete_items,
    MAX_PAGINATION_ITERATIONS,
)


def _make_client_error(msg="Test error"):
    return ClientError({"Error": {"Message": msg, "Code": "500"}}, "TestOp")


# ═══════════════════════════════════════════════════════════════════
# put_item
# ═══════════════════════════════════════════════════════════════════

class TestPutItem:
    @patch.object(db_utils, "_get_table")
    def test_success(self, mock_get_table):
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table

        result = put_item("TestTable", {"id": "1", "name": "test"})
        assert result == {"success": True}
        mock_table.put_item.assert_called_once_with(Item={"id": "1", "name": "test"})

    @patch.object(db_utils, "_get_table")
    def test_client_error(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.put_item.side_effect = _make_client_error("Access denied")
        mock_get_table.return_value = mock_table

        result = put_item("TestTable", {"id": "1"})
        assert result["success"] is False
        assert "Access denied" in result["error"]

    @patch.object(db_utils, "_get_table", side_effect=Exception("unexpected"))
    def test_generic_error(self, mock_get_table):
        result = put_item("TestTable", {"id": "1"})
        assert result["success"] is False
        assert "unexpected" in result["error"]

    @patch.object(db_utils, "_get_table")
    def test_empty_item(self, mock_get_table):
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table
        result = put_item("TestTable", {})
        assert result == {"success": True}

    @patch.object(db_utils, "_get_table")
    def test_large_item(self, mock_get_table):
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table
        large_item = {"id": "1", "data": "x" * 10000}
        result = put_item("TestTable", large_item)
        assert result == {"success": True}


# ═══════════════════════════════════════════════════════════════════
# get_item
# ═══════════════════════════════════════════════════════════════════

class TestGetItem:
    @patch.object(db_utils, "_get_table")
    def test_found(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": {"id": "1", "name": "test"}}
        mock_get_table.return_value = mock_table

        result = get_item("TestTable", {"id": "1"})
        assert result == {"id": "1", "name": "test"}

    @patch.object(db_utils, "_get_table")
    def test_not_found_returns_none(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_get_table.return_value = mock_table

        result = get_item("TestTable", {"id": "nonexistent"})
        assert result is None

    @patch.object(db_utils, "_get_table")
    def test_client_error_returns_none(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.get_item.side_effect = _make_client_error()
        mock_get_table.return_value = mock_table

        result = get_item("TestTable", {"id": "1"})
        assert result is None

    @patch.object(db_utils, "_get_table")
    def test_composite_key(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": {"userId": "u1", "expenseId": "e1"}}
        mock_get_table.return_value = mock_table

        result = get_item("Expenses", {"userId": "u1", "expenseId": "e1"})
        assert result["userId"] == "u1"
        assert result["expenseId"] == "e1"


# ═══════════════════════════════════════════════════════════════════
# query_items (uses Query, not Scan)
# ═══════════════════════════════════════════════════════════════════

class TestQueryItems:
    @patch.object(db_utils, "_get_table")
    def test_returns_items(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": [{"id": "1"}, {"id": "2"}]}
        mock_get_table.return_value = mock_table

        result = query_items("TestTable", "key_condition")
        assert len(result) == 2
        # Verify table.query was called, NOT table.scan
        mock_table.query.assert_called()
        mock_table.scan.assert_not_called()

    @patch.object(db_utils, "_get_table")
    def test_with_gsi(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": [{"id": "1"}]}
        mock_get_table.return_value = mock_table

        query_items("TestTable", "kc", index_name="date-index")
        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs["IndexName"] == "date-index"

    @patch.object(db_utils, "_get_table")
    def test_with_filter(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_get_table.return_value = mock_table

        query_items("TestTable", "kc", filter_expression="category = :c")
        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs["FilterExpression"] == "category = :c"

    @patch.object(db_utils, "_get_table")
    def test_with_limit(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": [{"id": "1"}]}
        mock_get_table.return_value = mock_table

        query_items("TestTable", "kc", limit=10)
        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs["Limit"] == 10

    @patch.object(db_utils, "_get_table")
    def test_descending_order(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_get_table.return_value = mock_table

        query_items("TestTable", "kc", scan_forward=False)
        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs["ScanIndexForward"] is False

    @patch.object(db_utils, "_get_table")
    def test_pagination_fetches_all_pages(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.query.side_effect = [
            {"Items": [{"id": "1"}], "LastEvaluatedKey": {"id": "1"}},
            {"Items": [{"id": "2"}], "LastEvaluatedKey": {"id": "2"}},
            {"Items": [{"id": "3"}]},
        ]
        mock_get_table.return_value = mock_table

        result = query_items("TestTable", "kc")
        assert len(result) == 3
        assert mock_table.query.call_count == 3

    @patch.object(db_utils, "_get_table")
    def test_pagination_respects_limit(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.query.side_effect = [
            {"Items": [{"id": "1"}, {"id": "2"}], "LastEvaluatedKey": {"id": "2"}},
            {"Items": [{"id": "3"}, {"id": "4"}]},
        ]
        mock_get_table.return_value = mock_table

        result = query_items("TestTable", "kc", limit=3)
        assert len(result) == 3

    @patch.object(db_utils, "_get_table")
    def test_empty_result(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_get_table.return_value = mock_table

        result = query_items("TestTable", "kc")
        assert result == []

    @patch.object(db_utils, "_get_table")
    def test_client_error_returns_empty(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.query.side_effect = _make_client_error()
        mock_get_table.return_value = mock_table

        result = query_items("TestTable", "kc")
        assert result == []


# ═══════════════════════════════════════════════════════════════════
# query_by_partition (convenience wrapper)
# ═══════════════════════════════════════════════════════════════════

class TestQueryByPartition:
    @patch.object(db_utils, "_get_table")
    def test_queries_by_user_id(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [{"userId": "u1", "expenseId": "e1"}]
        }
        mock_get_table.return_value = mock_table

        result = query_by_partition("Expenses", "userId", "u1")
        assert len(result) == 1
        # Must use query, not scan
        mock_table.query.assert_called()
        mock_table.scan.assert_not_called()

    @patch.object(db_utils, "_get_table")
    def test_with_gsi(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_get_table.return_value = mock_table

        query_by_partition("Expenses", "userId", "u1", index_name="date-index")
        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs["IndexName"] == "date-index"

    @patch.object(db_utils, "_get_table")
    def test_empty_result(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_get_table.return_value = mock_table

        result = query_by_partition("Expenses", "userId", "nonexistent")
        assert result == []


# ═══════════════════════════════════════════════════════════════════
# update_item
# ═══════════════════════════════════════════════════════════════════

class TestUpdateItem:
    @patch.object(db_utils, "_get_table")
    def test_success_returns_updated_attributes(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.update_item.return_value = {"Attributes": {"id": "1", "name": "updated"}}
        mock_get_table.return_value = mock_table

        result = update_item("TestTable", {"id": "1"}, "SET #n = :v", {":v": "updated"}, {"#n": "name"})
        assert result == {"id": "1", "name": "updated"}

    @patch.object(db_utils, "_get_table")
    def test_passes_expression_names(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.update_item.return_value = {"Attributes": {}}
        mock_get_table.return_value = mock_table

        update_item("TestTable", {"id": "1"}, "SET #s = :v", {":v": "active"}, {"#s": "status"})
        call_kwargs = mock_table.update_item.call_args[1]
        assert call_kwargs["ExpressionAttributeNames"] == {"#s": "status"}

    @patch.object(db_utils, "_get_table")
    def test_without_expression_names(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.update_item.return_value = {"Attributes": {}}
        mock_get_table.return_value = mock_table

        update_item("TestTable", {"id": "1"}, "SET amount = :v", {":v": 100})
        call_kwargs = mock_table.update_item.call_args[1]
        assert "ExpressionAttributeNames" not in call_kwargs

    @patch.object(db_utils, "_get_table")
    def test_client_error_returns_none(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.update_item.side_effect = _make_client_error()
        mock_get_table.return_value = mock_table

        result = update_item("TestTable", {"id": "1"}, "SET x = :v", {":v": 1})
        assert result is None


# ═══════════════════════════════════════════════════════════════════
# delete_item
# ═══════════════════════════════════════════════════════════════════

class TestDeleteItem:
    @patch.object(db_utils, "_get_table")
    def test_success(self, mock_get_table):
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table

        result = delete_item("TestTable", {"id": "1"})
        assert result == {"success": True}
        mock_table.delete_item.assert_called_once_with(Key={"id": "1"})

    @patch.object(db_utils, "_get_table")
    def test_composite_key(self, mock_get_table):
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table

        key = {"userId": "u1", "expenseId": "e1"}
        result = delete_item("Expenses", key)
        assert result == {"success": True}
        mock_table.delete_item.assert_called_once_with(Key=key)

    @patch.object(db_utils, "_get_table")
    def test_client_error(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.delete_item.side_effect = _make_client_error("Not found")
        mock_get_table.return_value = mock_table

        result = delete_item("TestTable", {"id": "1"})
        assert result["success"] is False
        assert "Not found" in result["error"]

    @patch.object(db_utils, "_get_table", side_effect=Exception("connection error"))
    def test_generic_error(self, mock_get_table):
        result = delete_item("TestTable", {"id": "1"})
        assert result["success"] is False


# ═══════════════════════════════════════════════════════════════════
# batch_write_items
# ═══════════════════════════════════════════════════════════════════

class TestBatchWriteItems:
    @patch.object(db_utils, "_get_table")
    def test_success(self, mock_get_table):
        mock_table = MagicMock()
        mock_batch_writer = MagicMock()
        mock_table.batch_writer.return_value.__enter__ = MagicMock(return_value=mock_batch_writer)
        mock_table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_table.return_value = mock_table

        items = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        result = batch_write_items("TestTable", items)
        assert result["success"] is True
        assert result["count"] == 3

    @patch.object(db_utils, "_get_table")
    def test_empty_list(self, mock_get_table):
        mock_table = MagicMock()
        mock_batch_writer = MagicMock()
        mock_table.batch_writer.return_value.__enter__ = MagicMock(return_value=mock_batch_writer)
        mock_table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_table.return_value = mock_table

        result = batch_write_items("TestTable", [])
        assert result["success"] is True
        assert result["count"] == 0

    @patch.object(db_utils, "_get_table")
    def test_client_error(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.batch_writer.side_effect = _make_client_error("Throughput exceeded")
        mock_get_table.return_value = mock_table

        result = batch_write_items("TestTable", [{"id": "1"}])
        assert result["success"] is False


# ═══════════════════════════════════════════════════════════════════
# scan_items (admin only, clearly separated from query)
# ═══════════════════════════════════════════════════════════════════

class TestScanItems:
    @patch.object(db_utils, "_get_table")
    def test_returns_all_items(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": [{"id": "1"}, {"id": "2"}]}
        mock_get_table.return_value = mock_table

        result = scan_items("TestTable")
        assert len(result) == 2

    @patch.object(db_utils, "_get_table")
    def test_with_filter(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": [{"id": "1"}]}
        mock_get_table.return_value = mock_table

        scan_items("TestTable", filter_expression="some_filter")
        call_kwargs = mock_table.scan.call_args[1]
        assert call_kwargs["FilterExpression"] == "some_filter"

    @patch.object(db_utils, "_get_table")
    def test_pagination(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.scan.side_effect = [
            {"Items": [{"id": "1"}], "LastEvaluatedKey": {"id": "1"}},
            {"Items": [{"id": "2"}]},
        ]
        mock_get_table.return_value = mock_table

        result = scan_items("TestTable")
        assert len(result) == 2

    @patch.object(db_utils, "_get_table")
    def test_client_error_returns_empty(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.scan.side_effect = _make_client_error()
        mock_get_table.return_value = mock_table

        result = scan_items("TestTable")
        assert result == []

    @patch.object(db_utils, "_get_table")
    def test_empty_table(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": []}
        mock_get_table.return_value = mock_table

        result = scan_items("TestTable")
        assert result == []


# ═══════════════════════════════════════════════════════════════════
# batch_delete_items
# ═══════════════════════════════════════════════════════════════════

class TestBatchDeleteItems:
    @patch.object(db_utils, "_get_table")
    def test_success(self, mock_get_table):
        mock_table = MagicMock()
        mock_batch_writer = MagicMock()
        mock_table.batch_writer.return_value.__enter__ = MagicMock(return_value=mock_batch_writer)
        mock_table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_table.return_value = mock_table

        keys = [{"userId": "u1", "expenseId": "e1"}, {"userId": "u1", "expenseId": "e2"}]
        result = batch_delete_items("Expenses", keys)
        assert result["success"] is True
        assert result["count"] == 2
        assert mock_batch_writer.delete_item.call_count == 2

    @patch.object(db_utils, "_get_table")
    def test_empty_keys(self, mock_get_table):
        result = batch_delete_items("TestTable", [])
        assert result["success"] is True
        assert result["count"] == 0
        mock_get_table.assert_not_called()

    @patch.object(db_utils, "_get_table")
    def test_client_error(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.batch_writer.side_effect = _make_client_error("Throughput exceeded")
        mock_get_table.return_value = mock_table

        result = batch_delete_items("TestTable", [{"id": "1"}])
        assert result["success"] is False

    @patch.object(db_utils, "_get_table", side_effect=Exception("connection error"))
    def test_generic_error(self, mock_get_table):
        result = batch_delete_items("TestTable", [{"id": "1"}])
        assert result["success"] is False


# ═══════════════════════════════════════════════════════════════════
# Pagination safety limits
# ═══════════════════════════════════════════════════════════════════

class TestPaginationSafety:
    def test_max_pagination_constant_is_reasonable(self):
        """Safety limit should be at least 100 and at most 10000."""
        assert 100 <= MAX_PAGINATION_ITERATIONS <= 10000

    @patch.object(db_utils, "_get_table")
    def test_query_pagination_stops_at_limit(self, mock_get_table):
        """query_items breaks out of infinite pagination after MAX iterations."""
        mock_table = MagicMock()
        # Simulate infinite pagination — every response has LastEvaluatedKey
        mock_table.query.return_value = {
            "Items": [{"id": "x"}],
            "LastEvaluatedKey": {"id": "x"},
        }
        mock_get_table.return_value = mock_table

        result = query_items("TestTable", "kc")
        # Initial call + (MAX-1) paginated calls = MAX items total
        # (break fires at iterations == MAX, before the MAX-th fetch)
        assert len(result) == MAX_PAGINATION_ITERATIONS
        assert mock_table.query.call_count == MAX_PAGINATION_ITERATIONS

    @patch.object(db_utils, "_get_table")
    def test_scan_pagination_stops_at_limit(self, mock_get_table):
        """scan_items breaks out of infinite pagination after MAX iterations."""
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [{"id": "x"}],
            "LastEvaluatedKey": {"id": "x"},
        }
        mock_get_table.return_value = mock_table

        result = scan_items("TestTable")
        assert len(result) == MAX_PAGINATION_ITERATIONS
        assert mock_table.scan.call_count == MAX_PAGINATION_ITERATIONS
