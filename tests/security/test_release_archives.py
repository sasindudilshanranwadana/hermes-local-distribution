import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from scripts.archive_release_assets import archive_release_assets

ROOT = Path(__file__).resolve().parents[2]


class ReleaseArchiveTests(unittest.TestCase):
    def test_archives_restore_platform_executable_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            release_assets = Path(temporary_directory)
            linux_binary = release_assets / "hermes-local-setup-linux" / "Hermes-Local-Setup"
            mac_binary = release_assets / "hermes-local-setup-macos" / "Hermes-Local-Setup"
            mac_app_binary = (
                release_assets
                / "hermes-local-setup-macos"
                / "Hermes Local Setup.app"
                / "Contents"
                / "MacOS"
                / "Hermes-Local-Setup"
            )
            windows_binary = (
                release_assets / "hermes-local-setup-windows" / "Hermes-Local-Setup.exe"
            )
            for binary in (linux_binary, mac_binary, mac_app_binary, windows_binary):
                binary.parent.mkdir(parents=True, exist_ok=True)
                binary.write_bytes(binary.name.encode())
                binary.chmod(0o644)

            with mock.patch("scripts.archive_release_assets.Path.chmod", return_value=None):
                archives = archive_release_assets(release_assets)
            self.assertEqual(len(archives), 3)

            expected_modes = {
                "hermes-local-setup-linux.zip": {"Hermes-Local-Setup": 0o755},
                "hermes-local-setup-macos.zip": {
                    "Hermes-Local-Setup": 0o755,
                    "Hermes Local Setup.app/Contents/MacOS/Hermes-Local-Setup": 0o755,
                },
                "hermes-local-setup-windows.zip": {"Hermes-Local-Setup.exe": 0o644},
            }
            for archive_name, members in expected_modes.items():
                with (
                    self.subTest(archive=archive_name),
                    zipfile.ZipFile(release_assets / archive_name) as archive,
                ):
                    for member, expected_mode in members.items():
                        actual_mode = stat.S_IMODE(archive.getinfo(member).external_attr >> 16)
                        self.assertEqual(actual_mode, expected_mode)

    def test_release_workflow_uses_permission_preserving_archiver(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release-installers.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("python scripts/archive_release_assets.py release-assets", workflow)
        self.assertNotIn("zip -r", workflow)


if __name__ == "__main__":
    unittest.main()
