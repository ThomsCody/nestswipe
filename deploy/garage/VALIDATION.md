# Local validation — 2026-11-16

Production has not been changed. Read-only production inventory found one bucket,
`listing-photos`, with 3,219 objects and 815,023,321 bytes, no bucket versioning,
and 12 GB free on the VM filesystem. Recheck these numbers before downtime.

Completed locally:

- Backend: **382 tests passed**, including PostgreSQL driver integration and the
  new scheduler-pause regression, under Python 3.14.9 in the built test image.
- Deployment/security tests: **25 passed**; existing secret provisioning:
  **4 passed**; Garage provisioning: **2 passed** (idempotence, restrictive umask,
  file modes and symlink protection).
- Backup downloader regression passed: transfer, checksums, retention, duplicate,
  unsafe-name, cleanup and weekly scheduling gate.
- ShellCheck passed for migration, backup, security and remote-deployment scripts.
  Both Compose configurations resolve; production endpoint and region are fixed
  to Garage regardless of stale environment values. `git diff --check` passed.
- Disposable MinIO-to-Garage rehearsal: **4 objects / 6,400,022 bytes**, including
  multipart, empty and Unicode-key objects. Exact keys, SHA256, content headers
  and user metadata verified. Authenticated photo route, presigned read, new
  upload/read/delete, corruption rejection, repeat copy and storage rollback passed.
- Stopped Garage data and metadata volumes were archived and restored into fresh
  volumes/container. Every restored object passed the same full verification.
- Exact `cutover.sh` ran inside a Linux control container against an isolated
  PostgreSQL/MinIO/Garage/backend stack. One database photo reference and its
  object survived. Backend stayed healthy with scheduler paused and ingress off.
  Live HTTP image retrieval and controlled upload/read/delete passed. Its database
  dump was restored into a separate database with the reference intact.
- The failure handler was exercised during rehearsal; rollback to MinIO restored
  live HTTP image access. Retaining the source backend image before rebuild fixed
  an image-retagging issue discovered by that rehearsal.
- The exact production backend image was built and started locally: uid 1001,
  per-file secrets, paused scheduler and live authenticated Garage image passed.
- Independent read-only review completed. Its stale endpoint override finding was
  fixed and verified. Rollback is explicitly a storage rollback using the tested
  new backend image, which preserves scheduler-pause capability.

Raw local manifests and snapshots are in ignored `backups/garage-rehearsal/` and
`backups/cutover-local/`. They are not committed. No production data was copied
locally for these rehearsals.

The initial 1Password SSH-agent failure was resolved on retry. Signing and
production authentication succeeded. Production delivery is now proceeding only
after all local gates above; final production evidence will be recorded separately.
