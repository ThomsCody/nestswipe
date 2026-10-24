#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/nestswipe/deploy

# Check required secrets exist
if [ ! -f .env ]; then
  echo "ERROR: deploy/.env not found. Run setup-secrets.sh first."
  exit 1
fi
if [ ! -f oauth.json ]; then
  echo "ERROR: deploy/oauth.json not found. Run setup-secrets.sh first."
  exit 1
fi

echo "==> Installing backup scripts and schedule ..."
sudo -n bash backup/install-production.sh

# Prevent the scheduled backup from stopping containers during a deployment.
# Downloads also take a shared lock and can continue during deployment.
exec 9< /home/ubuntu/nestswipe-backups/.backup.lock
flock -s -w 300 9 || { echo "ERROR: backup is still running; retry deployment later."; exit 1; }

echo "==> Building containers ..."
docker compose -f docker-compose.prod.yml build

echo "==> Running database migrations ..."
docker compose -f docker-compose.prod.yml run --rm backend \
  alembic upgrade head

echo "==> Starting services ..."
docker compose -f docker-compose.prod.yml up -d

echo "==> Deployment complete!"
docker compose -f docker-compose.prod.yml ps
