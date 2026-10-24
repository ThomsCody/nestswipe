# Nestswipe backups

These jobs use the existing VM disk and Mac disk. They do not provision Oracle
resources or use a paid backup service. Network traffic still uses the account's
existing transfer allowance.

## Schedule and retention

- Production: Saturday at **03:00 Europe/Paris**, retaining **2 completed backups**.
- Mac: Monday at **22:00 Europe/Paris**, retaining **3 completed backups** in
  `rosen_immo/backups/`.
- Native cron wakes each script hourly. The script checks its Paris-time weekly
  deadline and last successful cycle before doing work. This handles daylight
  saving time, a changed Mac timezone, and missed runs: a sleeping/offline Mac
  retries at a later hourly tick. It does not wake or boot the Mac.
- Failures do not mark a cycle successful. A new download must match both size
  and SHA-256 before it replaces a partial directory or triggers retention.
- Temporary working space is needed while creating/downloading a new backup.
  The retention counts refer to completed backups, not the temporary staging copy.

## Contents and consistency

Each `nestswipe-YYYYMMDDTHHMMSSZ` directory contains an encrypted
`backup.tar.gz.enc`, `SHA256SUMS`, and a manifest with its name, hash and size.
The encrypted payload includes:

- `database.dump`: PostgreSQL custom-format logical dump.
- `globals.sql`: PostgreSQL roles/global configuration, including password hashes.
- `deploy_minio_data.tar`: photo objects and MinIO metadata.
- `deploy_seloger_browser_profile.tar`: scraper profile/cookies.
- `deploy_frontend_dist.tar`: the deployed frontend build.
- `project.tar.gz`: deployed application source and configuration, **including
  production `.env` and `oauth.json`**. Build caches, Git history, local backups,
  Terraform secrets/state and diagnostics are excluded.
- Image/version inventory, metadata and inner checksums.

The backend, browser scraper and MinIO are stopped briefly while the database is
dumped and their volume files are copied. PostgreSQL remains running. The jobs
restart the services before compression/encryption. API requests can fail during
this short capture window. An error/signal handler attempts to restart services
even when the backup fails; a host crash or SIGKILL can bypass shell cleanup.

TLS certificates/Caddy runtime state are not backed up; Caddy can obtain fresh
certificates. This is an application recovery package, not a bootable VM image.
Images are recorded but not exported; preserve/build replacement images before
an upstream registry removes needed versions.

## Encryption and unattended access

OpenSSL 3 CMS uses AES-256-GCM authenticated encryption with an RSA recipient
certificate. The public recipient certificate is installed on production. The
private recovery key exists only at:

`rosen_immo/backups/.keys/recovery-private.pem`

**Keep an independent secure copy of this key. Losing it makes the backups
unrecoverable.** It is protected by filesystem permissions and the Mac's
FileVault, not by an interactive passphrase. The Mac's cron only downloads
ciphertext; it never decrypts automatically.

The separate `.keys/download_ed25519` SSH key is restricted on the server to
`latest` and `fetch nestswipe-<timestamp>` operations. It cannot open a shell,
forward ports, execute arbitrary commands or write files. Host verification is
pinned in `.keys/known_hosts`; the job does not use the interactive 1Password
SSH agent. All backups, keys and logs are ignored by Git and excluded from
deployment rsync. Never move them into a tracked directory.

## Installed paths and manual runs

Production:

- `/usr/local/sbin/nestswipe-production-backup`
- `/usr/local/sbin/nestswipe-backup-export`
- `/etc/nestswipe-backup/recipient.pem`
- `/etc/cron.d/nestswipe-backup`
- `/var/lib/nestswipe-backup/last-success`
- `/home/ubuntu/nestswipe-backups/`
- `/var/log/nestswipe-backup.log` (weekly log rotation)

Run a production backup:

```sh
ssh ubuntu@145.241.161.221 'sudo /usr/local/sbin/nestswipe-production-backup'
```

Download the latest completed backup from the Mac:

```sh
./deploy/backup/download-backup.sh
```

The Mac cron entry invokes this path directly, so keep this checkout in its
current location. Its log is `backups/.logs/download.log`. No email or external
notification is configured; inspect the logs and backup timestamps. Production
failures are also sent to the system log under `nestswipe-backup`.

## Deployment and first installation

Every `./deploy/deploy.sh` run installs the versioned production scripts, cron
schedule, log rotation and recovery instructions before building the application.
The installer replaces files atomically under the backup lock. The application
deployment then holds a shared lock so a scheduled backup cannot stop containers
during a build or migration. An active backup/download can delay installation;
after five minutes the deployment fails safely and can be retried.

