import unittest
from pathlib import Path

from hermes_local_setup.config_io import load_answers
from hermes_local_setup.models import Capability, InstallMode


ROOT = Path(__file__).resolve().parents[2]


class ConfigIoTests(unittest.TestCase):
    def test_loads_nonsecret_answers_and_models(self) -> None:
        answers, models = load_answers(ROOT / "tests" / "fixtures" / "local_answers.json")
        self.assertEqual(answers.mode, InstallMode.LOCAL)
        self.assertEqual(models[0].model_id, "qwen-local")
        self.assertIn(Capability.CODING, models[0].capabilities)

    def test_rejects_unknown_fields(self) -> None:
        path = ROOT / "tests" / "fixtures" / "bad-answers.tmp.json"
        path.write_text('{"mode":"local","providers":[],"models":[],"secret":"bad"}')
        try:
            with self.assertRaisesRegex(ValueError, "unknown"):
                load_answers(path)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

