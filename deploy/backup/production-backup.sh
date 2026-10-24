#!/usr/bin/env bash
# Installed as root outside the deployment checkout; see README.md.
set -euo pipefail
umask 077
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

PROJECT=/home/ubuntu/nestswipe
DEST=/home/ubuntu/nestswipe-backups
STATE=/var/lib/nestswipe-backup
CERT=/etc/nestswipe-backup/recipient.pem
LOCK=$DEST/.backup.lock
stage=
stopped=()

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }

restart_services() {
    local i container
    for ((i=${#stopped[@]}-1; i>=0; i--)); do
        container=${stopped[$i]}
        docker start "$container" >/dev/null || return 1
        if [[ "$container" == deploy-minio-1 ]]; then
            local ready=false
            for ((attempt=0; attempt<30; attempt++)); do
                if docker exec deploy-postgres-1 wget -q --spider \
                    http://minio:9000/minio/health/live 2>/dev/null; then
                    ready=true
                    break
                fi
                sleep 1
            done
            if [[ "$ready" != true ]]; then
                log 'ERROR: MinIO readiness failed; continuing to restart application.'
            fi
        fi
    done
    stopped=()
}

cleanup() {
    local status=$?
    trap - EXIT HUP INT TERM
    if ((${#stopped[@]})); then
        restart_services || { log 'ERROR: recovery could not restart all services'; status=1; }
    fi
    if [[ -n "$stage" && "$stage" == "$DEST"/.partial.* ]]; then
        rm -rf -- "$stage"
    fi
    if ((status != 0)); then
        log "ERROR: backup failed (exit $status); previous completed backups retained."
        logger -t nestswipe-backup "Backup failed with exit $status" || true
    fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

[[ $EUID == 0 ]] || { log 'Run as root'; exit 1; }
[[ ${1:-} == '' || ${1:-} == --scheduled ]] || exit 2
install -d -m 750 -o root -g ubuntu "$DEST"
install -d -m 700 "$STATE"
touch "$LOCK"
chmod 644 "$LOCK"
exec 9>"$LOCK"
flock -n -x 9 || exit 0

# An hourly cron tick plus a Paris-time gate handles DST and missed Saturdays.
day=$(TZ=Europe/Paris date +%u)
hour=$(TZ=Europe/Paris date +%H)
days=$(((day + 1) % 7))
if ((days == 0 && 10#$hour < 3)); then days=7; fi
cycle=$(TZ=Europe/Paris date -d "$days days ago" +%F)
if [[ ${1:-} == --scheduled && -f "$STATE/last-success" ]] &&
    [[ $(cat "$STATE/last-success") == "$cycle" ]]; then
    exit 0
fi

[[ -s "$CERT" && -s "$PROJECT/deploy/.env" && -s "$PROJECT/deploy/oauth.json" ]]
openssl x509 -in "$CERT" -checkend 604800 -noout >/dev/null
for container in deploy-backend-1 deploy-seloger-browser-1 deploy-minio-1 deploy-postgres-1; do
    [[ $(docker inspect --format '{{.State.Running}}' "$container") == true ]] || {
        log "ERROR: $container is not running; refusing an incomplete backup"
        exit 1
    }
done

volumes=(deploy_minio_data deploy_seloger_browser_profile deploy_frontend_dist)
paths=()
estimated_kb=524288
for volume in "${volumes[@]}"; do
    path=$(docker volume inspect --format '{{.Mountpoint}}' "$volume")
    [[ -d "$path" && "$path" == /var/lib/docker/volumes/*/_data ]]
    paths+=("$path")
    size=$(du -sk "$path" | awk '{print $1}')
    estimated_kb=$((estimated_kb + size * 3))
done
free_kb=$(df -Pk "$DEST" | awk 'NR==2 {print $4}')
((free_kb > estimated_kb)) || { log 'ERROR: insufficient disk space for a safe backup'; exit 1; }

name=nestswipe-$(date -u +%Y%m%dT%H%M%SZ)
[[ ! -e "$DEST/$name" ]]
stage=$(mktemp -d "$DEST/.partial.XXXXXXXX")
mkdir "$stage/payload"
log "Starting $name"

# Quiesce writers before the logical DB snapshot and physical object-store copy.
# Mark each container before stopping it, so even a partial stop is recovered.
for container in deploy-backend-1 deploy-seloger-browser-1 deploy-minio-1; do
    stopped+=("$container")
    docker stop --time 30 "$container" >/dev/null
done
docker exec deploy-postgres-1 sh -c \
    'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
    > "$stage/payload/database.dump"
docker exec deploy-postgres-1 sh -c \
    'exec pg_dumpall -U "$POSTGRES_USER" --globals-only' \
    > "$stage/payload/globals.sql"
[[ -s "$stage/payload/database.dump" && -s "$stage/payload/globals.sql" ]]
docker exec -i deploy-postgres-1 pg_restore --list \
    < "$stage/payload/database.dump" > /dev/null

for ((i=0; i<${#volumes[@]}; i++)); do
    tar -C "${paths[$i]}" -cf "$stage/payload/${volumes[$i]}.tar" .
done
restart_services
log 'Database and volume snapshots captured; production services restarted.'
healthy=false
for ((attempt=0; attempt<12; attempt++)); do
    if curl -fsS --max-time 10 https://nestswipe.freeddns.org/api/v1/health >/dev/null 2>&1; then
        healthy=true
        break
    fi
    sleep 5
done
[[ "$healthy" == true ]] || { log 'ERROR: application health did not recover'; exit 1; }

# This encrypted archive intentionally includes production .env and oauth.json.
tar -C "$PROJECT" \
    --exclude='./.git' --exclude='./backups' --exclude='*/node_modules' \
    --exclude='*/.venv' --exclude='*/venv' --exclude='*/__pycache__' \
    --exclude='./frontend/dist' --exclude='./infra/.terraform' \
    --exclude='*.tfstate*' --exclude='*.tfvars' \
    --exclude='./browser-profile' --exclude='./browser-diagnostics' \
    -czf "$stage/payload/project.tar.gz" .
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}' > "$stage/payload/containers.txt"
docker image ls --digests --format '{{.Repository}}:{{.Tag}}\t{{.Digest}}\t{{.ID}}' \
    > "$stage/payload/images.txt"
cp /usr/local/share/nestswipe-backup/README.md "$stage/payload/RESTORE.md"
printf 'name=%s\ncreated_utc=%s\nhost_kernel=%s\n' "$name" "$(date -u +%FT%TZ)" "$(uname -r)" \
    > "$stage/payload/metadata.txt"
(cd "$stage/payload" && sha256sum ./* > CONTENTS.sha256)

# AES-GCM authenticated encryption; only the Mac has the RSA decryption key.
tar -C "$stage/payload" -czf - . |
    openssl cms -encrypt -binary -aes-256-gcm -stream -outform DER \
        -out "$stage/backup.tar.gz.enc" "$CERT"
rm -rf -- "$stage/payload"
(cd "$stage" && sha256sum backup.tar.gz.enc > SHA256SUMS)
bytes=$(stat -c %s "$stage/backup.tar.gz.enc")
digest=$(sha256sum "$stage/backup.tar.gz.enc" | awk '{print $1}')
printf '%s %s %s\n' "$name" "$digest" "$bytes" > "$stage/manifest.txt"
chmod 750 "$stage"
chmod 640 "$stage"/*
chown -R root:ubuntu "$stage"
mv -- "$stage" "$DEST/$name"
stage=

# Only this exact naming scheme is eligible for retention pruning.
completed=()
shopt -s nullglob
for path in "$DEST"/nestswipe-*; do
    [[ -d "$path" && ! -L "$path" && ${path##*/} =~ ^nestswipe-[0-9]{8}T[0-9]{6}Z$ ]] || continue
    [[ -s "$path/backup.tar.gz.enc" && -s "$path/SHA256SUMS" ]] || continue
    completed+=("$path")
done
for ((i=0; i<${#completed[@]}-2; i++)); do
    rm -rf -- "${completed[$i]}"
done
printf '%s\n' "$cycle" > "$STATE/last-success.tmp"
mv "$STATE/last-success.tmp" "$STATE/last-success"
log "Completed $name ($bytes encrypted bytes); keeping the newest two backups."
