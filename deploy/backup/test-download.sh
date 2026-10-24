#!/usr/bin/env bash
# Meaningful transfer/retention failure tests. Run on macOS, no production access.
set -euo pipefail
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
export NESTSWIPE_BACKUP_DIR=$tmp/local
export NESTSWIPE_SSH_BIN=$tmp/fake-ssh
export FAKE_REMOTE=$tmp/remote
mkdir -p "$NESTSWIPE_BACKUP_DIR/.keys" "$FAKE_REMOTE"
printf fixture > "$NESTSWIPE_BACKUP_DIR/.keys/download_ed25519"
printf fixture > "$NESTSWIPE_BACKUP_DIR/.keys/known_hosts"
cat > "$NESTSWIPE_SSH_BIN" <<'MOCK'
#!/bin/bash
set -eu
last=${!#}
case "$last" in
    latest) cat "$FAKE_REMOTE/manifest" ;;
    fetch\ *) cat "$FAKE_REMOTE/payload" ;;
    *) exit 99 ;;
esac
MOCK
chmod +x "$NESTSWIPE_SSH_BIN"
mkdir "$NESTSWIPE_BACKUP_DIR/nestswipe-do-not-delete"
for day in 01 02 03 04 05; do
    printf 'backup for day %s\n' "$day" > "$FAKE_REMOTE/payload"
    digest=$(shasum -a 256 "$FAKE_REMOTE/payload" | awk '{print $1}')
    bytes=$(stat -f %z "$FAKE_REMOTE/payload")
    printf 'nestswipe-202610%sT010000Z %s %s\n' "$day" "$digest" "$bytes" > "$FAKE_REMOTE/manifest"
    "$ROOT/deploy/backup/download-backup.sh" >/dev/null
done
[[ ! -e "$NESTSWIPE_BACKUP_DIR/nestswipe-20261001T010000Z" ]]
[[ ! -e "$NESTSWIPE_BACKUP_DIR/nestswipe-20261002T010000Z" ]]
for day in 03 04 05; do [[ -s "$NESTSWIPE_BACKUP_DIR/nestswipe-202610${day}T010000Z/SHA256SUMS" ]]; done
[[ -d "$NESTSWIPE_BACKUP_DIR/nestswipe-do-not-delete" ]]
"$ROOT/deploy/backup/download-backup.sh" >/dev/null

# A corrupt new transfer must not remove any successful backups or leave partials.
sed 's/20261005/20261006/' "$FAKE_REMOTE/manifest" > "$FAKE_REMOTE/next"
mv "$FAKE_REMOTE/next" "$FAKE_REMOTE/manifest"
printf corruption >> "$FAKE_REMOTE/payload"
if "$ROOT/deploy/backup/download-backup.sh" >/dev/null 2>&1; then
    echo 'FAIL: corrupt transfer accepted' >&2; exit 1
fi
[[ ! -e "$NESTSWIPE_BACKUP_DIR/nestswipe-20261006T010000Z" ]]
for day in 03 04 05; do [[ -s "$NESTSWIPE_BACKUP_DIR/nestswipe-202610${day}T010000Z/SHA256SUMS" ]]; done
[[ -z $(find "$NESTSWIPE_BACKUP_DIR" -maxdepth 1 -name '.partial.*' -print) ]]
[[ ! -d "$NESTSWIPE_BACKUP_DIR/.download.lock" ]]

# Do not trust filenames supplied by a compromised/misconfigured remote command.
printf '../../escape bad 3\n' > "$FAKE_REMOTE/manifest"
if "$ROOT/deploy/backup/download-backup.sh" >/dev/null 2>&1; then
    echo 'FAIL: unsafe remote filename accepted' >&2; exit 1
fi

# Once this weekly cycle succeeded, cron must not contact SSH again.
rm "$NESTSWIPE_SSH_BIN"
"$ROOT/deploy/backup/download-backup.sh" --scheduled >/dev/null
echo 'PASS: transfer, checksum, retention, duplicate, unsafe-name, cleanup and weekly-gate tests'
