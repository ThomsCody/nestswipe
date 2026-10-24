#!/usr/bin/env bash
# Run on the production VM as root, after the first backup has completed.
# Provisions access only: does not restart or recreate any container.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
[[ $EUID == 0 ]] || { echo 'Run with sudo on the production VM.'; exit 1; }
[[ -s .env ]] || { echo 'Missing deploy/.env'; exit 1; }

# Serialize database maintenance with the production backup job.
[[ -s /var/lib/nestswipe-backup/last-success ]] || {
    echo 'Wait for the first production backup to complete successfully.'
    exit 1
}
exec 9>/home/ubuntu/nestswipe-backups/.backup.lock
flock -n -x 9 || { echo 'Backup is active; retry after it completes.'; exit 1; }

chmod 600 .env
if ! grep -q '^DD_POSTGRES_PASSWORD=' .env; then
    printf '\nDD_POSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 32)" >> .env
fi
DD_POSTGRES_PASSWORD=$(sed -n 's/^DD_POSTGRES_PASSWORD=//p' .env)
[[ $DD_POSTGRES_PASSWORD =~ ^[0-9a-f]{64}$ ]] || {
    echo 'Expected one generated 64-character hexadecimal DD_POSTGRES_PASSWORD.'
    exit 1
}
export DD_POSTGRES_PASSWORD

# Pass the password by environment name, never in arguments or output.
docker compose -f docker-compose.prod.yml exec -T -e DD_POSTGRES_PASSWORD postgres \
    sh -c 'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
SET log_statement = 'none';
SET log_min_duration_statement = -1;
\getenv dd_password DD_POSTGRES_PASSWORD
SELECT 'CREATE ROLE datadog LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'datadog') \gexec
ALTER ROLE datadog WITH LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'dd_password';
ALTER ROLE datadog SET default_transaction_read_only = on;
SELECT format('GRANT CONNECT ON DATABASE %I TO datadog', datname)
FROM pg_database WHERE datname IN (current_database(), 'postgres') \gexec
SQL

for target in application postgres; do
    docker compose -f docker-compose.prod.yml exec -T postgres \
        sh -c 'db=$POSTGRES_DB; [ "$1" = postgres ] && db=postgres; exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$db"' \
        sh "$target" < datadog/postgres.sql
done
echo 'Datadog database access is configured. Containers have not been restarted.'
