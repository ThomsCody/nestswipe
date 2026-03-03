#!/usr/bin/env bash
set -euo pipefail

SERVER="ubuntu@145.241.161.221"
REMOTE_DIR="/home/ubuntu/nestswipe"

echo "==> Syncing project to ${SERVER}:${REMOTE_DIR} ..."
rsync -avz --delete \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '__pycache__' \
  --exclude '.venv' \
  --exclude 'venv' \
  --exclude '*.pyc' \
  --exclude 'frontend/dist' \
  --exclude 'infra/.terraform' \
  --exclude 'infra/*.tfstate' \
  --exclude 'infra/*.tfstate.*' \
  --exclude 'infra/*.tfvars' \
  --exclude 'deploy/.env' \
  --exclude 'deploy/oauth.json' \
  --exclude '.env' \
  --exclude 'oauth.json' \
  --exclude '.DS_Store' \
  ./ "${SERVER}:${REMOTE_DIR}/"

echo "==> Running remote deployment ..."
ssh "${SERVER}" 'sg docker -c "bash /home/ubuntu/nestswipe/deploy/remote-deploy.sh"'
