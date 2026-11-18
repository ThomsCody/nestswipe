#!/usr/bin/env bash
set -euo pipefail

SERVER="${NESTSWIPE_SERVER:-ubuntu@145.241.161.221}"
REMOTE_DIR="/home/ubuntu/nestswipe"
GIT_REVISION="$(git rev-parse HEAD)"
command -v dd-auth >/dev/null || { echo 'Install dd-auth before deploying (required for production image scans).' >&2; exit 1; }

echo "==> Syncing project to ${SERVER}:${REMOTE_DIR} ..."
rsync -avz --delete \
  --exclude '.git' \
  --exclude '/backups/' \
  --exclude 'node_modules' \
  --exclude '__pycache__' \
  --exclude '.venv' \
  --exclude 'venv' \
  --exclude '*.pyc' \
  --exclude 'frontend/dist' \
  --exclude '/infra/' \
  --exclude 'deploy/.env' \
  --exclude 'deploy/oauth.json' \
  --exclude '/deploy/secrets/' \
  --exclude '.env' \
  --exclude '.env.reboot-key.tmp' \
  --exclude 'oauth.json' \
  --exclude '.DS_Store' \
  ./ "${SERVER}:${REMOTE_DIR}/"

# Keep the VM credential restricted to monitor reads; administrative keys stay local.
python3 deploy/security/provision-reboot-key.py --provision \
  --env-file "${NESTSWIPE_ENV_FILE:-deploy/.env}" --server "$SERVER"

echo "==> Checking host monitoring and deploying application containers ..."
# The local commit must be expanded here: the remote checkout has no .git directory.
# shellcheck disable=SC2029
ssh "${SERVER}" "sg docker -c 'GIT_REVISION=${GIT_REVISION} bash /home/ubuntu/nestswipe/deploy/remote-deploy.sh'"

echo "==> Scanning the exact deployed images and linking their Dockerfiles ..."
NESTSWIPE_SERVER="$SERVER" dd-auth --force-app-key --org-uuid cd1824fa-b069-11ee-b818-da7ad0900002 \
  --site datadoghq.com -- bash deploy/security/scan-production-images.sh
