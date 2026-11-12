import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reboot_watch import credentials

spec = importlib.util.spec_from_file_location(
    "reboot_key", Path(__file__).with_name("provision-reboot-key.py")
)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)

KEY = "a" * 40
IDENTITY = {"data": {"relationships": {"org": {"data": {"id": "personal"}}}}}


class KeyTests(unittest.TestCase):
    def test_creates_only_monitor_read_scope(self):
        with patch.object(
            setup,
            "request",
            side_effect=[
                IDENTITY,
                {"data": []},
                {"data": {"attributes": {"scopes": ["monitors_read"], "key": KEY}}},
            ],
        ) as request:
            self.assertEqual(setup.provision({}, "personal"), KEY)
            payload = request.call_args.args[3]
            self.assertEqual(payload["data"]["attributes"]["scopes"], ["monitors_read"])

    def test_existing_key_is_reused_without_creating_another(self):
        with patch.object(
            setup,
            "request",
            side_effect=[
                IDENTITY,
                {"data": [{"id": "existing", "attributes": {"name": setup.KEY_NAME}}]},
                {"data": {"attributes": {"scopes": ["monitors_read"], "key": KEY}}},
            ],
        ) as request:
            self.assertEqual(setup.provision({}, "personal"), KEY)
            self.assertTrue(
                all(call.args[1] == "GET" for call in request.call_args_list)
            )

    def test_refuses_wrong_organization(self):
        with patch.object(setup, "request", return_value=IDENTITY) as request:
            with self.assertRaisesRegex(ValueError, "Wrong Datadog"):
                setup.provision({}, "another")
            request.assert_called_once()

    def test_refuses_existing_broad_scope(self):
        with (
            patch.object(
                setup,
                "request",
                side_effect=[
                    IDENTITY,
                    {
                        "data": [
                            {"id": "existing", "attributes": {"name": setup.KEY_NAME}}
                        ]
                    },
                    {
                        "data": {
                            "attributes": {"scopes": ["monitors_write"], "key": KEY}
                        }
                    },
                ],
            ),
            self.assertRaisesRegex(ValueError, "unexpected scopes"),
        ):
            setup.provision({}, "personal")

    def test_atomic_secret_update_preserves_other_values_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "deploy").mkdir()
            env = root / "deploy/.env"
            env.write_text("DD_API_KEY=api\nDD_APP_KEY=admin\nOTHER=value\n")
            setup.store_key(env, KEY)
            before = env.stat().st_mtime_ns
            setup.store_key(env, KEY)
            self.assertEqual(before, env.stat().st_mtime_ns)
            self.assertEqual(env.stat().st_mode & 0o777, 0o600)
            self.assertIn("DD_APP_KEY=admin\nOTHER=value\n", env.read_text())
            self.assertEqual(credentials(root)["DD_APP_KEY"], KEY)
            self.assertFalse(env.with_name(".env.reboot-key.tmp").exists())

    def test_rejects_key_with_newline_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("OTHER=preserved\n")
            with self.assertRaises(ValueError):
                setup.store_key(path, KEY + "\nINJECTED=value")
            self.assertEqual(path.read_text(), "OTHER=preserved\n")

    def test_accepts_prefixed_keys_and_quotes_special_characters(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "deploy").mkdir()
            path = root / "deploy/.env"
            path.write_text("DD_API_KEY=api\n")
            key = "ddapp_" + KEY + "#special"
            setup.store_key(path, key)
            self.assertEqual(credentials(root)["DD_APP_KEY"], key)

    def test_sync_sends_only_dedicated_key_over_stdin(self):
        with patch.object(setup.subprocess, "run") as run:
            setup.sync("ubuntu@example.org", KEY)
            self.assertEqual(json.loads(run.call_args.kwargs["input"]), KEY)
            self.assertNotIn(KEY, repr(run.call_args.args))


if __name__ == "__main__":
    unittest.main()
