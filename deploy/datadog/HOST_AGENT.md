# Production host Agent

Datadog runs as systemd services on the production Ubuntu VM. Fleet Automation
owns Agent upgrades and remote configuration. Application deployments check
the services and sockets but never reinstall the Agent or overwrite its files.
There is no production Agent container.

- Host identity: `nestswipe-vnic` (preserved from the former container).
- Remote Configuration and remote updates are enabled.
- APM: `/var/run/datadog/apm.socket`; custom metrics: `/var/run/datadog/dsd.socket`.
- Backend mounts the socket directory read-only. APM TCP and DogStatsD UDP
  listeners are disabled; no public monitoring ports are needed.
- systemd preserves the socket directory across Agent restarts and upgrades,
  so application bind mounts continue to see newly created sockets.
- Docker logs and integrations use the local Docker socket. `dd-agent` belongs
  to the Docker group, which effectively grants host-administrator capabilities.
- Network monitoring uses the root `datadog-agent-sysprobe` service.
- PostgreSQL is discovered by its Docker image and private container IP.
  No database port is published. See [database setup](POSTGRES.md).

## First installation / replacement VM

Requires Docker Compose, curl, Python 3 with PyYAML (`python3-yaml` on Ubuntu),
the existing `deploy/.env`, and provisioned database monitoring credentials.
Run from the production checkout:

```sh
sudo python3 deploy/datadog/setup-host-agent.py
sudo systemctl start datadog-agent
bash deploy/datadog/check-host-agent.sh
```

The installer runs without starting the Agent so an existing collector can be
stopped before the cutover. `--agent-minor-version` optionally chooses the
initial version; it never pins or downgrades a subsequent Fleet upgrade.
The bootstrap is idempotent. An existing installation without its bootstrap
marker requires explicit `--configure-existing` after inspection.

Secrets are read locally from Compose's resolved environment and written only
to root-owned Agent configuration files readable by the `dd-agent` group.
Installer logs and initial configuration backups are private under
`/var/lib/nestswipe-agent`. Never copy these into the repository.

After rotating the database monitoring password, run:

```sh
sudo python3 deploy/datadog/setup-host-agent.py --refresh-db-credentials
```

## Verification

```sh
sudo datadog-agent status
sudo /opt/datadog-agent/embedded/bin/installer status
bash deploy/datadog/check-host-agent.sh
curl --fail --silent --show-error https://nestswipe.freeddns.org/api/v1/health
```

Check authorized Remote Configuration, healthy PostgreSQL/DBM and Docker checks,
APM traces, log delivery, DogStatsD packets, and network monitoring. In Datadog,
open Fleet Automation for `nestswipe-vnic` and verify remote Agent management.
Limit Agent Upgrade and Agent Configuration Management permissions to trusted
administrators. Configuration changes through Fleet persist across app deploys.

References:
- https://docs.datadoghq.com/agent/guide/setup_remote_config/
- https://docs.datadoghq.com/extend/dogstatsd/unix_socket/
