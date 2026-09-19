import tempfile
import unittest
from pathlib import Path

from hermes_local_setup.diagnostics import create_support_bundle
from hermes_local_setup.health import HealthCheck, HealthLevel, HealthReport
from hermes_local_setup.redaction import SecretRedactor


class HealthAndDiagnosticsTests(unittest.TestCase):
    def test_health_report_uses_worst_level(self) -> None:
        report = HealthReport(
            checks=(
                HealthCheck("hermes", HealthLevel.HEALTHY, "ready"),
                HealthCheck("memory", HealthLevel.DEGRADED, "disabled"),
            )
        )
        self.assertEqual(report.overall, HealthLevel.DEGRADED)

    def test_support_bundle_is_allowlisted_and_redacted(self) -> None:
        secret = "synthetic-support-secret"
        report = HealthReport(
            checks=(HealthCheck("provider", HealthLevel.HEALTHY, f"ready {secret}"),)
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "support.zip"
            create_support_bundle(
                output,
                report=report,
                versions={"kit": "0.1.0a1"},
                redactor=SecretRedactor([secret]),
            )
            raw = output.read_bytes()
            self.assertNotIn(secret.encode(), raw)
            self.assertNotIn(b"conversation", raw.lower())
            self.assertNotIn(b"memory", raw.lower())


if __name__ == "__main__":
    unittest.main()
