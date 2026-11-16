#!/usr/bin/env python3
"""Materialize Compose secrets from the existing .env without exposing values."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


EXPRESSIONS = {
    "postgres_password": "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}",
    "database_url": (
        "postgresql+psycopg://${POSTGRES_USER:?POSTGRES_USER is required}:"
        "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}@postgres:5432/"
        "${POSTGRES_DB:?POSTGRES_DB is required}"
    ),
    "jwt_secret": "${JWT_SECRET:?JWT_SECRET is required}",
    "decodo_api_key": "${DECODO_API_KEY:-}",
    "proxy_user": "${PROXY_USER:-}",
    "proxy_password": "${PROXY_PASSWORD:-}",
    "sendgrid_api_key": "${SENDGRID_API_KEY:-}",
}
BROWSER_SECRETS = {"proxy_user", "proxy_password"}


def read_values(env_file: Path) -> dict[str, str]:
    # Let Compose itself interpret quoting, interpolation and dollar signs,
    # exactly as the previous production environment configuration did.
    config = {
        "services": {"credentials": {"image": "unused", "environment": EXPRESSIONS}}
    }
    # The specified .env is authoritative; unrelated caller credentials must
    # never silently replace the production values.
    variables = {name.upper() for name in EXPRESSIONS} | {
        "POSTGRES_USER",
        "POSTGRES_DB",
    }
    environment = {k: v for k, v in os.environ.items() if k not in variables}
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-p",
            "nestswipe-secret-provision",
            "-f",
            "-",
            "config",
            "--format",
            "json",
        ],
        input=json.dumps(config),
        text=True,
        capture_output=True,
        env=environment,
    )
    if result.returncode:
        # Compose diagnostics can contain interpolated values. Do not echo them.
        raise RuntimeError("Cannot resolve credentials; check required values in .env")
    resolved = json.loads(result.stdout)["services"]["credentials"]["environment"]
    # `compose config` escapes literal dollars for a future Compose invocation.
    # Files are consumed directly, so undo that serialization exactly once.
    return {name: value.replace("$$", "$") for name, value in resolved.items()}


def provision(values: dict[str, str], directory: Path) -> None:
    if directory.is_symlink():
        raise RuntimeError("Refusing a symlinked secrets directory")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    # Check every existing file before changing anything. An old .env must not
    # silently rotate live credentials after this one-time migration.
    for name, value in values.items():
        path = directory / name
        if path.is_symlink():
            raise RuntimeError(f"Refusing a symlinked secret: {name}")
        if path.exists() and path.read_bytes() != value.encode("utf-8"):
            raise RuntimeError(
                f"Existing secret differs from .env: {name}; reconcile explicitly"
            )
    for name, value in values.items():
        path = directory / name
        # The browser runs as uid 1001. Compose bind-mounted secrets cannot
        # remap ownership. Only its two files are readable by that container;
        # the host directory stays 0700 and all mounts are read-only.
        mode = 0o444 if name in BROWSER_SECRETS else 0o600
        if path.exists():
            path.chmod(mode)
            continue
        descriptor, temporary = tempfile.mkstemp(prefix=".secret-", dir=directory)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(value.encode("utf-8"))
                output.flush()
                os.fsync(output.fileno())
                os.fchmod(output.fileno(), mode)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        provision(read_values(args.env_file.resolve()), args.output_dir)
    except (OSError, RuntimeError, ValueError) as error:
        # Never include credential values in errors or command output.
        raise SystemExit(
            f"Secret provisioning failed ({type(error).__name__}); "
            "check configuration and file permissions"
        ) from None
    print(
        f"Verified {len(EXPRESSIONS)} secret files; values were not printed or changed."
    )


if __name__ == "__main__":
    main()
