# Maintenance monitoring

Nestswipe uses Datadog's existing native vulnerability management for host and
container CVEs. Do not install a separate vulnerability scanner or maintain a
second vulnerability database on the VM.

The custom additions report application-specific backup state and Ubuntu's reboot
flag to the existing host Agent every five minutes over its DogStatsD Unix socket.
They require no new Oracle resource, API key, public port or custom metric.

| Check | Failure condition |
| --- | --- |
| Production backup | Last attempted backup failed, no valid completed archive, or Saturday 03:00 Paris backup is still missing at 09:00. |
| Mac copy | No checksum-verified download acknowledgement for Monday 22:00 Paris by Tuesday 04:00, or the acknowledged archive predates the preceding Saturday. |
| Reboot | Ubuntu creates `/var/run/reboot-required`. |

Two failing samples trigger an alert; one healthy sample recovers. If checks stop
arriving for 20 minutes, their monitors report missing data. Unresolved alert/no-data
states remind the owner once per day. Paris deadlines account for daylight saving
and allow six hours for slow jobs/retries. A sleeping/offline Mac will eventually
alert; the job cannot wake it. An acknowledgement proves the transfer was verified
at that time, not that the Mac still has its files or that a database restore works.

## Native vulnerability detection and notifications

On 25 October 2026, production already had `sbom.enabled`,
`sbom.container_image.enabled` and `sbom.host.enabled` set to true. The Agent's
container-image/SBOM integrations were healthy and sending data. Datadog's findings
API confirmed both Nestswipe host findings and running-container findings.

The existing native notification rule **Critical and High Severity Findings**
(`n0p-rfx-u8t`) routes high/critical findings to its existing owner, with a daily
aggregation window. The monitoring follow-up adds its missing
`container_image_vulnerability` category while preserving all existing categories,
recipients and aggregation. Native notification rules report new issues; they are
not a daily email of the whole historical backlog. Review fix availability and
running-image status in Datadog when prioritizing remediation.

Agent configuration remains managed through Fleet. No separate vulnerability
scanner, scanner timer or CVE service-check monitor remains installed. Native
finding presence is verified at the account level; it does not prove every
language package is covered or that all version matches are exploitable.

References:
- https://docs.datadoghq.com/security/cloud_security_management/setup/agent/linux/
- https://docs.datadoghq.com/api/latest/security-monitoring/patch-a-vulnerability-based-notification-rule/

## Installation and deployment

Prerequisites: the existing host Agent/DogStatsD socket, systemd, Python 3.10+
with timezone data, and the existing backup installation. Normal app deployments
reinstall these versioned monitoring files without restarting the Agent or
changing its native security configuration. First installation or a monitoring-only
deployment:

```sh
sudo bash deploy/backup/install-production.sh
sudo bash deploy/security/install-monitoring.sh
```

Backup installation must precede updating the Mac downloader: the restricted key
now accepts `ack <archive-name> <sha256>` after successful local verification.
The server validates the name/digest against a retained archive manifest and writes
only `/var/lib/nestswipe-backup-receipts/mac`. The receipt directory belongs to
ubuntu (mode 700); the key still cannot execute a shell or choose a write path.
Never acknowledge a backup that has not been checked on the Mac. Existing local
archives can be checksum-verified and acknowledged without downloading again.

Publish only the three custom monitors using the existing `dd-auth` procedure,
explicit expected organization UUID, and existing owner's notification handle:

```sh
python3 deploy/datadog/publish_monitor.py --org-uuid "$EXPECTED_ORG_UUID" \
  --notify "$NOTIFY_HANDLE" --definitions deploy/datadog/maintenance-*-monitor.json
# Repeat with --apply after reviewing validation and live service-check data.
```

The publisher validates every definition, refuses unmanaged name collisions and
reads saved settings back. Never store credentials or the notification handle in
source. Monitor notification delivery depends on Datadog and the owner's routing.

## Operations and verification

```sh
sudo systemctl start nestswipe-security-report.service
sudo journalctl -u nestswipe-security-report --since today
sudo systemctl list-timers 'nestswipe-security-*'
```

Confirm statuses in the intended Datadog account; a successful local socket send
alone does not prove backend ingestion. Local checks are covered by
`python3 -m unittest discover -s deploy/security -p 'test_*.py'` and the Mac transfer
tests, including failure/retention/acknowledgement behavior.

To remove the custom checks, disable/stop the report timer/service, then mute or
remove only their three monitors to avoid intentional missing-data alerts. Preserve
native vulnerability collection/notifications, the backup cron, keys and archives.
Reverting only download acknowledgements causes the Mac monitor to become stale.

## Automatic overnight reboots

