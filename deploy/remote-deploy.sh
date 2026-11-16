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

# Agent upgrades and configuration are managed independently through Fleet.
# Check before touching application containers; never reinstall/reset the Agent.
bash datadog/check-host-agent.sh

# Materialize the existing credentials without printing or rotating them.
# This must happen before any Compose command starts replacement containers.
python3 provision-secrets.py --env-file .env --output-dir secrets

python3 garage/provision.py --directory secrets

# An ordinary deploy must never switch an existing installation to an empty store.
if docker inspect deploy-minio-1 >/dev/null 2>&1 && [[ ! -s secrets/garage-migration-verified ]]; then
  echo "ERROR: complete the historical Garage migration and validate images before ordinary deployment."
  exit 1
fi

echo "==> Installing backup scripts and schedule ..."
sudo -n bash backup/install-production.sh

# Prevent the scheduled backup from stopping containers during a deployment.
# Downloads also take a shared lock and can continue during deployment.
exec 9< /home/ubuntu/nestswipe-backups/.backup.lock
flock -s -w 300 9 || { echo "ERROR: backup is still running; retry deployment later."; exit 1; }
sudo -n bash security/install-monitoring.sh

echo "==> Building containers ..."
docker compose -f docker-compose.prod.yml build

echo "==> Preparing Garage ..."
docker compose -f docker-compose.prod.yml up -d --wait garage
python3 garage/init.py --directory secrets --bucket "${STORAGE_BUCKET:-listing-photos}"

echo "==> Running database migrations ..."
docker compose -f docker-compose.prod.yml run --rm backend \
  alembic upgrade head

echo "==> Starting services ..."
docker compose -f docker-compose.prod.yml up -d

bash datadog/check-host-agent.sh

echo "==> Deployment complete!"
docker compose -f docker-compose.prod.yml ps
