import json
import tempfile
import unittest
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import reboot_watch as watch


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.policy = {
            "timezone": "Europe/Paris",
            "start_hour": 2,
            "end_hour": 5,
            "idle_minutes": 15,
            "cooldown_hours": 24,
        }
        for name, value in [
            ("STATE", root),
            ("FLAG", root / "flag"),
            ("BOOT_ID", root / "boot"),
        ]:
            patcher = patch.object(watch, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        watch.FLAG.touch()
        watch.BOOT_ID.write_text("before")
        self.mocks = {}
        for name, value in [
            ("monitor_state", "Alert"),
            ("in_window", True),
            ("healthy", None),
            ("no_sessions", None),
            ("idle", True),
            ("release", None),
            ("maintenance_locks", nullcontext()),
            ("command", ""),
        ]:
            patcher = patch.object(watch, name, return_value=value)
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(watch.time, "sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_eligible_reboot_reserves_before_request_and_persists_attempt(self):
        watch.run(self.policy, apply=True)
        self.assertEqual(
            self.mocks["idle"].call_args_list[-1].kwargs, {"reserve": True}
        )
        self.mocks["command"].assert_called_once_with("systemctl", "reboot")
        self.assertFalse(
            json.loads((watch.STATE / "attempt.json").read_text())["verified"]
        )
        self.mocks["release"].assert_not_called()

    def test_dry_run_never_reserves_or_reboots(self):
        watch.run(self.policy)
        self.mocks["idle"].assert_called_once_with(self.policy)
        self.mocks["command"].assert_not_called()
        self.assertFalse((watch.STATE / "attempt.json").exists())

    def test_reboot_flag_required(self):
        watch.FLAG.unlink()
        watch.run(self.policy, apply=True)
        self.mocks["monitor_state"].assert_not_called()
        self.mocks["command"].assert_not_called()

    def test_monitor_states_other_than_alert_never_authorize_reboot(self):
        for state in ["OK", "No Data", "Unknown", "Warn"]:
            with self.subTest(state=state):
                self.mocks["monitor_state"].return_value = state
                watch.run(self.policy, apply=True)
                self.mocks["command"].assert_not_called()

    def test_daytime_defers(self):
        self.mocks["in_window"].return_value = False
        watch.run(self.policy, apply=True)
        self.mocks["idle"].assert_not_called()
        self.mocks["command"].assert_not_called()

    def test_activity_and_activity_race_both_defer(self):
        for results in [[False], [True, False]]:
            self.mocks["idle"].side_effect = results
            watch.run(self.policy, apply=True)
            self.mocks["command"].assert_not_called()

    def test_connection_appearing_after_reservation_releases_it(self):
        self.mocks["no_sessions"].side_effect = [None, ValueError("SSH connected")]
        with self.assertRaises(ValueError):
            watch.run(self.policy, apply=True)
        self.mocks["release"].assert_called_once()
        self.mocks["command"].assert_not_called()

    def test_monitor_failure_after_reservation_releases_it(self):
        self.mocks["monitor_state"].side_effect = ["Alert", OSError("API unavailable")]
        with self.assertRaises(OSError):
            watch.run(self.policy, apply=True)
        self.mocks["release"].assert_called_once()
        self.mocks["command"].assert_not_called()

    def test_busy_maintenance_lock_defers(self):
        self.mocks["maintenance_locks"].side_effect = BlockingIOError("backup active")
        with self.assertRaises(BlockingIOError):
            watch.run(self.policy, apply=True)
        self.mocks["idle"].assert_not_called()
        self.mocks["command"].assert_not_called()

    def test_reboot_failure_does_not_loop(self):
        self.mocks["command"].side_effect = OSError("reboot failed")
        with self.assertRaises(OSError):
            watch.run(self.policy, apply=True)
        self.mocks["release"].assert_called_once()
        with self.assertRaisesRegex(ValueError, "not completed"):
            watch.run(self.policy, apply=True)
        self.mocks["command"].assert_called_once()

    def test_postboot_verification_requires_monitor_ok(self):
        watch.write_state({"boot_id": "previous", "timestamp": 0, "verified": False})
        watch.FLAG.unlink()
        for state in ["Alert", "No Data", "Unknown"]:
            self.mocks["monitor_state"].return_value = state
            with self.assertRaisesRegex(ValueError, "waiting for Datadog"):
                watch.run(self.policy, apply=True)
            self.assertFalse(
                json.loads((watch.STATE / "attempt.json").read_text())["verified"]
            )
        self.mocks["monitor_state"].return_value = "OK"
        watch.run(self.policy, apply=True)
        self.assertTrue(
            json.loads((watch.STATE / "attempt.json").read_text())["verified"]
        )
        self.assertNotIn(
            unittest.mock.call("systemctl", "reboot"),
            self.mocks["command"].call_args_list,
        )


class WindowTests(unittest.TestCase):
    def test_paris_window_in_winter_summer_and_both_dst_transitions(self):
        policy = {"timezone": "Europe/Paris", "start_hour": 2, "end_hour": 5}
        for iso, allowed in [
            ("2026-11-12T00:59:59+00:00", False),
            ("2026-11-12T01:00:00+00:00", True),
            ("2026-11-12T04:00:00+00:00", False),
            ("2026-07-12T00:00:00+00:00", True),
            ("2026-07-12T03:00:00+00:00", False),
            ("2026-03-29T01:00:00+00:00", True),
            ("2026-10-25T00:30:00+00:00", True),
            ("2026-10-25T01:30:00+00:00", True),
        ]:
            with self.subTest(iso=iso):
                self.assertEqual(
                    watch.in_window(policy, datetime.fromisoformat(iso).timestamp()),
                    allowed,
                )


if __name__ == "__main__":
    unittest.main()
