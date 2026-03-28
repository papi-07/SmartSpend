#!/bin/bash
# SmartSpend — Cleanup Script
# Tears down all AWS resources created by the SAM deployment.
# Usage: ./scripts/cleanup.sh

set -euo pipefail

echo "============================================"
echo "  SmartSpend — Resource Cleanup"
echo "============================================"
echo ""
echo "WARNING: This will delete ALL SmartSpend AWS resources."
echo "         DynamoDB tables, S3 buckets, Lambda functions,"
echo "         API Gateway, Cognito User Pool — everything."
echo ""
read -p "Are you sure? (y/N): " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Aborted."
    exit 0
fi

# Navigate to project root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo ""
echo "Emptying S3 buckets (required before CloudFormation can delete them)..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 rm "s3://smartspend-receipts-${ACCOUNT_ID}" --recursive 2>/dev/null || true
aws s3 rm "s3://smartspend-frontend-${ACCOUNT_ID}" --recursive 2>/dev/null || true

echo ""
echo "Deleting SAM stack..."
sam delete --no-prompts

echo ""
echo "  ✓ All SmartSpend resources deleted."
echo "============================================"
