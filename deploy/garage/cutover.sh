#!/usr/bin/env bash
# Run on the production VM only after local rehearsal and code synchronization.
# Leaves ingress and scheduled jobs paused for operator smoke tests.
set -euo pipefail
umask 077
PROJECT=${NESTSWIPE_PROJECT:-/home/ubuntu/nestswipe}
EVIDENCE=${NESTSWIPE_MIGRATION_EVIDENCE:-/home/ubuntu/nestswipe-backups/garage-migration}
LOCK=${NESTSWIPE_BACKUP_LOCK:-/home/ubuntu/nestswipe-backups/.backup.lock}
COMPOSE_FILE=${NESTSWIPE_COMPOSE_FILE:-docker-compose.prod.yml}
STACK=${NESTSWIPE_STACK:-deploy}
cd "$PROJECT/deploy"
[[ ! -e "$EVIDENCE" ]] || { echo 'Use a new evidence directory; refusing to overwrite a migration.'; exit 1; }
exec 9<"$LOCK"
flock -x -w 300 9 || { echo 'Backup lock unavailable'; exit 1; }
mkdir -m 700 "$EVIDENCE"
compose=(docker compose -p "$STACK" -f "$COMPOSE_FILE")
# Preserve the running image before build retags the service image.
old_backend="$STACK-before-garage:$(date -u +%Y%m%dT%H%M%SZ)"
docker image tag "$(docker inspect --format '{{.Image}}' "$STACK-backend-1")" "$old_backend"
printf '%s\n' "$old_backend" > "$EVIDENCE/previous-backend-image"
# All dependencies/builds must succeed before disrupting the running application.
python3 garage/provision.py --directory secrets
"${compose[@]}" build backend
"${compose[@]}" up -d --wait garage
python3 garage/init.py --container "$STACK-garage-1" --directory secrets
paused=false
rollback() {
    status=$?
    trap - EXIT
    if [[ "$paused" == true && $status != 0 ]]; then
        echo 'Migration failed; restoring MinIO backend with writers still paused.'
        docker start "$STACK-minio-1" >/dev/null
        "${compose[@]}" -f garage/rollback.yml up -d --no-deps backend
        echo 'Inspect backend health before enabling scheduler and restarting caddy.'
    fi
    exit "$status"
}
trap rollback EXIT
paused=true
docker stop --time 60 "$STACK-caddy-1" "$STACK-backend-1" >/dev/null
# Snapshot DB references and database while every application writer is stopped.
docker exec "$STACK-postgres-1" sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$EVIDENCE/database.dump"
docker exec "$STACK-postgres-1" sh -c 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT coalesce(json_agg(s3_key), '\''[]'\''::json) FROM listing_photos"' > "$EVIDENCE/photo-keys.json"
docker stop --time 60 "$STACK-minio-1" >/dev/null
# Physical source snapshot plus untouched original volume provide rollback copies.
docker run --rm --user 0 -v "${STACK}_minio_data":/source:ro -v "$EVIDENCE:/evidence" "$old_backend" sh -c 'tar -C /source -cf /evidence/minio-data.tar .'
docker start "$STACK-minio-1" >/dev/null
for ((attempt=0; attempt<30; attempt++)); do
    if docker exec "$STACK-postgres-1" wget -q --spider http://minio:9000/minio/health/live; then break; fi
    sleep 1
done
docker run --rm --user 0 --network "${STACK}_default" \
    -v "$PROJECT/deploy/garage:/migration:ro" -v "$PROJECT/deploy/secrets:/secrets:ro" \
    -v "$EVIDENCE:/evidence" "$old_backend" \
    python /migration/migrate.py \
    --source-endpoint minio:9000 --source-access-key-file /secrets/minio_root_user \
    --source-secret-key-file /secrets/minio_root_password --target-endpoint garage:3900 \
    --target-access-key-file /secrets/garage_access_key --target-secret-key-file /secrets/garage_secret_key \
    --report /evidence/manifest.json
python3 - "$EVIDENCE" <<'PY'
import json
import pathlib
import sys
p = pathlib.Path(sys.argv[1])
manifest = json.loads((p / "manifest.json").read_text())
keys = {obj["key"] for bucket in manifest["buckets"] for obj in bucket["objects"]}
references = json.loads((p / "photo-keys.json").read_text())
missing = sorted(set(references) - keys)
(p / "reference-check.json").write_text(json.dumps({"references": len(references), "missing_before_and_after": missing}))
# Existing missing images are recorded; the full source key set is preserved.
print(f'DB references: {len(references)}; pre-existing missing keys: {len(missing)}')
PY
SCHEDULER_ENABLED=false "${compose[@]}" up -d --no-deps --wait backend
paused=false
printf 'COPY VERIFIED. Backend is running with scheduler paused; caddy remains stopped.\n'
printf 'Evidence: %s\n' "$EVIDENCE"
printf 'Validate images and controlled upload/delete before reopening.\n'
