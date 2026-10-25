#!/usr/bin/env python3
"""Read local maintenance state; submit service checks via the existing Agent socket."""

import argparse
import json
import os
import re
import socket
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

STATE = Path("/var/lib/nestswipe-security")
BACKUPS = Path("/home/ubuntu/nestswipe-backups")
BACKUP_STATE = Path("/var/lib/nestswipe-backup")
RECEIPT = Path("/var/lib/nestswipe-backup-receipts/mac")
CONTAINERS = [
    "deploy-backend-1",
    "deploy-seloger-browser-1",
    "deploy-caddy-1",
    "deploy-postgres-1",
    "deploy-minio-1",
]
NAME = re.compile(r"nestswipe-(\d{8}T\d{6}Z)")
UTC = timezone.utc  # noqa: UP017 -- the Ubuntu host uses Python 3.10


def atomic_json(path, data):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
        json.dump(data, f)
        temporary = f.name
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


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


def inventory():
    output = subprocess.check_output(
        ["docker", "inspect", "--format", "{{.Name}} {{.Image}}", *CONTAINERS],
        text=True,
        timeout=30,
    )
    found = dict(line.lstrip("/").split() for line in output.splitlines())
    if set(found) != set(CONTAINERS):
        raise ValueError("Incomplete production image inventory")
    return found


def summarize(report):
    results = report.get("Results", [])
    os_packages = sum(
        len(r.get("Packages") or []) for r in results if r.get("Class") == "os-pkgs"
    )
    os_info = report.get("Metadata", {}).get("OS", {})
    if not os_info.get("Family") or not os_packages:
        raise ValueError("Unsupported or empty OS inventory; scan is inconclusive")
    findings = sorted(
        {
            (
                v["VulnerabilityID"],
                v["PkgName"],
                v.get("InstalledVersion", ""),
                v["FixedVersion"],
                v.get("Severity", "UNKNOWN"),
            )
            for r in results
            for v in r.get("Vulnerabilities") or []
            if v.get("FixedVersion")
        }
    )
    return {"os": os_info, "os_packages": os_packages, "fixable": findings}


def scan(state=STATE):
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    started = datetime.now(UTC).timestamp()
    try:
        images = inventory()
        reports = {}
        with tempfile.TemporaryDirectory(dir=state) as temporary:
            for container, image_id in images.items():
                path = Path(temporary) / (container + ".json")
                subprocess.run(
                    [
                        "/usr/local/bin/nestswipe-trivy",
                        "image",
                        "--image-src",
                        "docker",
                        "--scanners",
                        "vuln",
                        "--no-progress",
                        "--list-all-pkgs",
                        "--format",
                        "json",
                        "--cache-dir",
                        "/var/cache/nestswipe-trivy",
                        "--timeout",
                        "15m",
                        "--parallel",
                        "1",
                        "--output",
                        str(path),
                        image_id,
                    ],
                    check=True,
                    timeout=1000,
                )
                reports[container] = summarize(json.loads(path.read_text()))
                os.replace(path, state / (container + ".json"))
        if inventory() != images:
            raise ValueError(
                "Images changed during scan; retry against deployed images"
            )
        database = json.loads(
            Path("/var/cache/nestswipe-trivy/db/metadata.json").read_text()
        )
        updated = (
            datetime.strptime(database["UpdatedAt"][:19], "%Y-%m-%dT%H:%M:%S")
            .replace(tzinfo=UTC)
            .timestamp()
        )
        completed = datetime.now(UTC).timestamp()
        if (
            not database["UpdatedAt"].endswith("Z")
            or not 0 <= completed - updated <= 48 * 3600
        ):
            raise ValueError("Vulnerability database is older than 48 hours or invalid")
        atomic_json(
            state / "scan.json",
            {
                "status": "ok",
                "started": started,
                "completed": completed,
                "database_updated": updated,
                "images": images,
                "reports": reports,
            },
        )
    except Exception as exc:
        # Preserve previous reports for diagnosis, but never emit a stale green state.
        atomic_json(
            state / "scan.json",
            {"status": "failed", "started": started, "error": type(exc).__name__},
        )
        raise


def scan_checks(now, state=STATE, images=None, unit_result="success"):
    if unit_result != "success":
        return (
            2,
            "Scan service failed, timed out or was killed; inspect its journal.",
        ), (3, "Scan failed.")
    path = state / "scan.json"
    if not path.exists():
        return (2, "No successful container scan."), (3, "Scan unavailable.")
    data = json.loads(path.read_text())
    if data.get("status") != "ok":
        return (2, "Container scan failed; inspect nestswipe-security-scan journal."), (
            3,
            "Scan failed.",
        )
    if now - data["completed"] > 36 * 3600 or data["completed"] > now + 300:
        return (
            2,
            "Container scan is older than 36 hours or has an invalid timestamp.",
        ), (3, "Scan stale.")
    if not 0 <= now - data.get("database_updated", 0) <= 48 * 3600:
        return (2, "Vulnerability database is stale or unknown."), (
            3,
            "Database stale.",
        )
    if data["images"] != (inventory() if images is None else images):
        return (2, "Production images changed since last scan."), (
            3,
            "New images await scanning.",
        )
    findings = [
        finding for report in data["reports"].values() for finding in report["fixable"]
    ]
    urgent = sum(f[-1] in {"HIGH", "CRITICAL"} for f in findings)
    status = 2 if urgent else (1 if findings else 0)
    message = (
        f"{len(findings)} fixable package/advisory matches across five images; "
        f"{urgent} HIGH/CRITICAL. Review /var/lib/nestswipe-security/*.json. "
        "Matches require applicability review; MinIO is included but unchanged."
    )
    return (0, "Exact deployed image IDs scanned within 36 hours."), (status, message)


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
    try:
        result = subprocess.check_output(
            [
                "systemctl",
                "show",
                "nestswipe-security-scan.service",
                "--property=Result",
                "--value",
            ],
            text=True,
            timeout=10,
        ).strip()
        checks["scan"], checks["vulnerabilities"] = scan_checks(now, unit_result=result)
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        checks["scan"] = (2, "Unable to inspect current image scan state.")
        checks["vulnerabilities"] = (3, "Scan state unavailable.")
    for name, (status, message) in checks.items():
        send(name, status, message)
    print(json.dumps({key: value[0] for key, value in checks.items()}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["scan", "report"])
    args = parser.parse_args()
    if args.action == "scan":
        scan()
    else:
        report()
