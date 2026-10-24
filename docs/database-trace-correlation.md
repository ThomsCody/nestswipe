# Database trace correlation

The backend uses SQLAlchemy's asynchronous Psycopg 3 driver. Production and
the local Datadog Compose overlay enable `DD_DBM_PROPAGATION_MODE=full` and
name database spans `nestswipe-db` with `DD_PSYCOPG_SERVICE`.

DBM collection alone does not connect APM spans to database activity. Full
propagation adds the current database span's trace context to SQL comments.
The previous asyncpg driver used prepared statement objects that ddtrace
3.10.0 could not annotate, even with full propagation enabled. Existing traces
cannot acquire those missing comments retroactively.

All database URLs must use `postgresql+psycopg://`. Update an existing local
`.env` when upgrading. No database schema or stored-data migration is needed.

## Validation

Run ordinary backend tests, then exercise a disposable PostgreSQL database:

```sh
TEST_POSTGRES_URL='postgresql+psycopg://user:password@localhost/test_db' \
  python -m pytest tests/test_postgres_driver.py -v
```

These tests check PostgreSQL types, parameter binding, commit/rollback, and
observe `pg_stat_activity` to prove the server received the current trace ID.
The tests create only temporary objects and never modify application tables.

For production, run `scripts/verify_dbm_correlation.py` using `ddtrace-run`
inside the configured backend container. `--seconds 12` gives DBM time to
sample the read-only query. The script emits trace/span IDs, never credentials
or application rows. Search the resulting IDs in Datadog APM and DBM and
verify that the same span is returned by both APIs. Also verify an ordinary
authenticated API request still succeeds.

Only the backend container needs rebuilding/recreating. Hold the production
backup lock during replacement; PostgreSQL does not need restarting.

Rollback: restore the previous backend image, requirements and asyncpg URL,
then recreate only the backend under the same lock. Stored data is unchanged.

References:
- https://docs.datadoghq.com/database_monitoring/connect_dbm_and_apm/
- https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg
