"""Validate or upsert Nestswipe monitors in an explicitly selected Datadog org."""

import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--org-uuid", required=True, help="Expected Datadog organization UUID"
    )
    parser.add_argument(
        "--notify",
        required=True,
        help="Datadog notification handle, e.g. @owner@example.com",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create/update after validation; default only validates",
    )
    args = parser.parse_args()
    if not args.notify.startswith("@") or any(char.isspace() for char in args.notify):
        parser.error("--notify must be one Datadog notification handle")
    site = os.environ.get("DD_SITE", "datadoghq.com")
    if site not in {
        "datadoghq.com",
        "datadoghq.eu",
        "us3.datadoghq.com",
        "us5.datadoghq.com",
        "ap1.datadoghq.com",
        "ap2.datadoghq.com",
        "ddog-gov.com",
    }:
        parser.error("Unsupported DD_SITE")
    headers = {
        "DD-API-KEY": os.environ["DD_API_KEY"],
        "DD-APPLICATION-KEY": os.environ["DD_APP_KEY"],
        "Content-Type": "application/json",
    }

    def request(method, path, data=None):
        req = Request(
            "https://api." + site + path,
            method=method,
            headers=headers,
            data=json.dumps(data).encode() if data is not None else None,
        )
        try:
            with urlopen(req, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            # The API's validation errors are useful; request headers stay private.
            raise SystemExit(
                f"Datadog {method} {path}: HTTP {exc.code}: {exc.read().decode()}"
            ) from None

    identity = request("GET", "/api/v2/current_user")
    if identity["data"]["relationships"]["org"]["data"]["id"] != args.org_uuid:
        raise SystemExit("Credentials belong to a different Datadog organization.")
    payloads = [
        json.loads(path.read_text())
        for path in sorted(Path(__file__).parent.glob("*-monitor.json"))
    ]
    for payload in payloads:
        payload["message"] += "\n\n" + args.notify
        request("POST", "/api/v1/monitor/validate", payload)
    if not args.apply:
        print("All monitor configurations validated; no monitor was changed.")
        return
    for payload in payloads:
        upsert_monitor(request, payload, args.notify)


def upsert_monitor(request, payload, notify):
    matches = [
        monitor
        for monitor in request(
            "GET", "/api/v1/monitor?" + urlencode({"name": payload["name"]})
        )
        if monitor["name"] == payload["name"]
    ]
    if len(matches) > 1:
        raise SystemExit(
            "Multiple monitors have this exact name; resolve duplicates before applying."
        )
    if matches and "managed_by:nestswipe" not in matches[0].get("tags", []):
        raise SystemExit(
            "An unmanaged monitor has this name; refusing to overwrite it."
        )
    if matches:
        result = request("PUT", f"/api/v1/monitor/{matches[0]['id']}", payload)
    else:
        result = request("POST", "/api/v1/monitor", payload)
    saved = request("GET", f"/api/v1/monitor/{result['id']}")
    if (
        saved["query"] != payload["query"]
        or saved["type"] != payload["type"]
        or notify not in saved["message"]
        or any(
            saved["options"].get(key) != value
            for key, value in payload["options"].items()
        )
    ):
        raise SystemExit("Saved monitor does not match the requested configuration.")
    print(
        json.dumps(
            {
                "id": saved["id"],
                "name": saved["name"],
                "state": saved.get("overall_state"),
            }
        )
    )


if __name__ == "__main__":
    main()
