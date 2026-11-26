"""Safety checks for the one-time credential migration and later deployments."""

import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch


spec = importlib.util.spec_from_file_location(
    "provision_secrets", Path(__file__).with_name("provision-secrets.py")
)
provision_secrets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provision_secrets)


class ProvisionTests(unittest.TestCase):
    def test_compose_serialization_is_decoded_without_losing_literal_dollars(self):
        result = Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "services": {
                        "credentials": {
                            "environment": {"jwt_secret": "literal-$$value-$$$$-end"}
                        }
                    }
                }
            ),
        )
        with patch.object(provision_secrets.subprocess, "run", return_value=result):
            self.assertEqual(
                provision_secrets.read_values(Path(".env")),
                {"jwt_secret": "literal-$value-$$-end"},
            )

    def test_permissions_exact_values_and_idempotent_mounts(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "secrets"
            values = {
                "jwt_secret": " test-$value\n",
                "proxy_password": "example",
                "proxy_user": "",
            }
            provision_secrets.provision(values, directory)
            inode = (directory / "jwt_secret").stat().st_ino
            provision_secrets.provision(values, directory)
            self.assertEqual((directory / "jwt_secret").read_bytes(), b" test-$value\n")
            self.assertEqual((directory / "jwt_secret").stat().st_ino, inode)
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            self.assertEqual(
                stat.S_IMODE((directory / "jwt_secret").stat().st_mode), 0o600
            )
            self.assertEqual(
                stat.S_IMODE((directory / "proxy_password").stat().st_mode), 0o444
            )
            self.assertEqual((directory / "proxy_user").read_bytes(), b"")

    def test_different_existing_value_aborts_before_creating_any_files(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            (directory / "jwt_secret").write_text("current")
            with self.assertRaisesRegex(RuntimeError, "differs"):
                provision_secrets.provision(
                    {"database_url": "new", "jwt_secret": "stale"}, directory
                )
            self.assertFalse((directory / "database_url").exists())
            self.assertEqual((directory / "jwt_secret").read_text(), "current")

    def test_file_only_web_data_key_is_preserved_and_default_is_disabled(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            secret = directory / "decodo_web_data_api_key"
            provision_secrets.provision({"jwt_secret": "example"}, directory)
            self.assertEqual(secret.read_bytes(), b"")
            value = b"web-data-key-with-$-characters\r\n"
            secret.write_bytes(value)
            inode = secret.stat().st_ino
            provision_secrets.provision({"jwt_secret": "example"}, directory)
            self.assertEqual(secret.read_bytes(), value)
            self.assertEqual(secret.stat().st_ino, inode)
            self.assertEqual(stat.S_IMODE(secret.stat().st_mode), 0o600)

    def test_file_only_key_cannot_be_a_symlink(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            (directory / "decodo_web_data_api_key").symlink_to(directory / "outside")
            with self.assertRaisesRegex(RuntimeError, "symlinked"):
                provision_secrets.provision({}, directory)
            self.assertFalse((directory / "outside").exists())

    def test_symlinked_directory_and_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            directory = root / "secrets"
            directory.mkdir()
            link = root / "link"
            link.symlink_to(directory, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "symlinked"):
                provision_secrets.provision({"jwt_secret": "example"}, link)
            (directory / "jwt_secret").symlink_to(root / "outside")
            with self.assertRaisesRegex(RuntimeError, "symlinked"):
                provision_secrets.provision({"jwt_secret": "example"}, directory)
            self.assertFalse((root / "outside").exists())


if __name__ == "__main__":
    unittest.main()
