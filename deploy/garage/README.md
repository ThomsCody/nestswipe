# Garage storage migration

Garage v2.5.0 is pinned by manifest digest. The MinIO Python SDK remains the S3
client; `MINIO_*` configuration names are retained to keep the change bounded.
`MINIO_REGION=garage` is explicit. Both Garage metadata and object-data volumes
are required for recovery. One node preserves the previous single-VM failure
exposure; it is not redundant storage.

## Initial local setup

Run `python3 deploy/garage/provision.py --directory deploy/secrets`, start Garage
with Compose, then run `deploy/garage/init.py` with the actual container name and
secrets directory. The generated files are ignored by Git. They are reused on
subsequent deployments. Garage's RPC secret is owner-readable; S3 key files are
readable inside the non-root backend, behind a host directory with mode 0700.

## Migration gates

Before changing production, rehearse against disposable local MinIO and Garage:
copy including multipart, empty and Unicode-key objects; verify key sets, every
SHA256 and content/user metadata; test authenticated image serving, presigned
reads, upload/delete, corruption detection, and rollback. Stop Garage and archive
both volumes, restore into fresh volumes, and rerun full verification. Run the
backend suite and deployment/security tests. `rehearse.py` exercises the data and
application operations against the explicitly named disposable containers.

Production needs enough free space for original MinIO, its snapshot, Garage and
backup scratch space. Inventory all buckets and reject versioned source buckets;
Garage does not preserve S3 version history. Provision every destination bucket
before copying. This deployment uses `listing-photos`.

## Production cutover

1. Build/test locally, review changes, then synchronize reviewed source. Preserve
   all production secrets and keep migration evidence outside the rsynced tree.
   If the installed backup job still targets MinIO, pause only its cron entry
   under the same exclusive backup lock before cutover, saving the original.
   Restore the schedule with the Garage-aware installer after verification;
   restore the original schedule instead if rolling back to MinIO. This covers
   the gap between cutover and ordinary deployment.
2. The backup root is root-owned. Create a protected writable evidence parent
   once with `sudo install -d -o ubuntu -g ubuntu -m 700
   /home/ubuntu/nestswipe-backups/garage-migrations`. Set
   `NESTSWIPE_MIGRATION_EVIDENCE` to a **new child directory** there when running
   `bash deploy/garage/cutover.sh` on the VM. It takes the exclusive backup
   lock, prepares Garage/backend, stops ingress and backend, snapshots PostgreSQL
   and MinIO, copies all objects, checks every byte and metadata field, records DB
   reference coverage and starts the backend with `SCHEDULER_ENABLED=false`.
   The original MinIO volume is never deleted. Caddy stays stopped for validation.
3. Inspect `manifest.json` and `reference-check.json` in the migration evidence
   directory. Existing missing references are reported distinctly; all existing
   objects must be preserved. Validate several existing galleries through the
   authenticated API, then a controlled object upload/read/delete without DB
   changes. Verify backend health and scheduler remains paused.
4. Only after those smoke tests pass, write the verified manifest path into
   `deploy/secrets/garage-migration-verified`. This unlocks ordinary deployment.
   Run the standard deployment to install backup and monitor scripts
   and enable normal scheduling/ingress. Verify public health and image access.
   Keep MinIO stopped (not deleted) and retain the pre-migration snapshot.
5. On failure before reopening, perform a storage rollback using the tested new
   backend image (which supports scheduler pause). Run Compose with `garage/rollback.yml` and
   `--no-deps backend`, keeping writers paused, verify MinIO image access, then
   explicitly enable scheduling and reopen ingress. After reopening, rollback
   requires a new write freeze and reconciliation of new objects/deletions;
   switching endpoints alone is unsafe.

Do not use `docker compose down -v`. Do not copy MinIO's volume into Garage.
Do not use deletion-based mirroring. Database snapshots and manifests may contain
private data: retain them in protected backup locations, never Git or chat.

## Backups and restore

`production-backup.sh` now stops Garage and includes both `deploy_garage_meta`
and `deploy_garage_data`. Restore them together while Garage is stopped, with the
same version/configuration/secrets. Older MinIO backups use their bundled MinIO
configuration first. Verify the restored objects through S3 and database photo
references before reopening the restored application.
