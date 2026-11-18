#!/usr/bin/env bash
set +x
set -euo pipefail

: "${DD_API_KEY:?Run this script through dd-auth}"
: "${DD_APP_KEY:?Run this script through dd-auth}"
SERVER="${NESTSWIPE_SERVER:-ubuntu@145.241.161.221}"
source_root=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
bundle_dir=$(mktemp -d)
trap 'rm -rf "$bundle_dir"' EXIT
# Supply committed source because the rsynced server directory has no .git.
git -C "$source_root" bundle create "$bundle_dir/source.bundle" HEAD
services=''
for service in "$@"; do
  case "$service" in
    backend|seloger-browser|caddy|frontend-build) services+=" $service" ;;
    *) echo "Unsupported scan service: $service" >&2; exit 1 ;;
  esac
done

# Credentials and source cross SSH on stdin. Credentials never enter a file.
# Service arguments above are restricted to fixed names before interpolation.
# shellcheck disable=SC2029
{
  printf '%s\0%s\0%s\0' "$DD_API_KEY" "$DD_APP_KEY" "${DD_SITE:-datadoghq.com}"
  cat "$bundle_dir/source.bundle"
} | ssh "$SERVER" "bash /home/ubuntu/nestswipe/deploy/security/scan-deployed-images.sh --receive$services"
