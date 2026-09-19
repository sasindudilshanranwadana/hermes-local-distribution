import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CliTests(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(ROOT / "src")
        return subprocess.run(
            [sys.executable, "-m", "hermes_local_setup", *args],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_plan_command_is_vps_free_json(self) -> None:
        result = self._run(
            "plan",
            "--answers",
            "tests/fixtures/local_answers.json",
            "--json",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["dry_run"])
        self.assertNotIn("100.81.25.128", result.stdout)

    def test_install_requires_explicit_apply_or_dry_run(self) -> None:
        result = self._run("install", "--answers", "tests/fixtures/local_answers.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--apply", result.stderr)

    def test_support_bundle_command_creates_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "support.zip"
            result = self._run("support-bundle", "--output", str(output))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
