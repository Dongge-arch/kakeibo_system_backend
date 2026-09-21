#!/usr/bin/env bash
set -euo pipefail

# Japan test environment only. Production in Singapore requires a separate explicit operation.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_DIR="${FRONTEND_DIR:-$(cd "$ROOT_DIR/../kakeibo_system_frontend/frontend-react" && pwd)}"
REGION="ap-northeast-1"
STACK_NAME="${STACK_NAME:-home-kakeibo-api-jp}"
LAYER_NAME="${LAYER_NAME:-home-kakeibo-layer-jp}"
DIST_DIR="$ROOT_DIR/dist_lambda"
STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT
LAYER_DIR="$STAGE_DIR/layer/python"

for name in KAKEIBO_DATABASE_URL KAKEIBO_JWT_SECRET KAKEIBO_API_KEY; do
  if [[ -z "${!name:-}" ]]; then
    printf 'Missing required environment variable: %s\n' "$name" >&2
    exit 1
  fi
done

command -v aws >/dev/null
command -v sam >/dev/null
command -v npm >/dev/null
command -v zip >/dev/null
command -v rsync >/dev/null

mkdir -p "$LAYER_DIR"
"${PYTHON_BIN:-python3}" -m pip install -q -r "$ROOT_DIR/lambda_api/requirements-layer.txt" \
  --target "$LAYER_DIR" --platform manylinux2014_aarch64 --implementation cp \
  --python-version 3.12 --only-binary=:all: --upgrade
rsync -a --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' \
  "$ROOT_DIR/src/" "$LAYER_DIR/src/"
"${PYTHON_BIN:-python3}" "$ROOT_DIR/tools/package_lambda_handlers.py"

(cd "$STAGE_DIR/layer" && zip -q -r "$STAGE_DIR/home-kakeibo-layer-jp.zip" python)
LAYER_ARN="$(aws lambda publish-layer-version --region "$REGION" --layer-name "$LAYER_NAME" \
  --zip-file "fileb://$STAGE_DIR/home-kakeibo-layer-jp.zip" \
  --compatible-runtimes python3.12 --compatible-architectures arm64 \
  --query LayerVersionArn --output text)"

sam deploy --template-file "$ROOT_DIR/template.yaml" --stack-name "$STACK_NAME" \
  --region "$REGION" --resolve-s3 --capabilities CAPABILITY_IAM \
  --no-confirm-changeset --no-fail-on-empty-changeset \
  --parameter-overrides \
  "HomeKakeiboLayerArn=$LAYER_ARN" \
  "KakeiboDatabaseUrl=$KAKEIBO_DATABASE_URL" \
  "KakeiboDatabaseInitialize=false" \
  "KakeiboJwtSecret=$KAKEIBO_JWT_SECRET" \
  "KakeiboApiKey=$KAKEIBO_API_KEY" \
  "FrontendCorsOrigin=${FRONTEND_CORS_ORIGIN:-*}" \
  "SupplierLogoBucketName=${SUPPLIER_LOGO_S3_BUCKET:-}" \
  "EnableScheduledAutoInput=false"

API_URL="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue | [0]" --output text)"
printf 'Japan API: %s\n' "$API_URL"

if [[ -n "${FRONTEND_S3_URI:-}" ]]; then
  (cd "$FRONTEND_DIR" && VITE_API_BASE_URL="$API_URL" VITE_API_KEY="$KAKEIBO_API_KEY" npm run build)
  aws s3 sync "$FRONTEND_DIR/dist/" "$FRONTEND_S3_URI" --region "$REGION" --delete
  if [[ -n "${CLOUDFRONT_DISTRIBUTION_ID:-}" ]]; then
    aws cloudfront create-invalidation --distribution-id "$CLOUDFRONT_DISTRIBUTION_ID" --paths '/*' >/dev/null
  fi
fi
