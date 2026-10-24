#!/usr/bin/env python3
"""One-time host bootstrap. Application deployments must not rerun installation."""

import argparse
import grp
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CONFIG = Path("/etc/datadog-agent")
STATE = Path("/var/lib/nestswipe-agent")


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def write_config(path, data):
    if not path.parent.exists():
        path.parent.mkdir(parents=True)
        os.chown(path.parent, 0, grp.getgrnam("dd-agent").gr_gid)
        path.parent.chmod(0o750)
    # umask is set before any configuration containing credentials is written.
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    os.chown(path, 0, grp.getgrnam("dd-agent").gr_gid)
    path.chmod(0o640)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-minor-version", help="Initial install only, e.g. 76.1")
    parser.add_argument("--configure-existing", action="store_true")
    parser.add_argument("--refresh-db-credentials", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run with sudo on the production VM.")
    os.umask(0o077)
    os.chdir(HERE.parent)
    marker = STATE / "bootstrapped"
    if marker.exists() and not args.refresh_db_credentials:
        print("Host Agent already configured; Fleet configuration preserved.")
        return

    # Compose parses .env syntax safely. Never source secrets as shell code,
    # include them in command arguments, or print the resolved environment.
    result = run(
        "docker",
        "compose",
        "-f",
        "docker-compose.prod.yml",
        "config",
        "--environment",
        capture_output=True,
        text=True,
    )
    values = dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )
    for key in ("DD_API_KEY", "DD_POSTGRES_PASSWORD", "POSTGRES_DB"):
        if not values.get(key):
            parser.error(
                f"Missing {key} in deploy/.env; provision DB monitoring first."
            )

    postgres_path = CONFIG / "conf.d/postgres.d/conf.yaml"
    if args.refresh_db_credentials:
        postgres = yaml.safe_load(postgres_path.read_text())
        for instance in postgres["instances"]:
            if instance.get("username") == "datadog":
                instance["password"] = values["DD_POSTGRES_PASSWORD"]
                instance["dbname"] = values["POSTGRES_DB"]
        write_config(postgres_path, postgres)
        run("systemctl", "restart", "datadog-agent")
        print("Database credentials refreshed; other integration settings preserved.")
        return

    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    if shutil.which("datadog-agent"):
        if not args.configure_existing:
            parser.error(
                "Existing host Agent found; inspect it before --configure-existing."
            )
    else:
        with tempfile.TemporaryDirectory(prefix="nestswipe-agent-") as temp:
            script = Path(temp) / "install.sh"
            run(
                "curl",
                "--fail",
                "--silent",
                "--show-error",
                "--location",
                "https://install.datadoghq.com/scripts/install_script_agent7.sh",
                "--output",
                str(script),
            )
            install_env = os.environ.copy()
            install_env.update(
                {
                    "DD_API_KEY": values["DD_API_KEY"],
                    "DD_SITE": values.get("DD_SITE", "datadoghq.com"),
                    "DD_HOSTNAME": "nestswipe-vnic",
                    "DD_REMOTE_UPDATES": "true",
                    "DD_INSTALL_ONLY": "true",
                }
            )
            if args.agent_minor_version:
                install_env["DD_AGENT_MINOR_VERSION"] = args.agent_minor_version
            logfile = STATE / "install.log"
            print(
                f"Installing host Agent; private installation log: {logfile}",
                flush=True,
            )
            with logfile.open("w") as log:
                run("bash", str(script), env=install_env, stdout=log, stderr=log)

    run("usermod", "-aG", "docker", "dd-agent")
    # Preserve installer-generated files privately before the initial bootstrap.
    for name in ("datadog.yaml", "system-probe.yaml"):
        existing = CONFIG / name
        backup = STATE / (name + ".initial")
        if existing.exists() and not backup.exists():
            shutil.copyfile(existing, backup)
            backup.chmod(0o600)
    agent = yaml.safe_load((HERE / "host-agent.yaml").read_text())
    agent["api_key"] = values["DD_API_KEY"]
    agent["site"] = values.get("DD_SITE", "datadoghq.com")
    write_config(CONFIG / "datadog.yaml", agent)
    write_config(
        CONFIG / "system-probe.yaml",
        yaml.safe_load((HERE / "host-system-probe.yaml").read_text()),
    )
    postgres = yaml.safe_load((HERE / "postgres.yaml").read_text())
    postgres["instances"][0]["password"] = values["DD_POSTGRES_PASSWORD"]
    postgres["instances"][0]["dbname"] = values["POSTGRES_DB"]
    write_config(postgres_path, postgres)

    # Keep the shared socket directory present across reboots and Agent upgrades.
    Path("/etc/tmpfiles.d/nestswipe-datadog.conf").write_text(
        "d /run/datadog 0755 dd-agent dd-agent -\n"
    )
    Path("/etc/tmpfiles.d/nestswipe-datadog.conf").chmod(0o644)
    run("systemd-tmpfiles", "--create", "/etc/tmpfiles.d/nestswipe-datadog.conf")
    # Docker bind mounts retain the directory inode. Removing /run/datadog on
    # an Agent restart would strand running applications on the old directory.
    for service in ("datadog-agent", "datadog-agent-exp"):
        dropin = Path(f"/etc/systemd/system/{service}.service.d")
        dropin.mkdir(parents=True, exist_ok=True)
        dropin.chmod(0o755)
        override = dropin / "nestswipe-sockets.conf"
        override.write_text("[Service]\nRuntimeDirectoryPreserve=yes\n")
        override.chmod(0o644)
    run("systemctl", "daemon-reload")
    # Services start at the coordinated cutover, after the Docker Agent stops.
    run("systemctl", "enable", "datadog-agent")
    marker.write_text(
        "Initial configuration installed; manage subsequent changes in Fleet.\n"
    )
    print(
        "Host Agent configured but not started. Stop the old Agent before starting it."
    )


if __name__ == "__main__":
    main()
