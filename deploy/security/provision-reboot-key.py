#!/usr/bin/env python3
"""Provision/reuse a monitor-read-only key and sync only that key to a VM."""

import argparse
import inspect
import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from reboot_watch import monitor_state, read_credentials

KEY_NAME = "Nestswipe overnight reboot watcher (monitors_read)"


def store_key(path, key):
    if not re.fullmatch(r"[a-fA-F0-9]{40}", key):
        raise ValueError("Unexpected application key format")
    if path.is_symlink():
        raise ValueError("Refusing to replace a symlinked secrets file")
    lines = path.read_text().splitlines()
    lines = [
        line for line in lines if line.partition("=")[0].strip() != "DD_REBOOT_APP_KEY"
    ]
    content = "\n".join([*lines, "DD_REBOOT_APP_KEY=" + key]) + "\n"
    if content == path.read_text():
        return
    temporary = path.with_name(".env.reboot-key.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with open(descriptor, "w") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def request(values, method, path, data=None):
    headers = {
        "DD-API-KEY": values["DD_API_KEY"],
        "DD-APPLICATION-KEY": values["DD_APP_KEY"],
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    with urlopen(
        Request(
            "https://api.datadoghq.com" + path,
            headers=headers,
            method=method,
            data=None if data is None else json.dumps(data).encode(),
        ),
        timeout=20,
    ) as response:
        return json.load(response)


def provision(values, org_uuid):
    identity = request(values, "GET", "/api/v2/current_user")
    if identity["data"]["relationships"]["org"]["data"]["id"] != org_uuid:
        raise ValueError("Wrong Datadog organization")
    matches = []
    for page in range(100):
        result = request(
            values,
            "GET",
            f"/api/v2/current_user/application_keys?page[size]=100&page[number]={page}",
        )
        matches.extend(
            key for key in result["data"] if key["attributes"]["name"] == KEY_NAME
        )
        if len(result["data"]) < 100:
            break
    else:
        raise ValueError("Application key listing did not complete")
    if len(matches) > 1:
        raise ValueError("Duplicate watcher keys; resolve before provisioning")
    if matches:
        saved = request(
            values, "GET", "/api/v2/current_user/application_keys/" + matches[0]["id"]
        )["data"]
    else:
        saved = request(
            values,
            "POST",
            "/api/v2/current_user/application_keys",
            {
                "data": {
                    "type": "application_keys",
                    "attributes": {"name": KEY_NAME, "scopes": ["monitors_read"]},
                }
            },
        )["data"]
    if saved["attributes"]["scopes"] != ["monitors_read"]:
        raise ValueError(
            "Existing watcher key has unexpected scopes; refusing to deploy it"
        )
    key = saved["attributes"].get("key")
    if not key:
        raise ValueError(
            "Existing key cannot be retrieved; restore DD_REBOOT_APP_KEY from secret storage"
        )
    return key


def sync(server, key):
    if not re.fullmatch(r"[A-Za-z0-9_.@:-]+", server) or server.startswith("-"):
        raise ValueError("Expected an SSH destination, without shell syntax or options")
    # The administrative local application key is never sent to the VM.
    remote = (
        "import os,json,sys,re\nfrom pathlib import Path\n"
        + inspect.getsource(store_key)
        + "\nstore_key(Path('/home/ubuntu/nestswipe/deploy/.env'), json.load(sys.stdin))\n"
    )
    subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "--",
            server,
            "python3 -c " + shlex.quote(remote),
        ],
        input=json.dumps(key),
        text=True,
        check=True,
        timeout=30,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file", type=Path, default=Path(__file__).resolve().parents[1] / ".env"
    )
    parser.add_argument(
        "--provision",
        action="store_true",
        help="Create or recover the dedicated key if absent locally",
    )
    parser.add_argument(
        "--server", help="Sync the validated dedicated key to this SSH destination"
    )
    args = parser.parse_args()
    policy = json.loads(Path(__file__).with_name("reboot-policy.json").read_text())
    definition = (
        Path(__file__).parent.parent / "datadog/maintenance-reboot-monitor.json"
    )
    values = read_credentials(args.env_file)
    key = values.get("DD_REBOOT_APP_KEY")
    if not key:
        if not args.provision:
            parser.error("DD_REBOOT_APP_KEY is missing; rerun with --provision")
        key = provision(values, policy["org_uuid"])
        # Persist before validation in case newly created-key propagation is slow.
        store_key(args.env_file, key)
    scoped = {**values, "DD_APP_KEY": key}
    for attempt in range(6):
        try:
            monitor_state(policy, values=scoped, definition=definition)
            break
        except HTTPError as error:
            if error.code != 403 or attempt == 5:
                raise
            time.sleep(5)
    if args.server:
        sync(args.server, key)
    print(
        "Dedicated watcher credential validated"
        + (" and synced" if args.server else "")
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        # Never print response bodies, secret file contents, or headers.
        raise SystemExit(f"Credential setup failed: {type(error).__name__}") from None
