import unittest

from hermes_local_setup.redaction import SecretRedactor


class RedactionTests(unittest.TestCase):
    def test_redacts_registered_and_pattern_secrets(self) -> None:
        redactor = SecretRedactor(["private-value-123456"])
        text = (
            "token=private-value-123456 Authorization: Bearer abcdefghijklmnop "
            "OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz"
        )
        redacted = redactor.redact(text)
        self.assertNotIn("private-value-123456", redacted)
        self.assertNotIn("abcdefghijklmnop", redacted)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz", redacted)
        self.assertGreaterEqual(redacted.count("[REDACTED]"), 3)

    def test_does_not_redact_normal_status_text(self) -> None:
        redactor = SecretRedactor()
        self.assertEqual(redactor.redact("service healthy"), "service healthy")


if __name__ == "__main__":
    unittest.main()

