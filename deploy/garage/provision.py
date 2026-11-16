#!/usr/bin/env python3
"""Create persistent Garage secrets without rotating existing credentials."""

import argparse
import os
from pathlib import Path
import secrets


def provision(directory):
    if directory.is_symlink():
        raise RuntimeError("Refusing symlinked secrets directory")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, value in {
        "garage_rpc_secret": secrets.token_hex(32),
        "garage_access_key": "GK" + secrets.token_hex(16),
        "garage_secret_key": secrets.token_hex(32),
    }.items():
        path = directory / name
        if path.is_symlink():
            raise RuntimeError("Refusing symlinked secret")
        mode = 0o400 if name == "garage_rpc_secret" else 0o444
        try:
            fd = os.open(
                path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                mode,
            )
        except FileExistsError:
            if not path.read_text().strip():
                raise RuntimeError("Empty Garage secret")
            path.chmod(mode)
            continue
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w") as f:
            f.write(value)
    # Docker bind-mounted secrets must be readable by the non-root backend.
    # Parent directory restricts host access; container mounts are read-only.
    directory.chmod(0o700)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", type=Path, required=True)
    provision(p.parse_args().directory)
    print("Garage secrets ready (values withheld)")
