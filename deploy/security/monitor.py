#!/usr/bin/env python3
"""Read local maintenance state; submit service checks via the existing Agent socket."""

import re
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BACKUPS = Path("/home/ubuntu/nestswipe-backups")
BACKUP_STATE = Path("/var/lib/nestswipe-backup")
RECEIPT = Path("/var/lib/nestswipe-backup-receipts/mac")
NAME = re.compile(r"nestswipe-(\d{8}T\d{6}Z)")
UTC = timezone.utc  # noqa: UP017 -- the Ubuntu host uses Python 3.10


def weekly_due(now, weekday, hour):
    """Most recent weekly Paris deadline with six hours allowed for completion."""
    local = datetime.fromtimestamp(now, ZoneInfo("Europe/Paris"))
    due = (local - timedelta(days=(local.weekday() - weekday) % 7)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    if local < due + timedelta(hours=6):
        due -= timedelta(days=7)
    return due.timestamp()


def backup_check(now, backups=BACKUPS, state=BACKUP_STATE):
    completed = []
    for path in backups.glob("nestswipe-*"):
        match = NAME.fullmatch(path.name)
        if not match or path.is_symlink() or not path.is_dir():
            continue
        try:
            name, digest, size = (path / "manifest.txt").read_text().split()
            if (
                name != path.name
                or not re.fullmatch("[a-f0-9]{64}", digest)
                or int(size) <= 0
                or (path / "backup.tar.gz.enc").stat().st_size != int(size)
            ):
                continue
            stamp = (
                datetime.strptime(match[1], "%Y%m%dT%H%M%SZ")
                .replace(tzinfo=UTC)
                .timestamp()
            )
            if stamp <= now + 300:
                completed.append(stamp)
        except (OSError, ValueError):
            continue
    if not completed:
        return 2, "No completed production backup with a valid manifest and size."
    latest = max(completed)
    result = state / "last-result"
    if result.exists():
        status, stamp = result.read_text().split()
        if status not in {"ok", "failed"}:
            raise ValueError("Invalid backup result state")
        if status == "failed" and int(stamp) >= latest:
            return (
                2,
                "Latest production backup attempt failed; inspect /var/log/nestswipe-backup.log.",
            )
    if latest < weekly_due(now, 5, 3):
        return (
            2,
            "Saturday 03:00 Paris backup missed its six-hour completion allowance.",
        )
    return (
        0,
        "Completed production backup is current (manifest and size checked, not a restore test).",
    )


def download_check(now, receipt=RECEIPT):
    if not receipt.exists():
        return 2, "No verified Mac download acknowledgement received."
    stamp, name = receipt.read_text().split()
    match = NAME.fullmatch(name)
    if not match:
        raise ValueError("Invalid Mac acknowledgement")
    stamp = int(stamp)
    created = (
        datetime.strptime(match[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).timestamp()
    )
    due = weekly_due(now, 0, 22)
    # Monday's download must contain the preceding Saturday's backup or newer.
    expected_backup = weekly_due(due + 1, 5, 3)
    if stamp > now + 300 or created > stamp + 300:
        return 2, "Invalid future timestamp in Mac acknowledgement."
    if stamp < due or created < expected_backup:
        return (
            2,
            "Monday 22:00 Paris verified Mac download missed its six-hour allowance; check Mac power, network and cron log.",
        )
    return (
        0,
        "Mac acknowledged a checksum-verified backup for the current weekly deadline.",
    )


def send(name, status, message):
    message = message.replace("\n", " ").replace("|", "/")[:1800]
    packet = (
        f"_sc|nestswipe.maintenance.{name}|{status}|h:nestswipe-vnic"
        f"|#env:prod,service:nestswipe-security|m:{message}"
    )
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
        client.connect("/var/run/datadog/dsd.socket")
        client.send(packet.encode())


def report():
    now = datetime.now(UTC).timestamp()
    checks = {}
    for name, function in [("backup", backup_check), ("mac_download", download_check)]:
        try:
            checks[name] = function(now)
        except (OSError, ValueError, TypeError, KeyError):
            checks[name] = (
                2,
                "Unable to read maintenance state; inspect reporter journal.",
            )
    checks["reboot"] = (
        (2, "Host reboot required; schedule maintenance.")
        if Path("/var/run/reboot-required").exists()
        else (0, "No reboot pending.")
    )
    for name, (status, message) in checks.items():
        send(name, status, message)
    print({key: value[0] for key, value in checks.items()})


if __name__ == "__main__":
    report()
