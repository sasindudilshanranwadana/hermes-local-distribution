import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKSUM_SCRIPT = ROOT / "scripts" / "write_checksums.py"


class ReleaseChecksumTests(unittest.TestCase):
    def test_manifest_is_complete_relative_and_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            distribution = Path(temporary_directory)
            executable = distribution / "Hermes-Local-Setup.exe"
            nested = (
                distribution
                / "Hermes Local Setup.app"
                / "Contents"
                / "MacOS"
                / "Hermes-Local-Setup"
            )
            nested.parent.mkdir(parents=True)
            executable.write_bytes(b"windows-binary")
            nested.write_bytes(b"macos-binary")
            (distribution / "SHA256SUMS.txt").write_text("stale\n", encoding="utf-8")
            (distribution / "SHA256SUMS.tmp").write_text("interrupted\n", encoding="utf-8")

            manifests: list[list[str]] = []
            for _ in range(2):
                result = subprocess.run(
                    [sys.executable, str(CHECKSUM_SCRIPT), str(distribution)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                manifests.append(
                    (distribution / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
                )

            expected = [
                (
                    f"{hashlib.sha256(nested.read_bytes()).hexdigest()}  "
                    "Hermes Local Setup.app/Contents/MacOS/Hermes-Local-Setup"
                ),
                (f"{hashlib.sha256(executable.read_bytes()).hexdigest()}  Hermes-Local-Setup.exe"),
            ]
            self.assertEqual(manifests, [expected, expected])
            self.assertNotIn(str(distribution), "\n".join(manifests[-1]))

    def test_release_workflow_uses_portable_checksum_generator(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release-installers.yml").read_text(
            encoding="utf-8"
        )

        self.assertEqual(workflow.count("python scripts/write_checksums.py dist"), 1)
        self.assertNotIn("Get-FileHash", workflow)
        self.assertNotIn("find dist", workflow)


if __name__ == "__main__":
    unittest.main()
