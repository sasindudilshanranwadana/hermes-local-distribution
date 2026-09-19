import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from hermes_local_setup.components import (
    install_mem0_server_archive,
    install_superpowers_archive,
)


def _archive(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, contents in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(contents)
            archive.addfile(info, io.BytesIO(contents))
    return output.getvalue()


class ComponentInstallerTests(unittest.TestCase):
    def test_installs_only_pinned_mem0_server_source(self) -> None:
        data = _archive(
            {
                "mem0-commit/server/Dockerfile": b"FROM python:3.12-slim\n",
                "mem0-commit/server/main.py": b"# server\n",
                "mem0-commit/README.md": b"not runtime\n",
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "mem0-server"
            install_mem0_server_archive(
                data,
                expected_sha256=hashlib.sha256(data).hexdigest(),
                destination=destination,
            )
            self.assertTrue((destination / "Dockerfile").is_file())
            self.assertTrue((destination / "main.py").is_file())
            self.assertFalse((destination / "README.md").exists())

    def test_mem0_source_rejects_checksum_mismatch_and_path_traversal(self) -> None:
        safe = _archive({"mem0-commit/server/Dockerfile": b"FROM scratch\n"})
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "checksum"):
                install_mem0_server_archive(
                    safe,
                    expected_sha256="0" * 64,
                    destination=Path(tmp) / "server",
                )
            unsafe = _archive({"mem0-commit/server/../../outside": b"bad"})
            with self.assertRaisesRegex(ValueError, "unsafe"):
                install_mem0_server_archive(
                    unsafe,
                    expected_sha256=hashlib.sha256(unsafe).hexdigest(),
                    destination=Path(tmp) / "server",
                )

    def test_installs_only_hermes_plugin_runtime_files(self) -> None:
        data = _archive(
            {
                "superpowers-commit/.hermes-plugin/plugin.yaml": b"name: superpowers\n",
                "superpowers-commit/.hermes-plugin/__init__.py": b"# plugin\n",
                "superpowers-commit/skills/tdd/SKILL.md": b"# TDD\n",
                "superpowers-commit/LICENSE": b"MIT\n",
                "superpowers-commit/docs/not-runtime.md": b"ignore\n",
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "superpowers"
            install_superpowers_archive(
                data,
                expected_sha256=hashlib.sha256(data).hexdigest(),
                destination=destination,
            )
            self.assertTrue((destination / "plugin.yaml").is_file())
            self.assertTrue((destination / "skills" / "tdd" / "SKILL.md").is_file())
            self.assertTrue((destination / "LICENSE").is_file())
            self.assertFalse((destination / "docs").exists())

    def test_rejects_checksum_mismatch_and_path_traversal(self) -> None:
        safe = _archive({"superpowers-commit/LICENSE": b"MIT\n"})
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "checksum"):
                install_superpowers_archive(
                    safe, expected_sha256="0" * 64, destination=Path(tmp) / "plugin"
                )
            unsafe = _archive({"superpowers-commit/skills/../../outside": b"bad"})
            with self.assertRaisesRegex(ValueError, "unsafe"):
                install_superpowers_archive(
                    unsafe,
                    expected_sha256=hashlib.sha256(unsafe).hexdigest(),
                    destination=Path(tmp) / "plugin",
                )


if __name__ == "__main__":
    unittest.main()
