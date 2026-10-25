# Maintenance monitoring

The existing host Datadog Agent receives service checks every five minutes over
its local DogStatsD Unix socket. No new Oracle resource, API key, public port,
Datadog security product or custom metric is needed. Notifications use the same
owner handle as the existing Nestswipe alert, supplied at publication time rather
than stored in source.

| Check | Failure condition |
| --- | --- |
| Production backup | Last attempted backup failed, no valid completed archive, or Saturday 03:00 Paris backup is still missing at 09:00. |
| Mac copy | No checksum-verified download acknowledgement for Monday 22:00 Paris by Tuesday 04:00, or the acknowledged archive predates the preceding Saturday. |
| Reboot | Ubuntu creates `/var/run/reboot-required`. |
| Scan health | Failed/inconclusive scan, more than 36 hours since completion, vulnerability database older than 48 hours, or deployed image IDs changed. |
| Fixable vulnerabilities | High/critical matches alert; other severities warn. Findings with no published fixed version remain in the reports. |

Two failing samples trigger an alert; one healthy sample recovers. If checks stop
arriving for 20 minutes, their monitors report missing data. Unresolved alert/no-data
states remind the owner once per day. Paris deadlines account for daylight saving
and allow six hours for slow jobs/retries. A sleeping/offline Mac will eventually
alert; the job cannot wake it. An acknowledgement proves the transfer was verified
at that time, not that the Mac still has its files or that a database restore works.

## Container scans

A systemd timer scans the exact image IDs of the five production containers daily
at 05:15 Europe/Paris, with up to 15 minutes of jitter. Deployment also requests a
scan after containers start. Trivy scans OS packages and supported language
packages/binaries; it does not inspect mounted databases, photo volumes or runtime
secrets. Secret scanning is disabled. Scanning does not pull replacement application
images, patch containers, restart services or reboot the host.

The scanner runs with a 50% single-CPU quota, low CPU/I/O priority, a 2 GiB memory
limit and a 100-minute overall timeout. Each image has a 15-minute scanner timeout.
Only the latest report per container and a summary are retained under root-only
`/var/lib/nestswipe-security/`. The vulnerability database/cache is under
`/var/cache/nestswipe-trivy/`. An image with no recognized OS package inventory is
inconclusive, never green. A deployment during the scan invalidates the result.

The first full scan on 25 October found matches beyond the earlier OS/runtime
package audits: Python package metadata, Caddy's embedded Go dependencies,
PostgreSQL image's `gosu` helper, and MinIO OS/Go dependencies. Counts are package
and advisory matches, not a count of exploitable application vulnerabilities.

MinIO is included in detection but remains unchanged, as requested. Finding a
published fix does not establish exploitability or guarantee a compatible upgrade;
review applicability and test updates. There is no blanket exclusion of existing
findings. Host packages and build-only frontend dependencies are outside this daily
container scan; existing dependency CI and Ubuntu updates remain separate.

## Installation and deployment

Prerequisites: the existing host Agent/DogStatsD socket, Docker, systemd, Python 3.10+
with timezone data, and the existing backup installation. On a replacement ARM64 VM,
install the reviewed scanner first:

- Version: Trivy **0.76.1**.
- Official release: <https://github.com/aquasecurity/trivy/releases/tag/v0.76.1>.
- Asset: `trivy_0.76.1_Linux-ARM64.tar.gz`.
- Archive SHA256: `e174dff2a6dba5e3ae41f8d0537a6324405bd08132497340304c6b20e0f16a1f`.
- Extracted binary SHA256: `b422130ea54e53e142e65c838662e48919ce9c3f23f17d80066b43e70550cb85`.
- Install the verified binary, owned by root, mode 755, at `/usr/local/bin/nestswipe-trivy`.

`install-monitoring.sh` verifies the binary checksum before installing the jobs.
Update the pin and verify upstream provenance when upgrading the scanner itself.
Normal app deployments reinstall versioned monitoring files without restarting the
Agent. First installation or a monitoring-only deployment:

```sh
sudo bash deploy/backup/install-production.sh
sudo bash deploy/security/install-monitoring.sh
sudo systemctl start --no-block nestswipe-security-scan.service
```

Backup installation must precede updating the Mac downloader: the restricted key
now accepts `ack <archive-name> <sha256>` after successful local verification.
The server validates the name/digest against a retained archive manifest and writes
only `/var/lib/nestswipe-backup-receipts/mac`. The receipt directory belongs to
ubuntu (mode 700); the key still cannot execute a shell or choose a write path.
Never acknowledge a backup that has not been checked on the Mac. Existing local
archives can be checksum-verified and acknowledged without downloading again.

Publish just these monitors using the existing `dd-auth` authentication procedure,
explicit expected organization UUID, and the existing owner's notification handle:

```sh
python3 deploy/datadog/publish_monitor.py --org-uuid "$EXPECTED_ORG_UUID" \
  --notify "$NOTIFY_HANDLE" --definitions deploy/datadog/maintenance-*-monitor.json
# Repeat with --apply only after reviewing validation and live service-check data.
```

The publisher validates every definition, refuses unmanaged name collisions and
reads saved settings back. Never store credentials or the notification handle in
source. Monitor notification delivery depends on Datadog and the owner's routing.

## Operations and verification

```sh
sudo systemctl start nestswipe-security-report.service
sudo journalctl -u nestswipe-security-report -u nestswipe-security-scan --since today
sudo systemctl list-timers 'nestswipe-security-*'
sudo cat /var/lib/nestswipe-security/scan.json
```

Confirm statuses in the intended Datadog account; a successful local socket send
alone does not prove backend ingestion. Local checks are covered by
`python3 -m unittest discover -s deploy/security -p 'test_*.py'` and the existing
Mac transfer tests, including failure/retention/acknowledgement behavior.

To remove these jobs, disable/stop their timers and the scan/report services, then
mute or remove their five Datadog monitors to avoid intentional missing-data alerts.
Do not disable the backup cron or change keys/archives. Reverting only the download
acknowledgement causes the Mac monitor to become stale.

## Fleet follow-up, 25 October 2026

The running host Agent is Fleet-managed 7.84.5. Retrying its reversible upgrade
experiment to 7.84.6-1 still failed because Fleet has no Linux ARM64 package for
that version. The public Fleet API also denied version lookup with the available
credentials. Do not bypass Fleet with an APT reinstall. No automatic Agent-upgrade
loop is installed; retry the patch when Fleet makes the ARM64 package available.
