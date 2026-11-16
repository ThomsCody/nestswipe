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

Production evidence will be appended after reviewed deployment.
