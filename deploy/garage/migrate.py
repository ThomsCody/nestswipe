#!/usr/bin/env python3
"""Copy S3 objects without deleting source data; verify every byte and metadata.

Run only with all application writers stopped. Credentials are read from files.
The JSON report contains keys and hashes, never credentials. Existing destination
objects are recopied and verified, making interrupted runs safely repeatable.
"""

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from minio import Minio


HEADERS = {
    "content-type",
    "cache-control",
    "content-disposition",
    "content-encoding",
    "content-language",
    "expires",
}


def metadata(stat):
    return {
        k.lower(): v
        for k, v in stat.metadata.items()
        if k.lower() in HEADERS or k.lower().startswith("x-amz-meta-")
    }


def download(client, bucket, key, output):
    response = client.get_object(bucket, key)
    digest = hashlib.sha256()
    size = 0
    try:
        for chunk in response.stream(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
            if output is not None:
                output.write(chunk)
    finally:
        response.close()
        response.release_conn()
    return size, digest.hexdigest()


def migrate(source, target, report_path, verify_only=False):
    report = {"buckets": [], "objects": 0, "bytes": 0}
    for bucket in source.list_buckets():
        if source.get_bucket_versioning(bucket.name).status:
            raise RuntimeError("Versioned source requires a separate history migration")
        if not target.bucket_exists(bucket.name):
            raise RuntimeError("Provision destination bucket before migration")
        records = []
        source_keys = set()
        for obj in source.list_objects(bucket.name, recursive=True):
            key = obj.object_name
            source_keys.add(key)
            headers = metadata(source.stat_object(bucket.name, key))
            with tempfile.TemporaryFile() as content:
                size, digest = download(source, bucket.name, key, content)
                if not verify_only:
                    content.seek(0)
                    target.put_object(
                        bucket.name,
                        key,
                        content,
                        size,
                        content_type=headers.get(
                            "content-type", "application/octet-stream"
                        ),
                        metadata={
                            k: v for k, v in headers.items() if k != "content-type"
                        },
                    )
                actual_size, actual_digest = download(target, bucket.name, key, None)
                actual_headers = metadata(target.stat_object(bucket.name, key))
                if (actual_size, actual_digest, actual_headers) != (
                    size,
                    digest,
                    headers,
                ):
                    raise RuntimeError(f"Verification failed for {bucket.name}/{key}")
            records.append(
                {"key": key, "bytes": size, "sha256": digest, "metadata": headers}
            )
            report["objects"] += 1
            report["bytes"] += size
        target_keys = {
            o.object_name for o in target.list_objects(bucket.name, recursive=True)
        }
        if target_keys != source_keys:
            raise RuntimeError(
                "Source/destination key sets differ; no objects were deleted"
            )
        report["buckets"].append({"name": bucket.name, "objects": records})
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("objects", "bytes")}, sort_keys=True))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for side in ("source", "target"):
        p.add_argument(f"--{side}-endpoint", required=True)
        p.add_argument(f"--{side}-access-key-file", type=Path, required=True)
        p.add_argument(f"--{side}-secret-key-file", type=Path, required=True)
        p.add_argument(
            f"--{side}-region", default="us-east-1" if side == "source" else "garage"
        )
        p.add_argument(f"--{side}-tls", action="store_true")
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--verify-only", action="store_true")
    a = p.parse_args()
    clients = []
    for side in ("source", "target"):
        clients.append(
            Minio(
                getattr(a, side + "_endpoint"),
                access_key=getattr(a, side + "_access_key_file").read_text().strip(),
                secret_key=getattr(a, side + "_secret_key_file").read_text().strip(),
                secure=getattr(a, side + "_tls"),
                region=getattr(a, side + "_region"),
            )
        )
    migrate(*clients, a.report, a.verify_only)


if __name__ == "__main__":
    main()
