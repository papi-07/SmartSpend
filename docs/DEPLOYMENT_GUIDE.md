# SmartSpend — Deployment Guide

Step-by-step instructions to deploy SmartSpend from scratch on AWS Free Tier.

## Prerequisites

1. **AWS Account** with Free Tier eligibility
2. **AWS CLI** configured (`aws configure`)
3. **AWS SAM CLI** installed (`brew install aws-sam-cli` or [install guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html))
4. **Node.js 18+** and **npm** (`brew install node`)
5. **Python 3.12** (for Lambda runtime compatibility)
6. **Git** (`brew install git`)

## Step 1: Clone the Repository

```bash
git clone <repository-url>
cd SmartSpend
```

## Step 2: Deploy the Backend

### Build the SAM application:
```bash
sam build
```

### Deploy (first time — guided):
```bash
sam deploy --guided
```

Answer the prompts:
- **Stack Name:** `smartspend`
- **AWS Region:** `ap-south-1` (Mumbai) or your preferred region
- **Confirm changes before deploy:** `Y`
- **Allow SAM CLI IAM role creation:** `Y`
- **Disable rollback:** `N`
- **Save arguments to samconfig.toml:** `Y`

### Subsequent deploys:
```bash
sam build && sam deploy
```

### Note the outputs:
```
Key                 ApiUrl
Value               https://xxxxx.execute-api.ap-south-1.amazonaws.com/prod/

Key                 UserPoolId
Value               ap-south-1_XXXXXXXXX

Key                 UserPoolClientId
Value               xxxxxxxxxxxxxxxxxxxxxxxxxx

Key                 FrontendUrl
Value               http://smartspend-frontend-xxxx.s3-website.ap-south-1.amazonaws.com
```

## Step 3: Configure the Frontend

### Install dependencies:
```bash
cd frontend
npm install
```

### Create `.env` file with your backend values:
```bash
cp .env.example .env
```

Edit `frontend/.env`:
```env
VITE_API_URL=https://xxxxx.execute-api.ap-south-1.amazonaws.com/prod
VITE_COGNITO_USER_POOL_ID=ap-south-1_XXXXXXXXX
VITE_COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
VITE_AWS_REGION=ap-south-1
```

### Test locally:
```bash
npm run dev
```

Open `http://localhost:5173` — you should see the login page.

## Step 4: Build and Deploy Frontend to S3

### Build production bundle:
```bash
npm run build
```

### Upload to S3:
```bash
# Get bucket name from SAM outputs
BUCKET=$(aws cloudformation describe-stacks \
  --stack-name smartspend \
  --query 'Stacks[0].Outputs[?OutputKey==`FrontendUrl`].OutputValue' \
  --output text | sed 's|http://||;s|\.s3-website.*||')

# Sync build output
aws s3 sync dist/ s3://$BUCKET/ --delete

# Set correct content types
aws s3 cp s3://$BUCKET/ s3://$BUCKET/ \
  --recursive \
  --exclude "*" \
  --include "*.js" \
  --content-type "application/javascript" \
  --metadata-directive REPLACE

aws s3 cp s3://$BUCKET/ s3://$BUCKET/ \
  --recursive \
  --exclude "*" \
  --include "*.css" \
  --content-type "text/css" \
  --metadata-directive REPLACE
```

## Step 5: Create a Test User

```bash
# Sign up
aws cognito-idp sign-up \
  --client-id <UserPoolClientId> \
  --username testuser@example.com \
  --password "TestPass123!" \
  --user-attributes Name=email,Value=testuser@example.com \
  --region ap-south-1

# Confirm (admin)
aws cognito-idp admin-confirm-sign-up \
  --user-pool-id <UserPoolId> \
  --username testuser@example.com \
  --region ap-south-1
```

## Step 6: Load Seed Data (Optional)

```bash
pip3 install boto3
python3 scripts/seed_data.py
```

## Step 7: Run E2E Tests

```bash
python3 scripts/e2e_test.py
```

Expected output: `✅ ALL E2E TESTS PASSED`

## Step 8: Subscribe to SNS Alerts (Optional)

```bash
SNS_ARN=$(aws cloudformation describe-stacks \
  --stack-name smartspend \
  --query 'Stacks[0].Outputs[?OutputKey==`SnsTopicArn`].OutputValue' \
  --output text)

aws sns subscribe \
  --topic-arn $SNS_ARN \
  --protocol email \
  --notification-endpoint your-email@example.com \
  --region ap-south-1
```

Confirm the subscription via the email you receive.

## Troubleshooting

### Lambda errors
```bash
# View CloudWatch logs for a specific function
aws logs tail /aws/lambda/SmartSpend-CreateExpense --follow --region ap-south-1
```

### API Gateway 403/401 errors
- Verify the Cognito token is valid and not expired
- Check that `Authorization: Bearer <token>` header is set
- Ensure the Cognito User Pool ID matches the API Gateway authorizer

### Frontend blank page
- Check browser console for errors
- Verify `.env` file has correct values
- Ensure `define: { global: 'globalThis' }` is in `vite.config.js`

### CORS errors
- All Lambda responses include CORS headers via `response_utils.py`
- API Gateway has CORS configured in `template.yaml`
- OPTIONS preflight is handled without authorization

## Cost Estimation (Free Tier)

| Service | Free Tier Limit | Expected Usage | Cost |
|---------|----------------|----------------|------|
| Lambda | 1M requests/month | ~500 | $0.00 |
| DynamoDB | 25 RCU/WCU | On-demand, minimal | $0.00 |
| S3 | 5 GB storage | <100 MB | $0.00 |
| API Gateway | 1M calls/month | ~500 | $0.00 |
| Cognito | 50,000 MAU | 1-5 users | $0.00 |
| Textract | 1,000 pages/month | <50 | $0.00 |
| SNS | 1,000 emails/month | <20 | $0.00 |
| **Total** | | | **$0.00** |

## Cleanup

To delete all resources:
```bash
# Empty S3 buckets first
aws s3 rm s3://smartspend-receipts-<account>-<region> --recursive
aws s3 rm s3://smartspend-frontend-<account>-<region> --recursive

# Delete CloudFormation stack
aws cloudformation delete-stack --stack-name smartspend --region ap-south-1
```
