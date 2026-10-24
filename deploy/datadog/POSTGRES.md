# PostgreSQL Database Monitoring

Production PostgreSQL 16 uses `pg_stat_statements`, a dedicated `datadog`
login with `pg_monitor`, and the host Datadog Agent. The Agent connects
over the private Docker network; no database port is published.

`postgres.yaml` enables DBM, schema metadata, and table/index statistics.
Query metrics, activity sampling, and sampled explain plans use the Agent's
defaults. SQL literal obfuscation remains enabled. This setup does not enable
raw SQL logging or `auto_explain`. The login has no grants to read application
table rows; the restricted explain function runs with the owner's privileges.

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

## Rollback

Remove the PostgreSQL `command` block and disable the PostgreSQL integration
in Fleet or remove `/etc/datadog-agent/conf.d/postgres.d/conf.yaml` on the host.
Under the backup lock, recreate only PostgreSQL with
`--no-deps --pull never --wait` as above, then restart the host Agent.
The inactive extension and monitoring role can remain for later reuse.

Reference: https://docs.datadoghq.com/database_monitoring/setup_postgres/selfhosted/
