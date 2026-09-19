import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {".py", ".toml", ".json", ".yaml", ".yml", ".md", ".sh", ".ps1"}


class RepositoryHygieneTests(unittest.TestCase):
    def test_tracked_source_has_no_personal_vps_markers(self) -> None:
        violations: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or path.suffix not in TEXT_SUFFIXES:
                continue
            if "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in ("100.81.25.128", "sasivps", "sdranwadana@gmail.com"):
                if marker in text:
                    violations.append(f"{path.relative_to(ROOT)}:{marker}")
        self.assertEqual(violations, [])

    def test_no_inline_secret_assignments_in_tracked_config(self) -> None:
        pattern = re.compile(
            r"(?im)^\s*[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)\s*=\s*(?!\$\{|example|change-me)[^\s#]+"
        )
        violations: list[str] = []
        for path in (ROOT / "services", ROOT / "policies", ROOT / "manifests"):
            for candidate in path.rglob("*"):
                if candidate.is_file() and candidate.suffix in {".env", ".json", ".toml", ".yaml", ".yml"}:
                    text = candidate.read_text(encoding="utf-8", errors="ignore")
                    if pattern.search(text):
                        violations.append(str(candidate.relative_to(ROOT)))
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
