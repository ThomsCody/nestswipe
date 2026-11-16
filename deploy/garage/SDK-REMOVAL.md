# OpenDAL SDK migration — 2026-11-16

The storage server remains Garage with existing keys and volumes. The application
now uses Apache OpenDAL 0.47.12 instead of the MinIO SDK. No boto3 dependency is
introduced. Active Compose definitions and provisioning no longer require the
MinIO service or its credentials. Original production volumes/snapshots remain
retained offline; historical recovery instructions are in README.md.

Local gates completed before production changes:

- 388 backend tests passed, including PostgreSQL integration, auth tokens,
  storage failure handling and memory/filesystem portability.
- 31 deployment/security/provisioning tests passed; ShellCheck and both Compose
  configurations passed. Backup downloader regression passed.
- Python 3.14.9 ARM64 final production image (uid 1001) read all 4 existing local
  Garage fixtures / 6,400,022 bytes with hashes unchanged from the original
  migration manifest and served an authenticated existing image.
- OpenDAL/Garage roundtrip passed for empty, Unicode and 10MB objects; byte hashes,
  content type and user metadata, authenticated image response, presigned HTTP
  read, upload and delete passed. Test objects were deleted afterward.
- Built dependency environment audit: no known vulnerabilities. MinIO and boto3
  are absent from the image. This does not establish the status of a particular
  Datadog SCA finding whose advisory details were unavailable through the API.
- OpenDAL stable release and cp311-abi3 Linux ARM64 wheel verified from PyPI.
  Python binding does not expose every S3 content header; SDK-only rollout does
  not rewrite existing objects. Historical copier retained through Git history.

Bazel formatting could not run because Appgate was disconnected; the local Ruff
formatter was used for changed Python files. Host pip-audit's Python3.10 virtual
environment failed; audit succeeded in the built Python3.14 Linux container.

## Production delivery

Implementation commit: `0488ed6561ae9beab3ace76706b70a42ec5ac684`.
Remote main matched this signed commit before deployment. Only the committed
archive was synchronized, without deletion; unrelated local changes were excluded.

On 2026-11-16, ingress and writers paused at **11:32:06 UTC**. The new backend
started with its scheduler disabled, then all checks passed before reopening at
approximately **11:33:15 UTC**. The backup exclusion lock covered the paused
interval; normal backup scheduling remains installed.

- **3,219 objects / 815,023,321 bytes**: before/after key, SHA256, size and exposed
  metadata inventories identical. No existing objects were rewritten.
- Manifest SHA256 (both inventories):
  `81f249bcfae75c9ed69852adff9abda83ebefb7ac32e7085a33001b06fb993f7`.
- **4,525 database photo references**, exact before/after comparison identical,
  **zero missing objects**.
- Actual production image: OpenDAL 0.47.12 present; MinIO and boto3 absent.
- Existing authenticated image and controlled upload/read/delete passed before
  reopening. Public HTTPS health and authenticated image SHA256 then passed;
  scheduler enabled and backend, Caddy, Garage healthy.
- Original `deploy_minio_data` volume and stopped MinIO container remain offline;
  original snapshots and credentials are preserved. No broad pruning occurred.
- Retired migration scripts moved out of the active production source directory
  into protected historical evidence; recovery also remains in Git history.

Evidence directory:
`/home/ubuntu/nestswipe-backups/garage-migrations/opendal-0488ed6/` contains
`before.json`, `after.json`, exact reference lists, rollout logs, rollout script,
rollback Compose and retired migration tools. Private keys/object references are
not committed. Retained backend image `nestswipe-pre-opendal:0488ed6` supports
software rollback without changing Garage data.

An initial attempt waited on the backup installer's exclusive lock while holding
the outer shared lock. This was caught before downtime; only the waiting lock
process was stopped. The installer was moved before the outer lock acquisition,
the ordering was tested locally, production health rechecked, and the retry passed.
The actual backup lock file was retained; archives and data were not deleted.

CI passed: https://github.com/ThomsCody/nestswipe/actions/runs/43858136179 .
