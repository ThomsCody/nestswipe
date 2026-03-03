#!/usr/bin/env bash
set -euo pipefail

SERVER="ubuntu@145.241.161.221"
REMOTE_DIR="/home/ubuntu/nestswipe/deploy"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "==> Ensuring remote directory exists ..."
ssh "${SERVER}" "mkdir -p ${REMOTE_DIR}"

# Upload .env
ENV_FILE="${SCRIPT_DIR}/.env"
if [ -f "$ENV_FILE" ]; then
  echo "==> Uploading deploy/.env ..."
  scp "$ENV_FILE" "${SERVER}:${REMOTE_DIR}/.env"
else
  echo "WARNING: deploy/.env not found — skipping. Copy .env.prod.example and fill in values."
fi

# Upload oauth.json
OAUTH_FILE="${PROJECT_ROOT}/oauth.json"
if [ -f "$OAUTH_FILE" ]; then
  echo "==> Uploading oauth.json ..."
  scp "$OAUTH_FILE" "${SERVER}:${REMOTE_DIR}/oauth.json"
else
  echo "WARNING: oauth.json not found at project root — skipping."
fi

echo "==> Done. Secrets uploaded to ${SERVER}:${REMOTE_DIR}"