`nestswipe-reboot-watch.timer` checks every five minutes on the VM, independently
of a developer laptop. `install-monitoring.sh`, called by every normal deployment,
installs the versioned Python watcher, systemd units, monitor definition and
`reboot-policy.json`. A new VM uses the same installation path and existing
project secrets; no manual VM-only cron entry or Codex automation is required.

The default maintenance window is **02:00 inclusive to 05:00 exclusive,
Europe/Paris**, including daylight-saving changes. A reboot requires all of:

- The uniquely named, managed Datadog reboot monitor is `Alert` in the configured
  personal organization, with the expected type and query. IDs are discovered,
  rather than tied to one VM. API errors and other states defer maintenance.
- Ubuntu's `/var/run/reboot-required` is present and the application and Agent
  are healthy.
- No authenticated client activity for at least 15 minutes. Signed-in browser
  tabs POST `/api/v1/auth/presence` every minute and on focus/visibility changes.
  Every other authenticated API request also renews activity, covering older
  browser versions while they are being used. A suspended/offline browser whose
  heartbeats have stopped for 15 minutes counts as disconnected; stored JWTs alone
  do not represent connected clients.
- No SSH/login sessions, backup, download, deployment or dpkg/APT operation.
- No unverified earlier reboot and no reboot in the preceding 24 hours.

Migration 022 creates a singleton presence row initialized to the current time,
so a fresh installation must observe at least 15 minutes before acting. The
watcher atomically reserves a five-minute maintenance lease only while the row
is idle. All authenticated requests serialize against that reservation and
receive `503` with `Retry-After: 60` during the handoff; a newly arriving request
cannot invalidate the idle decision after reservation. A failed preflight clears
the lease; it also expires automatically. Health checks remain available. Photo
URLs authenticated separately with query tokens are read-only and do not renew
presence; the browser heartbeat covers signed-in photo viewers.

The watcher holds the existing exclusive backup lock and POSIX dpkg locks through
the reboot request, and checks SSH, the time window and the monitor again after
reserving. A persisted attempt records the boot ID before requesting reboot.
An incomplete attempt prevents reboot loops. After boot, the timer verifies a
changed boot ID, healthy containers, public API and Agent, disappearance of the
reboot flag, and Datadog monitor recovery to `OK`. Failures remain in the journal
and the attempt remains unverified; it never blindly retries rebooting.

Installation prerequisites are the normal production paths/container names,
database migrations, a configured host Agent, the backup installation, and the
existing Datadog API key and dedicated `DD_REBOOT_APP_KEY` in `deploy/.env`.
Normal deployments run `provision-reboot-key.py --provision --server ...`:
the operator's local application key must initially permit `user_app_keys`.
The script creates or recovers one named key scoped only to `monitors_read`,
saves it in the ignored local `.env`, and sends only that dedicated key over SSH
to the VM's existing `.env`. Later deployments reuse it; they never send the
administrative application key. Initial provisioning validates the organization
UUID with the operator credential; runtime checks validate the numeric
organization ID in the monitor response using only `monitors_read`.
No secret is embedded in source or systemd units. When deploying a clean source
export, set `NESTSWIPE_ENV_FILE` to the operator's existing local secrets file.
Change the policy and commit it when changing org, installation path, public URL
or maintenance hours; the installer reapplies the committed policy on deployment.
Publish the updated reboot-monitor message with the existing publisher above.

```sh
# Normal deploy installs the watcher and applies migration 022 automatically.
./deploy/deploy.sh

# Standalone installation, after the app and migrations have been deployed:
sudo bash deploy/security/install-monitoring.sh
sudo systemctl list-timers nestswipe-reboot-watch.timer
sudo /usr/local/sbin/nestswipe-reboot-watch --check
sudo journalctl -u nestswipe-reboot-watch.service --since today

# Pause automatic reboots; a later deployment intentionally enables them again.
sudo systemctl disable --now nestswipe-reboot-watch.timer

# Watcher boundary, race, failure, recovery and DST tests:
python3 -m unittest discover -s deploy/security -p 'test_*.py'
```

`--check` never reserves maintenance or requests a reboot; it may report an SSH
session because the administrator running it is connected. It takes the same
maintenance locks briefly. Do not delete `attempt.json` to bypass failed recovery;
investigate and verify the host, monitor and pending reboot first.

## Fleet follow-up, 25 October 2026

The running host Agent is Fleet-managed 7.84.5. Retrying its reversible upgrade
experiment to 7.84.6-1 still failed because Fleet has no Linux ARM64 package for
that version. The public Fleet API also denied version lookup with the available
credentials. Do not bypass Fleet with an APT reinstall. No automatic Agent-upgrade
loop is installed; retry the patch when Fleet makes the ARM64 package available.
