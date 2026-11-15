# IaC findings: 2026-11-15 remediation

Datadog baseline: repository `github.com/ThomsCody/nestswipe`, branch `main`, commit
`c17b00f666a5da14ab869ece7d901c883df28f8e`. The completed inventory contains **272
findings: 10 high, 3 medium, 259 low**. This document records dispositions, not a
claim that Datadog has rescanned the changes or that production rollout is done.

## Disposition of all findings

| Rule | Count | Disposition |
| --- | ---: | --- |
| `terraform-output-without-description` | 249 | Upstream module documentation findings; no security behavior to remediate. |
| `dockerfile-env-no-refer-envvar` | 5 | Frontend build ARG-to-ENV assignments; intentional build inputs, not undefined references. |
| `dockercompose-hardcoded-credential-in-environment` | 4 | Fixed: require explicit local Compose credentials instead of insecure fallback values. |
| `dockercompose-image-uses-latest-or-no-tag` | 2 | Fixed: pin local and production MinIO to the exact deployed image digest. |
| `dockerfile-healthcheck-instruction-missing` | 4 | Fixed: four runtime HTTP healthchecks validated locally. |
| `dockerfile-missing-user-instruction` | 3 | Fixed: nonroot backend, Caddy and standalone nginx; access and ports validated locally. |
| `dockerfile-use-recommended-flags-with-useradd` | 1 | Fixed: browser useradd uses --no-log-init. |
| `dockercompose-docker-socket-mounted-in-container` | 2 | Intentional local Datadog integration; residual host-control risk documented below. |
| `dockercompose-privileged-ports-mapped-in-container` | 1 | Required Caddy public HTTP/HTTPS ports. |
| `dockercompose-volume-has-sensitive-host-directory` | 1 | Scoped Datadog telemetry socket directory, not a broad host runtime mount. |

Total: **14 findings selected for remediation**, **254 non-security/documentation
findings**, and **4 intentional integration exceptions**. No blanket suppression
or scanner configuration change is used.

The Terraform findings originate in transitive modules under the pinned Datadog
OCI onboarding dependency, including regional-stack VCN outputs. Adding output
descriptions would improve upstream documentation but would not change access,
network exposure or credential handling. Do not fork or redeploy infrastructure
solely to change these descriptions.

The five frontend assignments consume build arguments declared in that stage.
Public browser telemetry identifiers are intentionally compiled into the client;
these are not server API keys. The runtime worker must retain the existing build
argument behavior.

## Compose fixes

