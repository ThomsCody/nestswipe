#!/usr/bin/env python3
"""Fail-closed overnight reboot watcher; --check never reserves or reboots."""

import argparse
import fcntl
import json
import os
import shlex
import subprocess
import time
from contextlib import ExitStack, contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

STATE = Path("/var/lib/nestswipe-reboot")
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
FLAG = Path("/var/run/reboot-required")
DEFINITION = Path("/etc/nestswipe-reboot/monitor.json")


def command(*args):
    return subprocess.check_output(args, text=True, timeout=30).strip()


def database(sql):
    return command(
        "docker",
        "exec",
        "deploy-postgres-1",
        "sh",
        "-c",
        'exec psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
        '-v ON_ERROR_STOP=1 -Atc "$1"',
        "sh",
        sql,
    )


def read_credentials(path):
    # Parse data only: never source a shell file as root or print its contents.
    result = {}
    for line in Path(path).read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() in {
            "DD_API_KEY",
            "DD_APP_KEY",
            "DD_REBOOT_APP_KEY",
            "DD_SITE",
        }:
            parts = shlex.split(value, comments=True)
            if len(parts) != 1:
                raise ValueError("Invalid Datadog credential configuration")
            result[key.strip()] = parts[0]
    if result.get("DD_SITE", "datadoghq.com") != "datadoghq.com":
        raise ValueError("Policy expects the personal US1 organization")
    return result


def credentials(project):
    result = read_credentials(Path(project) / "deploy/.env")
    if result.get("DD_REBOOT_APP_KEY"):
        result["DD_APP_KEY"] = result["DD_REBOOT_APP_KEY"]
    return result


def monitor_state(policy, *, values=None, definition=None):
    values = credentials(policy["project"]) if values is None else values
    headers = {
        "DD-API-KEY": values["DD_API_KEY"],
        "DD-APPLICATION-KEY": values["DD_APP_KEY"],
    }

    def get(path):
        with urlopen(
            Request("https://api.datadoghq.com" + path, headers=headers), timeout=20
        ) as response:
            return json.load(response)

    expected = json.loads(
        (DEFINITION if definition is None else definition).read_text()
    )
    matches = [
        m
        for m in get("/api/v1/monitor?" + urlencode({"name": expected["name"]}))
        if m["name"] == expected["name"]
    ]
    if len(matches) != 1:
        raise ValueError("Reboot monitor is missing or ambiguous")
    saved = matches[0]
    # Scoped monitor keys can read this field without user-profile permissions.
    if saved["org_id"] != policy["org_id"]:
        raise ValueError("Wrong Datadog organization")
    if (
        saved["type"] != expected["type"]
        or saved["query"] != expected["query"]
        or "managed_by:nestswipe" not in saved.get("tags", [])
    ):
        raise ValueError("Unexpected reboot monitor definition")
    # No Data, Unknown, Warning, and HTTP failures must never authorize a reboot.
    return saved["overall_state"]


def in_window(policy, now=None):
    local = datetime.fromtimestamp(
        time.time() if now is None else now, ZoneInfo(policy["timezone"])
    )
    return policy["start_hour"] <= local.hour < policy["end_hour"]


def healthy(policy):
    for name in ("backend", "postgres", "garage", "caddy"):
        if (
            command(
                "docker",
                "inspect",
                "--format",
                "{{.State.Running}}",
                f"deploy-{name}-1",
            )
            != "true"
        ):
            raise ValueError(f"{name} is not running")
    for service in ("datadog-agent", "ssh"):
        if command("systemctl", "is-active", service) != "active":
            raise ValueError(f"{service} is not active")
    with urlopen(policy["health_url"], timeout=10) as response:
        if json.load(response) != {"status": "ok"}:
            raise ValueError("Application health failed")


def no_sessions():
    if command("who") or command(
        "ss", "-Htn", "state", "established", "sport", "=", ":22"
    ):
        raise ValueError("SSH/login session connected")


def idle(policy, reserve=False):
    minutes = int(policy["idle_minutes"])
    if minutes < 15:
        raise ValueError("At least 15 idle minutes are required")
    condition = (
        f"id = 1 AND last_activity <= clock_timestamp() - interval '{minutes} minutes' "
        "AND (reboot_until IS NULL OR reboot_until < clock_timestamp())"
    )
    sql = (
        "UPDATE maintenance_presence SET reboot_until = clock_timestamp() + interval '5 minutes' "
        f"WHERE {condition} RETURNING id"
        if reserve
        else f"SELECT id FROM maintenance_presence WHERE {condition}"
    )
    # UPDATE emits a command tag as well as RETURNING output unless -q is used.
    return database(sql).splitlines()[:1] == ["1"]


