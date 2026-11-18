#!/usr/bin/env bash
set +x
set -euo pipefail

if [ "${1:-}" = --receive ]; then
  shift
  IFS= read -r -d '' DD_API_KEY
  IFS= read -r -d '' DD_APP_KEY
  IFS= read -r -d '' DD_SITE
  export DD_API_KEY DD_APP_KEY DD_SITE
  source_dir=$(mktemp -d)
  trap 'rm -rf "$source_dir"' EXIT
  cat > "$source_dir/source.bundle"
  git init --quiet "$source_dir/repo"
  git -C "$source_dir/repo" fetch --quiet "$source_dir/source.bundle" HEAD
  git -C "$source_dir/repo" remote add origin https://github.com/ThomsCody/nestswipe
  export NESTSWIPE_SCAN_SOURCE="$source_dir/repo"
fi
: "${DD_API_KEY:?Inject Datadog credentials through scan-production-images.sh}"
: "${DD_APP_KEY:?Inject Datadog credentials through scan-production-images.sh}"
export DD_SITE="${DD_SITE:-datadoghq.com}"
cd "${NESTSWIPE_SCAN_SOURCE:?Provide committed source through scan-production-images.sh}"

command -v datadog-security-cli >/dev/null
if [ "$#" -eq 0 ]; then
  set -- backend seloger-browser caddy frontend-build
fi

for service in "$@"; do
  case "$service" in
    backend) dockerfile=backend/Dockerfile ;;
    seloger-browser) dockerfile=browser/Dockerfile ;;
    caddy) dockerfile=deploy/caddy/Dockerfile ;;
    frontend-build) dockerfile=frontend/Dockerfile ;;
    *) echo "Unsupported scan service: $service" >&2; exit 1 ;;
  esac
  # Exclude old Compose one-off jobs (such as historical backfills).
  container=$(docker ps -aq --no-trunc --filter label=com.docker.compose.project=deploy \
    --filter "label=com.docker.compose.service=$service" --filter label=com.docker.compose.oneoff=False)
  [[ "$container" =~ ^[0-9a-f]{64}$ ]] || {
    echo "Expected exactly one deployed container for $service" >&2; exit 1;
  }
  image_id=$(docker inspect --format '{{.Image}}' "$container")
  image_ref=$(docker inspect --format '{{.Config.Image}}' "$container")
  # Scan the image actually used by this container, never a newly rebuilt tag.
  test "$(docker image inspect --format '{{.Id}}' "$image_ref")" = "$image_id" || {
    echo "Image tag moved since $service was deployed; refusing to scan another image" >&2
    exit 1
  }
  revision=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image_id")
  source=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.source"}}' "$image_id")
  source_path=$(docker image inspect --format '{{index .Config.Labels "com.datadoghq.image.source_path"}}' "$image_id")
  [[ "$revision" =~ ^[0-9a-f]{40}$ ]] &&
    [ "$source" = 'https://github.com/ThomsCody/nestswipe' ] &&
    [ "$source_path" = "$dockerfile" ] || {
      echo "Missing or inconsistent source metadata for $service; rebuild and deploy it first" >&2
      exit 1
    }
  git checkout --detach --quiet "$revision"
  test -f "$dockerfile"
  echo "Scanning deployed $service: $image_ref ($image_id), commit $revision, $dockerfile"
  datadog-security-cli image "$image_ref" --dockerfile "$dockerfile" --env prod --tag "service:nestswipe-$service"
  test "$(docker inspect --format '{{.Image}}' "$container")" = "$image_id" || {
    echo "Container changed during the scan; repeat for the new deployment" >&2; exit 1;
  }
  test "$(docker image inspect --format '{{.Id}}' "$image_ref")" = "$image_id" || {
    echo "Image tag changed during the scan; repeat for the new deployment" >&2; exit 1;
  }
done
