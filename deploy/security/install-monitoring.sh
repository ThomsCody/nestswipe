#!/usr/bin/env bash
# Install versioned checks without restarting the Agent or application.
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
[[ $EUID == 0 ]] || { echo 'Run as root' >&2; exit 1; }
source_dir=$(cd "$(dirname "$0")" && pwd)
[[ -x /usr/local/bin/nestswipe-trivy ]]
[[ $(sha256sum /usr/local/bin/nestswipe-trivy | cut -d ' ' -f 1) == b422130ea54e53e142e65c838662e48919ce9c3f23f17d80066b43e70550cb85 ]]
[[ -S /var/run/datadog/dsd.socket ]]
install -d -m 700 /var/lib/nestswipe-security /var/cache/nestswipe-trivy
install -m 755 "$source_dir/monitor.py" /usr/local/sbin/.nestswipe-security-monitor.next
mv -f /usr/local/sbin/.nestswipe-security-monitor.next /usr/local/sbin/nestswipe-security-monitor
for unit in "$source_dir"/nestswipe-security-*.service "$source_dir"/nestswipe-security-*.timer; do
    install -m 644 "$unit" "/etc/systemd/system/${unit##*/}"
done
systemctl daemon-reload
systemctl enable --now nestswipe-security-report.timer nestswipe-security-scan.timer
systemctl start nestswipe-security-report.service
echo 'Maintenance reporting and daily image scanning enabled.'
