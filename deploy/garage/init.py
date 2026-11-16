#!/usr/bin/env python3
"""Idempotently provision the private application bucket and access key."""

import argparse
from pathlib import Path
import subprocess


def initialize(container, directory, bucket):
    def run(*args):
        result = subprocess.run(
            ["docker", "exec", container, "/garage", *args],
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError("Garage initialization failed; inspect container status")
        return result.stdout

    key = (directory / "garage_access_key").read_text().strip()
    secret = (directory / "garage_secret_key").read_text().strip()
    # Garage rejects importing an existing key; keep provisioning repeatable.
    if key not in run("key", "list"):
        run("key", "import", "--yes", "-n", "nestswipe", key, secret)
    if bucket not in run("bucket", "list").split():
        run("bucket", "create", bucket)
    run("bucket", "allow", "--read", "--write", "--owner", "--key", key, bucket)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--container", default="deploy-garage-1")
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--bucket", default="listing-photos")
    a = p.parse_args()
    initialize(a.container, a.directory, a.bucket)
    print("Garage bucket and credentials ready")
