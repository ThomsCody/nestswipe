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


if __name__ == "__main__":
    unittest.main()
