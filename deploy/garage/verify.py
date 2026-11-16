#!/usr/bin/env python3
"""Read-only object inventory; reports contain private keys and belong outside Git."""

import hashlib
import json
from pathlib import Path
import sys

from app.services.photo_storage import get_storage


def inventory(storage):
    records = []
    for entry in storage.scan("/"):
        if not entry.metadata.is_file:
            continue
        key = entry.path
        stat = storage.stat(key)
        digest = hashlib.sha256()
        size = 0
        with storage.open(key, "rb") as content:
            while chunk := content.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        if size != stat.content_length:
            raise RuntimeError("Object changed during inventory")
        records.append(
            {
                "key": key,
                "bytes": size,
                "sha256": digest.hexdigest(),
                "content_type": stat.content_type,
                "content_disposition": stat.content_disposition,
                "content_encoding": stat.content_encoding,
                "user_metadata": stat.user_metadata,
            }
        )
    return sorted(records, key=lambda item: item["key"])


if __name__ == "__main__":
    records = inventory(get_storage())
    Path(sys.argv[1]).write_text(json.dumps(records, indent=2) + "\n")
    print(
        json.dumps({"objects": len(records), "bytes": sum(x["bytes"] for x in records)})
    )
