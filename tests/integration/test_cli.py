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

    def test_repair_dry_run_and_uninstall_plan(self) -> None:
        repair = self._run(
            "repair",
            "--answers",
            "tests/fixtures/local_answers.json",
            "--dry-run",
        )
        self.assertEqual(repair.returncode, 0, repair.stderr)
        self.assertIn("mode=dry-run", repair.stdout)
        uninstall = self._run("uninstall-plan")
        self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
        self.assertIn("Preserve memories", uninstall.stdout)

    def test_doctor_returns_structured_status(self) -> None:
        result = self._run("doctor")
        self.assertIn(result.returncode, {0, 1})
        payload = json.loads(result.stdout)
        self.assertIn("overall", payload)
        self.assertGreaterEqual(len(payload["checks"]), 2)


if __name__ == "__main__":
    unittest.main()
