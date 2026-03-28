#!/bin/bash
# SmartSpend — Full Deployment Script
# Builds and deploys the SAM application to AWS.
# Usage: ./scripts/deploy.sh

set -euo pipefail

echo "============================================"
echo "  SmartSpend — SAM Build & Deploy"
echo "============================================"

# Navigate to project root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo ""
echo "[1/3] Validating SAM template..."
sam validate --lint
echo "  ✓ Template is valid."

echo ""
echo "[2/3] Building SAM application..."
sam build
echo "  ✓ Build successful."

echo ""
echo "[3/3] Deploying to AWS..."
sam deploy --guided
echo ""
echo "  ✓ Deployment complete!"
echo ""
echo "============================================"
echo "  Next steps:"
echo "  1. Note the API Gateway URL from the outputs above."
echo "  2. Update frontend/src/config.js with the API URL."
echo "  3. Build and deploy the frontend:"
echo "     cd frontend && npm install && npm run build"
echo "     aws s3 sync dist/ s3://smartspend-frontend-<ACCOUNT_ID>"
echo "============================================"