Production scripts remain installed outside the deployment directory, and
archives stay outside the checkout. Deployment does not create a backup, delete
archives, reset the weekly success marker, replace a certificate, generate keys,
or modify SSH authorization. The Mac's existing cron directly executes the
versioned `download-backup.sh`, so updates to that file take effect automatically.

The repository contains **code, schedules and documentation only**. Recovery
keys, SSH keys, certificates, credentials, encrypted dumps and runtime logs are
not committed. `/backups/` is ignored by Git and excluded from deployment rsync.

On a replacement VM, first provision the existing public recovery certificate
securely at `/etc/nestswipe-backup/recipient.pem`. Keep its private key off the VM.
Install Docker, OpenSSL 3, cron, logrotate and standard Ubuntu utilities; cron
must be running. The `ubuntu` group must exist. Then run:

```sh
sudo bash deploy/backup/install-production.sh --check
sudo bash deploy/backup/install-production.sh
```

The installer fails before changing installed scripts if the certificate or a
prerequisite is missing. It never silently creates a new recovery identity.
Separately provision the Mac's restricted download public key in the production
user's `authorized_keys` with this forced-command prefix:

```text
restrict,command="/usr/local/sbin/nestswipe-backup-export"
```

Append the public key on that same line. Do not use the unrestricted login key
for unattended downloads. Restore the Mac's `.keys/` directory securely, verify
the server host key independently before adding it to `.keys/known_hosts`, and
reinstall the Monday cron entry when moving to another Mac. These credentials
and machine-specific cron configuration are intentionally outside Git.

## Verify and decrypt on the Mac

Use the Homebrew OpenSSL 3 binary, not macOS's older LibreSSL. Set `BACKUP` to
one completed backup directory and `RESTORE_DIR` to a new private scratch path.

```sh
umask 077
BACKUP="$PWD/backups/nestswipe-YYYYMMDDTHHMMSSZ"
RESTORE_DIR=$(mktemp -d)
(cd "$BACKUP" && shasum -a 256 -c SHA256SUMS)
/opt/homebrew/bin/openssl cms -decrypt -binary -inform DER \
  -in "$BACKUP/backup.tar.gz.enc" \
  -inkey "$PWD/backups/.keys/recovery-private.pem" \
  -out "$RESTORE_DIR/payload.tar.gz"
# Decrypt fully and check the exit code before extracting: GCM authenticates
# at the end. Do not pipe unauthenticated plaintext directly into tar.
mkdir "$RESTORE_DIR/payload"
tar -xzf "$RESTORE_DIR/payload.tar.gz" -C "$RESTORE_DIR/payload"
(cd "$RESTORE_DIR/payload" && shasum -a 256 -c CONTENTS.sha256)
```

The decrypted scratch files contain credentials and private data. Remove the
scratch directory after use; do not commit or attach them to a ticket.

## Recovery procedure

1. Decrypt and validate both outer and inner checksums.
2. On an isolated machine, install Docker and a compatible PostgreSQL 16 image.
3. Extract `project.tar.gz` into a private application directory. Restore its
   configuration with restrictive permissions. Review `globals.sql` before
   loading it: an existing role may already exist, and it contains privileges.
4. Create the target database with the configured database owner. Restore using
   PostgreSQL 16 `pg_restore --exit-on-error --no-owner --no-privileges` into the
   **new, empty database**. Do not run a trial restore against production.
5. With MinIO stopped, extract `deploy_minio_data.tar` into its empty Docker
   volume. The archive preserves ownership. Initially use the recorded MinIO
   version; test storage migration separately. Restore browser/frontend volumes
   similarly. PostgreSQL's physical data directory is deliberately not copied.
6. Bring up services; check database row counts, login, favorites, photo access,
   browser startup and `/api/v1/health`. Check migration compatibility before
   deploying newer application code.

An archive-listing check alone is not a database restore test. The initial setup
also performs an isolated real restore; future periodic restore drills should be
performed separately. A backup on the same VM does not protect against losing
that VM; the Mac copy is essential.

## Tests

On macOS:

```sh
shellcheck deploy/backup/*.sh
bash deploy/backup/test-download.sh
```

The transfer tests use a fake SSH endpoint and cover retention, failed integrity
checks, unsafe filenames, partial cleanup and the weekly deadline gate.
