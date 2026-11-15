# Production Compose secrets

Production passes application credentials through read-only files under
`/run/secrets`, with access granted separately to each service. Development
continues to support environment variables. In the backend and browser,
explicit `*_FILE` settings take precedence over legacy environment values;
unreadable files fail rather than falling back. File contents are read exactly,
so do not append newlines when creating credentials manually.

`remote-deploy.sh` runs this before starting containers:

```sh
python3 provision-secrets.py --env-file .env --output-dir secrets
```

It uses Compose's own interpolation to preserve the credentials previously
injected from `.env`, including the database URL and JWT signing key. It never
prints credentials or rotates them. Required values must be set. Optional
integrations get empty files when unset. Existing files must match `.env`;
differences stop deployment for explicit reconciliation. Unchanged files keep
their inode so existing container bind mounts remain valid.

The host directory is mode `0700`, owned by the deployment user. Files are mode
`0600`, except the two proxy files, which are `0444` so the browser's uid 1001
can read them through its individual read-only mounts. The parent directory
prevents other unprivileged host users from reaching these files. Compose file
secrets do not remap file ownership. Host root and the Docker daemon remain
trusted. Ordinary Compose secrets do not encrypt files at rest.

`deploy/secrets/` is ignored by Git and excluded from deployment rsync, including
deletion. It is outside every application Docker build context. The existing
`.env` remains protected on the server for provisioning, monitoring and rollback;
Google OAuth continues to use its existing read-only JSON mount. Existing
encrypted production backups include both `.env` and the secret directory.

For an isolated test, set `NESTSWIPE_SECRETS_DIR` to an absolute scratch directory
when running the production Compose file. Use dummy credentials and a separate
Compose project and volumes. Never attach production volumes for a trial.

For rollback, retain the previous images and Compose configuration before
deployment. The original `.env` values remain usable by those images. Recreate
the affected services using the saved configuration and image IDs, preserving
all existing data volumes. Do not run `down -v`.

For future credential rotation, update the underlying service and `.env` and
replace the corresponding files together, then recreate every consuming
container. Existing mounts do not follow atomic replacement of host files.
Changing a PostgreSQL password file alone does not change an initialized
database's password.