`POSTGRES_PASSWORD`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` and `JWT_SECRET`
now use required Compose interpolation. Continue supplying the configured env
file (`docker compose --env-file deploy/.env ...`). Non-secret user/database
name defaults remain. The test service shares these actual service settings;
it is not a separate fixture with mocked authentication. Missing credentials
fail during Compose configuration, before a container starts.

This does not rotate any existing database or storage password. Existing local
volumes still require their matching credentials; do not delete volumes to make
a failed login disappear. No real credentials belong in this document or Git.

Both MinIO services now use:

```
minio/minio@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e
```

This is the exact existing production and local cached `linux/arm64` image,
labelled `RELEASE.2025-09-07T16-13-09Z`. It changes selection, not the deployed
server binary. Normal cache-aware pulling remains enabled. Registry manifest
requests for the release/digest returned unauthorized/denied during validation.
A fresh installation therefore needs registry access or a trusted saved copy of
this exact image. Availability of an amd64 image was not established; do not
silently replace this pin with `latest` or force cross-platform emulation.

## Intentional integration exceptions

- Local Datadog containers mount `/var/run/docker.sock:ro` for discovery and
  container logs. A read-only filesystem mount does **not** restrict Docker API
  operations; compromise of that trusted agent can control the Docker host.
  This is local development configuration, not the production stack. Datadog's
  [official socket rule](https://docs.datadoghq.com/security/default_rules/j9z-sms-f3m/)
  explicitly recognizes its Agent images as using the socket by design, and its
  [log collection documentation](https://docs.datadoghq.com/containers/docker/log/)
  uses this mount. Removing it silently breaks monitoring; an unvalidated proxy
  would relocate privileged access rather than prove it eliminated. Production
  uses its independently managed host Agent. Retain this explicit residual risk.
- Caddy ports 80 and 443 provide HTTP redirect/ACME and public HTTPS. Keep these
  intentional entry points. Backend, PostgreSQL and MinIO publish no production
  host ports.
- Backend `/var/run/datadog:/var/run/datadog:ro` exposes only Agent telemetry
  sockets. It does not expose `/var/run` generally or the Docker daemon socket.
  Mounting the directory supports socket recreation after Agent restarts;
  individual socket bind mounts can become stale. Nonroot backend still needs
  permission to connect to the sockets. Validate telemetry after rollout.

## Validation and rollout status

Completed for the Compose changes:

- Local Compose, local plus `docker-compose.dd.yml`, and production Compose
  pass `docker compose ... config --quiet` with dummy environment values.
- Each of the four required credential variables independently fails clearly
  when omitted.
- Exact pinned MinIO image resolves from local and production caches.
- Disposable local MinIO container, dummy credentials, no production mounts:
  bucket creation, upload, read/byte comparison, object deletion and bucket
  deletion passed. The test container was removed.

Runtime validation completed on isolated local Colima containers:

- Backend production/test, browser, Caddy and standalone frontend image builds
  passed. Frontend `tsc` and Vite completed; existing bundle-size warning and
  public browser-token build-argument advisory remain.
- Full backend suite: **379 passed, 2 skipped**. Browser suite: **26 passed**.
- Nonroot backend UID/GID1001 read mode0600 dummy secrets with production's
  owner layout; migrations001–022 and HTTP startup/health passed against a
  disposable PostgreSQL16 instance. Writable home and telemetry socket access
  passed against dummy sockets with the production directory/socket modes.
- Browser health, profile writes and actual Chromium startup passed using the
  production `init: true`/shared-memory layout.
- Nonroot Caddy served port80, proxied backend, reported healthy, wrote new
  data/config volumes, served port443 using internal test certificates, and
  retained those certificates across restart. No public ACME request was made.
- Standalone final nginx now runs UID101 on **8080**, with writable PID/cache
  paths. Static GET and backend proxy returned200 and Docker marked it healthy.
  Consumers of this final image must map their host port to8080. The production
  frontend-build target and local development target are unchanged.

Caddy's existing production data/config volumes require a one-time ownership
migration to1001 while preserving modes. New volumes inherit ownership from the
image; subsequent normal deployments require no repeat migration. Save original
ownership metadata for rollback, then verify real TLS/certificates after rollout.

The one-shot backend test stage declares `HEALTHCHECK NONE`; it exits with the
test result rather than pretending to run an HTTP service. Runtime HTTP checks
are liveness checks, not end-to-end dependency tests; the separate functional
checks below remain mandatory.

The signed runtime and Compose commits were integrated without conflicts.
Official Datadog IaC scanner1.20.6, with the same rule bundle for both scans
(SHA256 `545631ed7b64b4b4c50ad29012216bf61cf3ef5ecbd211ef9527ef0d5f0be1e0`),
executed1200 rules on14 files: baseline39 findings, integrated25. All14 selected
findings disappeared; no new rule/file findings appeared. The remaining25 are
nine direct intentional/documentation exclusions plus16 unchanged CI findings
outside the supplied hosted view. The249 transitive Terraform findings were not
fetched by this local scan; hosted follow-up remains necessary.

Production deployment, post-deploy functional checks and fresh hosted Datadog
scan remain **pending** until recorded with evidence. Local tests are not a production
validation.

## Serialized release and rollback convention

One designated release worker must continuously hold an exclusive remote
`/home/ubuntu/nestswipe-deploy.lock` from **before rsync** until post-deploy checks
or rollback completes. An SSH session can hold the lock using
`flock -n /home/ubuntu/nestswipe-deploy.lock` around a shell that stays alive for
the entire transaction; release only after the worker has finished. Every
collaborating deployer must respect this same lock. The stock deployment script
alone does not provide this serialization.

The actual backup coordination lock is
`/home/ubuntu/nestswipe-backups/.backup.lock`. The deployment's shared backup
lock prevents overlap with the exclusive scheduled backup, but permits another
deployment. Do not wrap the whole deployment in an additional held backup lock:
the backup installer acquires its own exclusive lock and would deadlock.

Before replacement, save the current source/configuration with file modes and
ownership, immutable image IDs, and Caddy volume ownership metadata outside the
rsync destination. Retain images without pruning. Nonroot Caddy may require
ownership adjustment of its existing data/config volumes; save the old metadata
before doing so. Confirm migration backward compatibility and preserve data
volumes. On a regression, keep the deployment lock, restore prior configuration,
images and ownership as needed, recreate affected services, and repeat health
checks. Never use `down -v` or restore old database contents for an application
rollback. Release gates include API health, a database-backed read, photo/storage
access, browser readiness and host-Agent/telemetry health.
