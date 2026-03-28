"""
SmartSpend — DynamoDB Helper Utilities
======================================
Provides reusable CRUD functions for all DynamoDB operations.
Uses boto3.resource('dynamodb') for cleaner high-level syntax.
All functions handle exceptions gracefully and return standardized responses.

Used by all Lambda functions via the shared CommonLayer.
"""

import os
import logging
import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Module-level DynamoDB resource — reused across warm Lambda invocations
_dynamodb = None

# Safety limit: max pagination iterations to prevent infinite loops
# 1000 pages × ~1 MB each ≈ 1 GB — more than enough for any user's data
MAX_PAGINATION_ITERATIONS = 1000


def _get_dynamodb():
    """Get or create a cached DynamoDB resource."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource(
            "dynamodb",
            region_name=os.environ.get("REGION", "us-east-1"),
        )
    return _dynamodb


def _get_table(table_name):
    """Get a DynamoDB Table object by name."""
    return _get_dynamodb().Table(table_name)


def put_item(table_name, item):
    """
    Put an item into a DynamoDB table.

    Args:
        table_name: Name of the DynamoDB table.
        item: Dict of attribute name-value pairs.

    Returns:
        dict: {"success": True} on success, {"success": False, "error": str} on failure.
    """
    try:
        table = _get_table(table_name)
        table.put_item(Item=item)
        return {"success": True}
    except ClientError as e:
        logger.error("put_item failed on %s: %s", table_name, e.response["Error"]["Message"])
        return {"success": False, "error": e.response["Error"]["Message"]}
    except Exception as e:
        logger.error("put_item unexpected error on %s: %s", table_name, str(e))
        return {"success": False, "error": str(e)}


def get_item(table_name, key):
    """
    Get a single item from a DynamoDB table by primary key.

    Args:
        table_name: Name of the DynamoDB table.
        key: Dict with partition key (and sort key if applicable).

    Returns:
        The item dict if found, None if not found, or {"success": False, "error": str} on failure.
    """
    try:
        table = _get_table(table_name)
        response = table.get_item(Key=key)
        return response.get("Item")
    except ClientError as e:
        logger.error("get_item failed on %s: %s", table_name, e.response["Error"]["Message"])
        return None
    except Exception as e:
        logger.error("get_item unexpected error on %s: %s", table_name, str(e))
        return None


def query_items(table_name, key_condition, index_name=None, filter_expression=None,
                limit=None, scan_forward=True):
    """
    Query items from a DynamoDB table using a key condition expression.

    Args:
        table_name: Name of the DynamoDB table.
        key_condition: A boto3 Key condition expression (e.g., Key('userId').eq('abc')).
        index_name: Optional GSI name to query.
        filter_expression: Optional filter expression applied after the query.
        limit: Max number of items to return.
        scan_forward: True for ascending sort key order, False for descending.

    Returns:
        List of item dicts, or empty list on failure.
    """
    try:
        table = _get_table(table_name)
        kwargs = {
            "KeyConditionExpression": key_condition,
            "ScanIndexForward": scan_forward,
        }
        if index_name:
            kwargs["IndexName"] = index_name
        if filter_expression:
            kwargs["FilterExpression"] = filter_expression
        if limit:
            kwargs["Limit"] = limit

        items = []
        response = table.query(**kwargs)
        items.extend(response.get("Items", []))

        # Handle pagination with safety limit to prevent infinite loops
        iterations = 0
        while "LastEvaluatedKey" in response:
            iterations += 1
            if iterations >= MAX_PAGINATION_ITERATIONS:
                logger.warning(
                    "query_items on %s hit max pagination limit (%d iterations, %d items)",
                    table_name, iterations, len(items),
                )
                break
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
            response = table.query(**kwargs)
            items.extend(response.get("Items", []))
            if limit and len(items) >= limit:
                items = items[:limit]
                break

        return items
    except ClientError as e:
        logger.error("query_items failed on %s: %s", table_name, e.response["Error"]["Message"])
        return []
    except Exception as e:
        logger.error("query_items unexpected error on %s: %s", table_name, str(e))
        return []


def update_item(table_name, key, update_expression, expression_values,
                expression_names=None):
    """
    Update an item in a DynamoDB table.

    Args:
        table_name: Name of the DynamoDB table.
        key: Dict with partition key (and sort key if applicable).
        update_expression: DynamoDB update expression string.
        expression_values: Dict of expression attribute values.
        expression_names: Optional dict of expression attribute names.

    Returns:
        Updated item attributes dict, or None on failure.
    """
    try:
        table = _get_table(table_name)
        kwargs = {
            "Key": key,
            "UpdateExpression": update_expression,
            "ExpressionAttributeValues": expression_values,
            "ReturnValues": "ALL_NEW",
        }
        if expression_names:
            kwargs["ExpressionAttributeNames"] = expression_names

        response = table.update_item(**kwargs)
        return response.get("Attributes")
    except ClientError as e:
        logger.error("update_item failed on %s: %s", table_name, e.response["Error"]["Message"])
        return None
    except Exception as e:
        logger.error("update_item unexpected error on %s: %s", table_name, str(e))
        return None


def delete_item(table_name, key):
    """
    Delete an item from a DynamoDB table.

    Args:
        table_name: Name of the DynamoDB table.
        key: Dict with partition key (and sort key if applicable).

    Returns:
        dict: {"success": True} on success, {"success": False, "error": str} on failure.
    """
    try:
        table = _get_table(table_name)
        table.delete_item(Key=key)
        return {"success": True}
    except ClientError as e:
        logger.error("delete_item failed on %s: %s", table_name, e.response["Error"]["Message"])
        return {"success": False, "error": e.response["Error"]["Message"]}
    except Exception as e:
        logger.error("delete_item unexpected error on %s: %s", table_name, str(e))
        return {"success": False, "error": str(e)}


def query_by_partition(table_name, partition_key, partition_value,
                       index_name=None, filter_expression=None,
                       limit=None, scan_forward=True):
    """
    Convenience wrapper: query all items for a given partition key value.
    This is the preferred method for fetching user-scoped data (e.g., all
    expenses for a userId). Always uses Query, never Scan.

    Args:
        table_name: Name of the DynamoDB table.
        partition_key: Name of the partition key attribute (e.g., "userId").
        partition_value: Value to match (e.g., "user-123").
        index_name: Optional GSI name.
        filter_expression: Optional post-query filter.
        limit: Max items to return.
        scan_forward: True for ascending, False for descending.

    Returns:
        List of item dicts, or empty list on failure.
    """
    key_condition = Key(partition_key).eq(partition_value)
    return query_items(
        table_name,
        key_condition,
        index_name=index_name,
        filter_expression=filter_expression,
        limit=limit,
        scan_forward=scan_forward,
    )


def batch_write_items(table_name, items):
    """
    Batch-write multiple items to a DynamoDB table using batch_writer.
    More efficient than calling put_item in a loop — batches up to 25
    items per request automatically.

    Args:
        table_name: Name of the DynamoDB table.
        items: List of item dicts to write.

    Returns:
        dict: {"success": True, "count": int} on success,
              {"success": False, "error": str} on failure.
    """
    try:
        table = _get_table(table_name)
        with table.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)
        return {"success": True, "count": len(items)}
    except ClientError as e:
        logger.error("batch_write_items failed on %s: %s", table_name, e.response["Error"]["Message"])
        return {"success": False, "error": e.response["Error"]["Message"]}
    except Exception as e:
        logger.error("batch_write_items unexpected error on %s: %s", table_name, str(e))
        return {"success": False, "error": str(e)}


def batch_delete_items(table_name, keys):
    """
    Batch-delete multiple items from a DynamoDB table using batch_writer.
    More efficient and safer than deleting in a manual loop — boto3's
    batch_writer handles retries and 25-item batching automatically.

    Args:
        table_name: Name of the DynamoDB table.
        keys: List of key dicts (each with partition key + sort key).

    Returns:
        dict: {"success": True, "count": int} on success,
              {"success": False, "error": str} on failure.
    """
    try:
        if not keys:
            return {"success": True, "count": 0}

        table = _get_table(table_name)
        with table.batch_writer() as batch:
            for key in keys:
                batch.delete_item(Key=key)
        return {"success": True, "count": len(keys)}
    except ClientError as e:
        logger.error("batch_delete_items failed on %s: %s", table_name, e.response["Error"]["Message"])
        return {"success": False, "error": e.response["Error"]["Message"]}
    except Exception as e:
        logger.error("batch_delete_items unexpected error on %s: %s", table_name, str(e))
        return {"success": False, "error": str(e)}


def scan_items(table_name, filter_expression=None):
    """
    Scan all items in a DynamoDB table. Use sparingly — scans are expensive.
    Intended for admin/analytics queries on small tables.

    Args:
        table_name: Name of the DynamoDB table.
        filter_expression: Optional filter expression to apply.

    Returns:
        List of item dicts, or empty list on failure.
    """
    try:
        table = _get_table(table_name)
        kwargs = {}
        if filter_expression:
            kwargs["FilterExpression"] = filter_expression

        items = []
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))

        # Handle pagination with safety limit to prevent infinite loops
        iterations = 0
        while "LastEvaluatedKey" in response:
            iterations += 1
            if iterations >= MAX_PAGINATION_ITERATIONS:
                logger.warning(
                    "scan_items on %s hit max pagination limit (%d iterations, %d items)",
                    table_name, iterations, len(items),
                )
                break
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
            response = table.scan(**kwargs)
            items.extend(response.get("Items", []))

        return items
    except ClientError as e:
        logger.error("scan_items failed on %s: %s", table_name, e.response["Error"]["Message"])
        return []
    except Exception as e:
        logger.error("scan_items unexpected error on %s: %s", table_name, str(e))
        return []