def release():
    database("UPDATE maintenance_presence SET reboot_until = NULL WHERE id = 1")


@contextmanager
def maintenance_locks():
    # Hold the same exclusive lock used by backups, downloads and deployments.
    # dpkg uses POSIX record locks, not flock; hold both until shutdown starts.
    with ExitStack() as stack:
        backup = stack.enter_context(
            open("/home/ubuntu/nestswipe-backups/.backup.lock", "rb")
        )
        fcntl.flock(backup, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for path in ("/var/lib/dpkg/lock-frontend", "/var/lib/dpkg/lock"):
            lock = stack.enter_context(open(path, "r+b"))
            fcntl.lockf(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def write_state(value):
    temporary = STATE / "attempt.json.tmp"
    temporary.write_text(json.dumps(value) + "\n")
    os.replace(temporary, STATE / "attempt.json")


def verify_previous(policy, attempt, apply):
    if attempt.get("verified"):
        return
    if attempt["boot_id"] == BOOT_ID.read_text().strip():
        raise ValueError("Previous reboot has not completed; refusing another attempt")
    healthy(policy)
    if FLAG.exists():
        raise ValueError("Reboot completed but reboot-required flag remains")
    if not apply:
        print("Previous reboot is healthy; --apply will clear its reservation")
        return
    release()
    command("systemctl", "start", "nestswipe-security-report.service")
    if monitor_state(policy) != "OK":
        raise ValueError("Host recovered; waiting for Datadog reboot-monitor recovery")
    attempt["verified"] = True
    write_state(attempt)
    print("Reboot verified: new boot, application and Agent healthy, monitor recovered")


def run(policy, apply=False):
    attempt_path = STATE / "attempt.json"
    attempt = json.loads(attempt_path.read_text()) if attempt_path.exists() else None
    if attempt and not attempt.get("verified"):
        verify_previous(policy, attempt, apply)
        return
    if not FLAG.exists():
        print("No reboot required")
        return
    if monitor_state(policy) != "Alert":
        print("Deferred: reboot monitor is not Alert")
        return
    if attempt and time.time() - attempt["timestamp"] < policy["cooldown_hours"] * 3600:
        print("Deferred: reboot cooldown")
        return
    # Dry runs still check the other conditions in daylight, but can never reboot.
    window = in_window(policy)
    if apply and not window:
        print("Deferred: outside 02:00–05:00 Europe/Paris maintenance window")
        return
    healthy(policy)
    no_sessions()
    with maintenance_locks():
        if not idle(policy):
            print(
                "Deferred: client activity within 15 minutes or maintenance already reserved"
            )
            return
        if not apply:
            print(
                f"Check passed; overnight window={window}; no reboot scheduled by --check"
            )
            return
        # The conditional UPDATE serializes with every authenticated request.
        if not idle(policy, reserve=True):
            print("Deferred: client activity arrived during checks")
            return
        requested = False
        try:
            no_sessions()
            if (
                not in_window(policy)
                or not FLAG.exists()
                or monitor_state(policy) != "Alert"
            ):
                raise ValueError("Reboot conditions changed during checks")
            write_state(
                {
                    "boot_id": BOOT_ID.read_text().strip(),
                    "timestamp": time.time(),
                    "verified": False,
                }
            )
            command("systemctl", "reboot")
            requested = True
            print("Reboot requested after an atomic idle reservation", flush=True)
            # Keep maintenance locks until systemd stops this unit for shutdown.
            time.sleep(60)
        finally:
            if not requested:
                release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--check", action="store_true")
    parser.add_argument(
        "--policy", type=Path, default=Path("/etc/nestswipe-reboot/policy.json")
    )
    args = parser.parse_args()
    os.umask(0o077)
    try:
        with open(STATE / "watch.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(json.loads(args.policy.read_text()), args.apply)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        # Do not log response bodies, environment values, or credential contents.
        print(f"Deferred safely: {type(exc).__name__}: {exc}", flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
