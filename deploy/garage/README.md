# Garage object storage

Garage v2.5.0 is pinned by manifest digest. Apache OpenDAL 0.47.12 provides the
provider-neutral Python storage API; the application no longer installs MinIO or
boto3. Python 3.14 on Linux ARM64 uses OpenDAL's published cp311-abi3 wheel.

`STORAGE_BACKEND=s3` selects Garage's S3-compatible API. `STORAGE_ENDPOINT`,
`STORAGE_REGION`, `STORAGE_BUCKET`, `STORAGE_ACCESS_KEY_FILE` and
`STORAGE_SECRET_KEY_FILE` configure that adapter. `STORAGE_ROOT` defaults to `/`;
changing it changes the object namespace. Ambient AWS credentials and EC2 metadata
lookup are disabled. `STORAGE_OPTIONS_FILE` accepts a protected JSON object of string-valued OpenDAL
provider options (e.g. GCS bucket and credential_path, or Azure container/account
settings). The supported scheme allowlist is s3, fs, memory, gcs and azblob.
Local tests exercise memory and filesystem portability; GCS/Azure are not tested
against live accounts. Provider-specific configuration, secret mounts and testing
are required before switching; changing a name alone does not migrate data.

Run `python3 deploy/garage/provision.py --directory deploy/secrets`, start Garage
with Compose, then run `deploy/garage/init.py` with the actual container name and
secrets directory. Existing credentials are reused, never rotated by deployment.

## Recovery and historical migration

The completed MinIO migration's reports remain in `PRODUCTION.md` and
`VALIDATION.md`. Original production volumes and snapshots are retained offline.
The retired `cutover.sh`, `rollback.yml`, `migrate.py`, and original rehearsal are
available from commit `ed7540b1f091f009bdd6d12ac1c5a3ca15f93a46`, together with
their matching Compose definitions and dependency requirements. Recover those
files into an isolated checkout, not over a running deployment. Use the original
secrets and mount retained source volumes read-only for inspection. Historical
snapshots are stale: freeze writes and reconcile objects and DB changes before
any rollback. Never simply point the live app back to the historical store.

The OpenDAL Python metadata interface does not expose every S3 content header
(e.g. Cache-Control). Therefore the historical byte-and-metadata-preserving copier
is not replaced by a lossy OpenDAL copier. The SDK change leaves existing objects,
keys, metadata and database references untouched.

## Backups and validation

Backups stop Garage and archive both `deploy_garage_meta` and
`deploy_garage_data`. Restore both with matching configuration and secrets.
Older backups must first use their bundled storage configuration. Never run
`docker compose down -v`, delete retained storage volumes, or copy one storage
engine's internal data files into another engine.

`verify.py` records a read-only SHA256/key/size/content-type/user-metadata inventory
using the configured storage backend. Reports contain private object keys and
belong in a protected backup directory, never Git. Compare before/after inventory
with writers paused when validating a deployment. Full S3 metadata preservation
for this SDK-only change follows from not writing any existing object.
