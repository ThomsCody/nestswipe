#!/usr/bin/env bash
# Install versioned checks without restarting the Agent or application.
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
[[ $EUID == 0 ]] || { echo 'Run as root' >&2; exit 1; }
source_dir=$(cd "$(dirname "$0")" && pwd)
[[ -S /var/run/datadog/dsd.socket ]]
install -m 755 "$source_dir/monitor.py" /usr/local/sbin/.nestswipe-security-monitor.next
mv -f /usr/local/sbin/.nestswipe-security-monitor.next /usr/local/sbin/nestswipe-security-monitor
for unit in "$source_dir"/nestswipe-security-report.service "$source_dir"/nestswipe-security-report.timer; do
    install -m 644 "$unit" "/etc/systemd/system/${unit##*/}"
done
systemctl daemon-reload
systemctl enable --now nestswipe-security-report.timer
systemctl start nestswipe-security-report.service
echo 'Backup, Mac acknowledgement and reboot reporting enabled.'
