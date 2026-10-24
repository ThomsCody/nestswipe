#!/usr/bin/env bash
# Read-only deployment prerequisite; never overwrite Fleet-managed configuration.
set -euo pipefail
for service in datadog-agent datadog-agent-trace datadog-agent-sysprobe datadog-agent-installer; do
    systemctl is-active --quiet "$service" || {
        echo "Host monitoring service is unavailable: $service"
        exit 1
    }
done
for socket in /var/run/datadog/apm.socket /var/run/datadog/dsd.socket; do
    [[ -S "$socket" ]] || { echo "Missing Agent socket: $socket"; exit 1; }
done
echo 'Host Agent, remote-management installer, and application sockets are ready.'
