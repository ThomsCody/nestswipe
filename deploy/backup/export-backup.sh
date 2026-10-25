#!/usr/bin/env bash
# Forced command for the Mac's SSH key. Only exports and a fixed receipt file.
set -euo pipefail
export PATH=/usr/bin:/bin
DEST=/home/ubuntu/nestswipe-backups
exec 9<"$DEST/.backup.lock"
flock -s -w 60 9

command=${SSH_ORIGINAL_COMMAND:-}
if [[ "$command" == latest ]]; then
    latest=
    shopt -s nullglob
    for path in "$DEST"/nestswipe-*; do
        [[ -d "$path" && ! -L "$path" && ${path##*/} =~ ^nestswipe-[0-9]{8}T[0-9]{6}Z$ ]] || continue
        [[ -s "$path/manifest.txt" && -s "$path/backup.tar.gz.enc" ]] || continue
        latest=$path
    done
    [[ -n "$latest" ]] || { echo 'No completed backup available' >&2; exit 1; }
    cat "$latest/manifest.txt"
elif [[ "$command" =~ ^fetch\ (nestswipe-[0-9]{8}T[0-9]{6}Z)$ ]]; then
    name=${BASH_REMATCH[1]}
    [[ -d "$DEST/$name" && ! -L "$DEST/$name" ]]
    [[ -f "$DEST/$name/backup.tar.gz.enc" && ! -L "$DEST/$name/backup.tar.gz.enc" ]]
    cat "$DEST/$name/backup.tar.gz.enc"
elif [[ "$command" =~ ^ack\ (nestswipe-[0-9]{8}T[0-9]{6}Z)\ ([a-f0-9]{64})$ ]]; then
    name=${BASH_REMATCH[1]}
    digest=${BASH_REMATCH[2]}
    [[ -d "$DEST/$name" && ! -L "$DEST/$name" ]]
    read -r expected_name expected_digest _bytes < "$DEST/$name/manifest.txt"
    [[ "$name" == "$expected_name" && "$digest" == "$expected_digest" ]]
    receipts=/var/lib/nestswipe-backup-receipts
    [[ -d "$receipts" && ! -L "$receipts" ]]
    umask 077
    temporary=$(mktemp "$receipts/.mac.XXXXXXXX")
    trap 'rm -f -- "$temporary"' EXIT
    printf '%s %s\n' "$(date +%s)" "$name" > "$temporary"
    mv -f -- "$temporary" "$receipts/mac"
else
    echo 'This key only permits latest, fetch or checksum acknowledgement of a named backup.' >&2
    exit 2
fi
