# PostgreSQL Database Monitoring

Production PostgreSQL 16 uses `pg_stat_statements`, a dedicated `datadog`
login with `pg_monitor`, and the host Datadog Agent. The Agent connects
over the private Docker network; no database port is published.

`postgres.yaml` enables DBM, schema metadata, and table/index statistics.
Query metrics, activity sampling, and sampled explain plans use the Agent's
defaults. SQL literal obfuscation remains enabled. This setup does not enable
raw SQL logging or `auto_explain`. The restricted explain function runs with
the owner's privileges. Production additionally grants `SELECT` on the 12
application tables listed in `postgres-scanning.sql` for scanning. The
`users` table includes OAuth refresh tokens and API keys; the owner explicitly
approved scanning access to these columns on 2026-11-23. The `alembic_version`
migration table is excluded, and new tables are not granted access
automatically. The role retains `default_transaction_read_only = on`
and has no application-table write privileges.

The instance appears as `nestswipe-db-prod`, service `nestswipe-db`, env `prod`.

## Initial setup or restore

1. Wait for the production backup to finish successfully, including its initial
   setup if another operator is installing the backup job.
2. Copy the Compose file and this directory to the production checkout.
3. Run `sudo bash deploy/datadog/setup-postgres.sh` from the checkout. It creates
   a random password in the existing ignored `deploy/.env`, provisions both
   the application and `postgres` databases, and refuses to run during a backup.
   It can be rerun without changing the existing password.
4. From `deploy/`, use the same backup lock during the restart:

   ```sh
   sudo flock -n /home/ubuntu/nestswipe-backups/.backup.lock \
     docker compose -f docker-compose.prod.yml up -d --no-deps --pull never \
       --wait postgres
   ```

   PostgreSQL must restart to load the extension and increase query text size.
   Allow a brief interruption. Restart the backend after PostgreSQL is healthy
   if its existing connection pool does not recover, holding the same lock.
5. Bootstrap the [host Agent](HOST_AGENT.md) on a new VM. If it is already
   installed, refresh credentials with
   `sudo python3 deploy/datadog/setup-host-agent.py --refresh-db-credentials`.
6. Verify `sudo datadog-agent status`: the `postgres` check
   should be OK with query metrics/activity samples and no collection errors.
   Check the application's health and a real database-backed request.

Normal deployments retain the PostgreSQL flags and leave the host Agent's
Fleet-managed configuration intact. The generated password is only on the
production VM and in its protected backups. A fresh database restore requires
this provisioning step before DBM can connect.

## Table scanning permissions

Applied to production on 2026-11-23. To restore the same explicit grants, run
from the production `deploy/` directory after provisioning the Datadog role:

```sh
sudo flock -n /home/ubuntu/nestswipe-backups/.backup.lock \
  docker compose -f docker-compose.prod.yml exec -T postgres \
  sh -c 'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < datadog/postgres-scanning.sql
```

These grants provide database read access; scan selection and scheduling are
managed separately in Datadog. Review the explicit table list before adding
new tables. To remove these grants, use `REVOKE SELECT` on the same tables.

## Rollback

Remove the PostgreSQL `command` block and disable the PostgreSQL integration
in Fleet or remove `/etc/datadog-agent/conf.d/postgres.d/conf.yaml` on the host.
Under the backup lock, recreate only PostgreSQL with
`--no-deps --pull never --wait` as above, then restart the host Agent.
The inactive extension and monitoring role can remain for later reuse.

Reference: https://docs.datadoghq.com/database_monitoring/setup_postgres/selfhosted/
