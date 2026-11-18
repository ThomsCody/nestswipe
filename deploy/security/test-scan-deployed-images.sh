#!/usr/bin/env bash
set -euo pipefail
scanner="$(cd "$(dirname "$0")" && pwd)/scan-deployed-images.sh"
fixture=$(mktemp -d)
trap 'rm -rf "$fixture"' EXIT
mkdir -p "$fixture/bin" "$fixture/backend"
touch "$fixture/backend/Dockerfile"
export NESTSWIPE_SCAN_SOURCE="$fixture" SCAN_TEST_LOG="$fixture/scans.log"
export DD_API_KEY=test DD_APP_KEY=test
export PATH="$fixture/bin:$PATH"
cat > "$fixture/bin/docker" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
case "$*" in
  ps*)
    [[ "$*" == *com.docker.compose.oneoff=False* ]] || exit 1
    [ "${SCAN_TEST_MODE:-}" != no_container ] || exit 0
    printf '%064d\n' 1 ;;
  'inspect --format {{.Image}} '*) echo sha256:deployed ;;
  'inspect --format {{.Config.Image}} '*) echo deploy-backend ;;
  'image inspect --format {{.Id}} '*)
    if [ "${SCAN_TEST_MODE:-}" = moved_tag ]; then echo sha256:other; else echo sha256:deployed; fi ;;
  *org.opencontainers.image.revision*)
    if [ "${SCAN_TEST_MODE:-}" = no_revision ]; then echo ''; else printf '%040d\n' 2; fi ;;
  *org.opencontainers.image.source*) echo https://github.com/ThomsCody/nestswipe ;;
  *com.datadoghq.image.source_path*) echo backend/Dockerfile ;;
  *) echo "Unexpected Docker invocation: $*" >&2; exit 1 ;;
esac
MOCK
cat > "$fixture/bin/datadog-security-cli" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$SCAN_TEST_LOG"
MOCK
chmod +x "$fixture/bin/docker" "$fixture/bin/datadog-security-cli"
printf '#!/usr/bin/env bash\nexit 0\n' > "$fixture/bin/git"
chmod +x "$fixture/bin/git"

bash "$scanner" backend > "$fixture/result.log" 2>&1
grep -Fxq 'image deploy-backend --dockerfile backend/Dockerfile --env prod --tag service:nestswipe-backend' "$SCAN_TEST_LOG"
for mode in moved_tag no_revision no_container; do
  : > "$SCAN_TEST_LOG"
  if SCAN_TEST_MODE="$mode" bash "$scanner" backend > "$fixture/result.log" 2>&1; then
    echo "Expected rejection for $mode" >&2; exit 1
  fi
  test ! -s "$SCAN_TEST_LOG" || { echo "Published a scan for $mode" >&2; exit 1; }
done
if bash "$scanner" postgres > "$fixture/result.log" 2>&1; then
  echo 'Unexpected acceptance of an upstream service' >&2; exit 1
fi
echo 'Deployed image selection and rejection checks passed.'
