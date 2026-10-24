#!/usr/bin/env bash
set -euo pipefail
umask 077
export PATH=/usr/bin:/bin:/usr/sbin:/sbin

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
DEST=${NESTSWIPE_BACKUP_DIR:-$ROOT/backups}
SSH=${NESTSWIPE_SSH_BIN:-/usr/bin/ssh}
HOST=${NESTSWIPE_BACKUP_HOST:-ubuntu@145.241.161.221}
stage=
locked=false
log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }
cleanup() {
    local status=$?
    trap - EXIT HUP INT TERM
    if [[ -n "$stage" && "$stage" == "$DEST"/.partial.* ]]; then rm -rf -- "$stage"; fi
    if [[ "$locked" == true ]]; then rm -rf -- "$DEST/.download.lock"; fi
    if ((status)); then log "ERROR: download failed (exit $status); completed backups retained."; fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
[[ ${1:-} == '' || ${1:-} == --scheduled ]] || exit 2
mkdir -p "$DEST"
chmod 700 "$DEST"

# Keep the weekly Paris deadline even if the Mac travels or sleeps at 22:00.
day=$(TZ=Europe/Paris date +%u)
hour=$(TZ=Europe/Paris date +%H)
days=$((day - 1))
if ((days == 0 && 10#$hour < 22)); then days=7; fi
cycle=$(TZ=Europe/Paris date -v-"${days}"d +%F)
if [[ ${1:-} == --scheduled && -f "$DEST/.last-success" ]] &&
    [[ $(cat "$DEST/.last-success") == "$cycle" ]]; then
    exit 0
fi

if ! mkdir "$DEST/.download.lock" 2>/dev/null; then
    oldpid=$(cat "$DEST/.download.lock/pid" 2>/dev/null || true)
    if [[ "$oldpid" =~ ^[0-9]+$ ]] && kill -0 "$oldpid" 2>/dev/null; then exit 0; fi
    # A just-created lock may not have its PID yet. Only reclaim old locks.
    modified=$(stat -f %m "$DEST/.download.lock")
    (($(date +%s) - modified > 3600)) || exit 0
    rm -rf -- "$DEST/.download.lock"
    mkdir "$DEST/.download.lock"
fi
locked=true
echo "$$" > "$DEST/.download.lock/pid"
key=$DEST/.keys/download_ed25519
known_hosts=$DEST/.keys/known_hosts
[[ -s "$key" && -s "$known_hosts" ]]
ssh_options=(-F /dev/null -i "$key" -o IdentityAgent=none -o IdentitiesOnly=yes
    -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known_hosts"
    -o ConnectTimeout=20 -o ServerAliveInterval=30 -o ServerAliveCountMax=3)
record=$("$SSH" "${ssh_options[@]}" "$HOST" latest)
[[ "$record" =~ ^(nestswipe-[0-9]{8}T[0-9]{6}Z)\ ([a-f0-9]{64})\ ([0-9]+)$ ]] || {
    log 'ERROR: invalid backup manifest'; exit 1;
}
name=${BASH_REMATCH[1]}
expected=${BASH_REMATCH[2]}
bytes=${BASH_REMATCH[3]}
((bytes > 0))

# Do not mark a missed production backup as a successful weekly download.
stamp=${name#nestswipe-}
backup_epoch=$(TZ=UTC date -j -f '%Y%m%dT%H%M%SZ' "$stamp" +%s)
if [[ ${1:-} == --scheduled ]] && (($(date +%s) - backup_epoch > 604800)); then
    log 'ERROR: latest production backup is more than seven days old'; exit 1
fi

if [[ -d "$DEST/$name" ]]; then
    actual=$(shasum -a 256 "$DEST/$name/backup.tar.gz.enc" | awk '{print $1}')
    [[ "$actual" == "$expected" ]] || { log 'ERROR: existing local backup checksum differs'; exit 1; }
    log "$name is already downloaded and verified."
else
    free_kb=$(df -Pk "$DEST" | awk 'NR==2 {print $4}')
    ((free_kb * 1024 > bytes + 104857600)) || { log 'ERROR: insufficient local disk space'; exit 1; }
    stage=$(mktemp -d "$DEST/.partial.XXXXXXXX")
    log "Downloading $name ($bytes encrypted bytes)"
    "$SSH" "${ssh_options[@]}" "$HOST" "fetch $name" > "$stage/backup.tar.gz.enc"
    [[ $(stat -f %z "$stage/backup.tar.gz.enc") == "$bytes" ]]
    actual=$(shasum -a 256 "$stage/backup.tar.gz.enc" | awk '{print $1}')
    [[ "$actual" == "$expected" ]] || { log 'ERROR: download checksum mismatch'; exit 1; }
    printf '%s  backup.tar.gz.enc\n' "$expected" > "$stage/SHA256SUMS"
    printf '%s\n' "$record" > "$stage/manifest.txt"
    mv -- "$stage" "$DEST/$name"
    stage=
    log "Downloaded and verified $name"
fi

completed=()
shopt -s nullglob
for path in "$DEST"/nestswipe-*; do
    [[ -d "$path" && ! -L "$path" && ${path##*/} =~ ^nestswipe-[0-9]{8}T[0-9]{6}Z$ ]] || continue
    [[ -s "$path/backup.tar.gz.enc" && -s "$path/SHA256SUMS" ]] || continue
    completed+=("$path")
done
for ((i=0; i<${#completed[@]}-3; i++)); do rm -rf -- "${completed[$i]}"; done
printf '%s\n' "$cycle" > "$DEST/.last-success.tmp"
mv "$DEST/.last-success.tmp" "$DEST/.last-success"
