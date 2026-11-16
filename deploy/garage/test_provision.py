import os
from pathlib import Path
import stat
import tempfile
import unittest

from provision import provision


class ProvisionTests(unittest.TestCase):
    def test_private_umask_and_idempotence(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "secrets"
            old = os.umask(0o077)
            try:
                provision(directory)
                values = {p.name: p.read_bytes() for p in directory.iterdir()}
                provision(directory)
            finally:
                os.umask(old)
            self.assertEqual(
                values, {p.name: p.read_bytes() for p in directory.iterdir()}
            )
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            for name in values:
                mode = 0o400 if name == "garage_rpc_secret" else 0o444
                self.assertEqual(stat.S_IMODE((directory / name).stat().st_mode), mode)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            link = Path(root) / "link"
            link.symlink_to(root)
            with self.assertRaises(RuntimeError):
                provision(link)
