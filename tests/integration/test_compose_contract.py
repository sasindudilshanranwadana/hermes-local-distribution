import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ComposeContractTests(unittest.TestCase):
    def test_compose_is_loopback_only_and_portable(self) -> None:
        compose = (ROOT / "services" / "compose.yaml").read_text(encoding="utf-8")
        for marker in ("100.81.25.128", "/root", "sasivps", "external: true"):
            self.assertNotIn(marker, compose)
        published = re.findall(r'- "([^\"]+:\d+:\d+)"', compose)
        self.assertTrue(published)
        self.assertTrue(all(binding.startswith("127.0.0.1:") for binding in published))

    def test_compose_parses_with_example_environment(self) -> None:
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                "services/runtime.env.example",
                "-f",
                "services/compose.yaml",
                "config",
                "--quiet",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
