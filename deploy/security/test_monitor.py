"""Maintenance checks must fail visibly for stale, failed or inconclusive data."""

import importlib.util
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "monitor", Path(__file__).with_name("monitor.py")
)
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


def epoch(text):
    return datetime.fromisoformat(text).timestamp()


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = epoch("2026-10-25T13:00:00+01:00")

    def archive(self, name="nestswipe-20261024T020000Z"):
        path = self.root / name
        path.mkdir()
        (path / "backup.tar.gz.enc").write_bytes(b"fixture")
        (path / "manifest.txt").write_text(f"{name} {'a' * 64} 7")
        return path

    def test_backup_current_then_failed_attempt(self):
        self.archive()
        self.assertEqual(monitor.backup_check(self.now, self.root, self.root)[0], 0)
        (self.root / "last-result").write_text(f"failed {int(self.now)}")
        self.assertEqual(monitor.backup_check(self.now, self.root, self.root)[0], 2)
        (self.root / "last-result").write_text(f"ok {int(self.now)}")
        self.assertEqual(monitor.backup_check(self.now, self.root, self.root)[0], 0)

    def test_missing_stale_and_incomplete_backup(self):
        self.assertEqual(monitor.backup_check(self.now, self.root, self.root)[0], 2)
        self.archive("nestswipe-20261017T020000Z")
        self.assertEqual(monitor.backup_check(self.now, self.root, self.root)[0], 2)
        path = self.archive()
        (path / "manifest.txt").write_text(f"{path.name} {'a' * 64} 999")
        self.assertEqual(monitor.backup_check(self.now, self.root, self.root)[0], 2)

    def test_paris_deadline_grace_and_dst(self):
        before = epoch("2026-10-31T08:59:59+01:00")
        after = epoch("2026-10-31T09:00:00+01:00")
        self.assertEqual(
            monitor.weekly_due(before, 5, 3), epoch("2026-10-24T03:00:00+02:00")
        )
        self.assertEqual(
            monitor.weekly_due(after, 5, 3), epoch("2026-10-31T03:00:00+01:00")
        )

    def test_mac_requires_fresh_receipt_and_saturday_archive(self):
        receipt = self.root / "mac"
        now = epoch("2026-10-27T04:00:00+01:00")
        receipt.write_text(f"{int(self.now)} nestswipe-20261024T020000Z")
        self.assertEqual(monitor.download_check(now, receipt)[0], 2)
        receipt.write_text(f"{int(now)} nestswipe-20261024T020000Z")
        self.assertEqual(monitor.download_check(now, receipt)[0], 0)
        receipt.write_text(f"{int(now)} nestswipe-20261017T020000Z")
        self.assertEqual(monitor.download_check(now, receipt)[0], 2)

    def test_scan_rejects_empty_unsupported_inventory(self):
        with self.assertRaises(ValueError):
            monitor.summarize({"Results": []})
        with self.assertRaises(ValueError):
            monitor.summarize({"Metadata": {"OS": {"Family": "debian"}}, "Results": []})

    def test_fixable_findings_deduplicated_without_hiding_backlog(self):
        vuln = {
            "VulnerabilityID": "CVE-test",
            "PkgName": "example",
            "FixedVersion": "2",
            "Severity": "HIGH",
        }
        report = {
            "Metadata": {"OS": {"Family": "debian"}},
            "Results": [
                {
                    "Class": "os-pkgs",
                    "Packages": [{}],
                    "Vulnerabilities": [vuln, vuln, dict(vuln, FixedVersion="")],
                }
            ],
        }
        summary = monitor.summarize(report)
        self.assertEqual(len(summary["fixable"]), 1)
        data = {
            "status": "ok",
            "completed": self.now,
            "database_updated": self.now,
            "images": {"backend": "sha256:a"},
            "reports": {"backend": summary},
        }
        monitor.atomic_json(self.root / "scan.json", data)
        scan, vulnerabilities = monitor.scan_checks(self.now, self.root, data["images"])
        self.assertEqual(scan[0], 0)
        self.assertEqual(vulnerabilities[0], 2)
        self.assertEqual(
            monitor.scan_checks(
                self.now, self.root, data["images"], unit_result="oom-kill"
            )[0][0],
            2,
        )
        data["database_updated"] = self.now - 49 * 3600
        monitor.atomic_json(self.root / "scan.json", data)
        self.assertEqual(
            monitor.scan_checks(self.now, self.root, data["images"])[0][0], 2
        )
        data["database_updated"] = self.now
        monitor.atomic_json(self.root / "scan.json", data)
        self.assertEqual(
            monitor.scan_checks(self.now + 36 * 3600 + 1, self.root, data["images"])[0][
                0
            ],
            2,
        )
        self.assertEqual(
            monitor.scan_checks(self.now, self.root, {"backend": "sha256:b"})[0][0], 2
        )
        data["status"] = "failed"
        monitor.atomic_json(self.root / "scan.json", data)
        self.assertEqual(
            monitor.scan_checks(self.now, self.root, data["images"])[1][0], 3
        )


if __name__ == "__main__":
    unittest.main()
