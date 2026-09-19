import sys
import unittest

from hermes_local_setup.commands import CommandRunner
from hermes_local_setup.redaction import SecretRedactor


class CommandRunnerTests(unittest.TestCase):
    def test_dry_run_does_not_execute(self) -> None:
        runner = CommandRunner(dry_run=True)
        result = runner.run([sys.executable, "-c", "raise SystemExit(17)"])
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.dry_run)

    def test_rejects_string_command(self) -> None:
        runner = CommandRunner()
        with self.assertRaisesRegex(TypeError, "argv"):
            runner.run("echo unsafe")  # type: ignore[arg-type]

    def test_redacts_output_and_registered_secret_in_argv(self) -> None:
        secret = "synthetic-command-secret"
        runner = CommandRunner(redactor=SecretRedactor([secret]))
        with self.assertRaisesRegex(ValueError, "secret"):
            runner.run([sys.executable, "-c", "print('ok')", secret])

    def test_captures_successful_output(self) -> None:
        runner = CommandRunner()
        result = runner.run([sys.executable, "-c", "print('ready')"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "ready")


if __name__ == "__main__":
    unittest.main()

