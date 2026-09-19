import os
import stat
import tempfile
import unittest
from pathlib import Path

from hermes_local_setup.secrets import SecretStore


class SecretStoreTests(unittest.TestCase):
    def test_rejects_invalid_names_and_multiline_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SecretStore(Path(tmp) / "secrets.env")
            with self.assertRaises(ValueError):
                store.set("bad-name", "value")
            with self.assertRaises(ValueError):
                store.set("GOOD_NAME", "first\nsecond")

    def test_writes_owner_only_and_returns_names_not_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            secret_file = Path(tmp) / "secrets.env"
            store = SecretStore(secret_file)
            store.set_many({"OPENROUTER_API_KEY": "synthetic-secret-value"})
            self.assertEqual(store.names(), ("OPENROUTER_API_KEY",))
            self.assertNotIn("synthetic-secret-value", repr(store))
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(secret_file.stat().st_mode), 0o600)

    def test_rejects_symlink_target(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real.env"
            real.write_text("SAFE=value\n", encoding="utf-8")
            link = Path(tmp) / "link.env"
            link.symlink_to(real)
            with self.assertRaisesRegex(ValueError, "symlink"):
                SecretStore(link).set("NEW_SECRET", "value")


if __name__ == "__main__":
    unittest.main()
