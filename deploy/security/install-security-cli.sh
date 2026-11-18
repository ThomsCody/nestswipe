#!/usr/bin/env bash
set -euo pipefail

if command -v datadog-security-cli >/dev/null 2>&1; then
  exit 0
fi

# Use the same signed Datadog package repository as the CI scanner.
keyring=/usr/share/keyrings/datadog-archive-keyring.gpg
# Share the Agent's existing keyring: APT requires one Signed-By value per repo.
if [ ! -s "$keyring" ]; then
  key_file=$(mktemp)
  trap 'rm -f "$key_file"' EXIT
  curl -fsSL https://keys.datadoghq.com/DATADOG_APT_KEY_CURRENT.public |
    gpg --dearmor > "$key_file"
  sudo -n install -m 0644 "$key_file" "$keyring"
fi
printf '%s\n' 'deb [signed-by=/usr/share/keyrings/datadog-archive-keyring.gpg] https://apt.datadoghq.com/ stable datadog-security-cli' |
  sudo -n tee /etc/apt/sources.list.d/datadog-security-cli.list >/dev/null
sudo -n apt-get update -qq
sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends datadog-security-cli
