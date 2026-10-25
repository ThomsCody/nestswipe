#!/usr/bin/env bash
# Deploy code and schedules only. Keys and recovery data are provisioned separately.
set -euo pipefail
umask 077
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
SOURCE=$(cd "$(dirname "$0")" && pwd)
DEST=/home/ubuntu/nestswipe-backups
CERT=/etc/nestswipe-backup/recipient.pem
temporary=
trap 'if [[ -n "$temporary" ]]; then rm -f -- "$temporary"; fi' EXIT

fail() { echo "Backup installation: $*" >&2; exit 1; }
[[ $EUID == 0 ]] || fail 'run as root'
[[ $# == 0 || ( $# == 1 && $1 == --check ) ]] || fail 'usage: install-production.sh [--check]'
for command in flock openssl docker tar gzip curl sha256sum logger logrotate; do
    command -v "$command" >/dev/null || fail "missing dependency: $command"
done
getent group ubuntu >/dev/null || fail 'the ubuntu group must exist'
systemctl is-active --quiet cron || fail 'the cron service must already be running'
[[ -s "$CERT" ]] || fail "provision the existing public recovery certificate at $CERT first; see deploy/backup/README.md"
openssl x509 -in "$CERT" -checkend 604800 -noout >/dev/null || fail 'recovery certificate is invalid or expires within seven days'
for script in production-backup.sh export-backup.sh; do
    bash -n "$SOURCE/$script"
done
for file in README.md nestswipe-backup.cron nestswipe-backup.logrotate; do
    [[ -s "$SOURCE/$file" ]] || fail "missing source file: $file"
done
if [[ ${1:-} == --check ]]; then
    echo 'Backup installation prerequisites are ready; no files changed.'
    exit 0
fi

install -d -m 750 -o root -g ubuntu "$DEST"
touch "$DEST/.backup.lock"
chmod 644 "$DEST/.backup.lock"
exec 9>"$DEST/.backup.lock"
flock -x -w 300 9 || fail 'backup/download is still running; retry deployment later'
install -d -m 700 -o root -g root /var/lib/nestswipe-backup
install -d -m 700 -o ubuntu -g ubuntu /var/lib/nestswipe-backup-receipts
install -d -m 755 -o root -g root /usr/local/share/nestswipe-backup

# Replace each file atomically while no backup or download holds the lock.
# Never truncate a script that an existing shell may still be reading.
install_file() {
    local source=$1 target=$2 mode=$3
    temporary=$(mktemp "$(dirname "$target")/.nestswipe-backup.XXXXXXXX")
    install -m "$mode" -o root -g root "$source" "$temporary"
    mv -fT -- "$temporary" "$target"
    temporary=
}
install_file "$SOURCE/production-backup.sh" /usr/local/sbin/nestswipe-production-backup 755
install_file "$SOURCE/export-backup.sh" /usr/local/sbin/nestswipe-backup-export 755
install_file "$SOURCE/README.md" /usr/local/share/nestswipe-backup/README.md 644
install_file "$SOURCE/nestswipe-backup.logrotate" /etc/logrotate.d/nestswipe-backup 644
# Publish the schedule last, once its executable and documentation are ready.
install_file "$SOURCE/nestswipe-backup.cron" /etc/cron.d/nestswipe-backup 644
echo 'Backup scripts, Saturday schedule and log rotation installed; keys and archives preserved.'
