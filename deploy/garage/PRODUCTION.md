# Production migration — 2026-11-16

**Complete. Nestswipe serves images from Garage v2.5.0.**

Implementation commit: `1510a596c08376f38db961d689c23270853dc2a4`, signed,
merged to `main` and verified on GitHub before deployment. Later documentation
commits record the result without changing the deployed application.

## Preservation evidence

With ingress and backend stopped and the exclusive backup lock held:

- Copied **3,219 objects / 815,023,321 bytes** from MinIO to Garage.
- Verified each object's complete SHA256, byte length, selected content headers
  and user metadata; source and destination key sets matched exactly.
- Checked **4,525 database photo references**, with **zero missing keys**.
- Preserved the original `deploy_minio_data` volume unchanged. MinIO is now
  stopped; its image/service remains available for a controlled rollback.
- Captured PostgreSQL and MinIO snapshots before copying.

Protected evidence on the production VM:

`/home/ubuntu/nestswipe-backups/garage-migrations/20261116/`

Contains `manifest.json`, `reference-check.json`, `photo-keys.json`,
`database.dump`, `minio-data.tar` and `previous-backend-image`.

Manifest SHA256:
`b610e94596f9e724f9c8e03d556f820536a01ef09cd0ac6d7ee7c12c216ff9c7`

Do not publish the raw manifests/snapshots: they contain application data.

## Application verification

Before reopening, with the scheduler disabled, six existing images passed
byte-for-byte authenticated HTTP checks and a controlled upload/read/delete
succeeded. The object count remained 3,219. Only then was the deployment marker
written and normal scheduling/ingress restored.

After reopening, public `/api/v1/health` returned `{"status":"ok"}` and three
existing images passed byte-for-byte authenticated public HTTPS checks.
The backend confirmed `garage:3900`, region `garage` and scheduler enabled.

Deployed `main.py`, `photo_storage.py` and production Compose SHA256 values
matched the signed implementation checkout. All five active application
containers were healthy after the backup restart; MinIO remained stopped.

## Backup and recovery

The Nestswipe backup cron entry was paused under its lock for cutover, with its
original saved in `garage-preflight-20261116/backup.cron` under the backup root.
The Garage-aware installer restored the tracked schedule; the installed cron
file was compared byte-for-byte with the repository version.

The revised installed backup job was exercised against production. It captured
PostgreSQL and both Garage volumes and restarted application services in six
seconds. The encrypted backup completed at **10:14:43 UTC**:

- Archive: `nestswipe-20261116T101312Z/backup.tar.gz.enc` under the backup root.
- Size: **1,005,267,676 bytes**.
- Installed backup state: `ok`; completed archive SHA256 verification passed.
- Final public health returned `ok`; backend, Garage and Caddy were healthy.

Local restore, rollback and compatibility evidence is in [VALIDATION.md](VALIDATION.md).
The implementation CI run passed:
https://github.com/ThomsCody/nestswipe/actions/runs/43846051160

## Operational notes

Source synchronization was non-deleting. Automatic approval review rejected
`rsync --delete`; no deletion-based synchronization was executed.
The configured personal SSH identity published the commit successfully after
1Password was unlocked. The read-only GitHub token could not push.

The deployment keeps the previous single-VM failure exposure; Garage replication
is one and independent backups remain required. Once normal writes resumed,
rollback requires quiescing writers and reconciling new objects/deletions first.
