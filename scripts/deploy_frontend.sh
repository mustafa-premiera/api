#!/usr/bin/env bash
# Build the SPA, sync it to S3 (config.json is managed by Terraform) and invalidate CloudFront.
set -euo pipefail
cd "$(dirname "$0")/.."
[ "${GITHUB_ACTIONS:-}" = "true" ] || export AWS_PROFILE="${AWS_PROFILE:-manara-free}"

BUCKET=$(terraform -chdir=infra output -raw frontend_bucket)
DIST_ID=$(terraform -chdir=infra output -raw distribution_id)

npm --prefix frontend ci
npm --prefix frontend run build

aws s3 sync frontend/dist "s3://$BUCKET" --delete --exclude config.json
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths '/*'
