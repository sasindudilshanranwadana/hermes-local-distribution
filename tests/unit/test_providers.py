import json
import unittest

from hermes_local_setup.models import ProviderConfig, ProviderKind
from hermes_local_setup.providers import ProviderClient, ProviderError
from hermes_local_setup.redaction import SecretRedactor


class ProviderClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = ProviderConfig(
            provider_id="example",
            kind=ProviderKind.OPENAI_COMPATIBLE,
            base_url="https://models.example/v1",
            credential_env="EXAMPLE_API_KEY",
            privacy="cloud",
        )

    def test_discovers_models_without_exposing_key(self) -> None:
        seen_headers: dict[str, str] = {}

        def transport(url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
            self.assertEqual(url, "https://models.example/v1/models")
            seen_headers.update(headers)
            return 200, json.dumps({"data": [{"id": "model-a"}, {"id": "model-b"}]}).encode()

        secret = "synthetic-provider-secret"
        client = ProviderClient(transport=transport, redactor=SecretRedactor([secret]))
        models = client.discover(self.provider, secret)
        self.assertEqual(models, ("model-a", "model-b"))
        self.assertEqual(seen_headers["Authorization"], f"Bearer {secret}")
        self.assertNotIn(secret, repr(client))

    def test_authentication_failure_is_plain_language_and_redacted(self) -> None:
        def transport(url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
            return 401, b'{"error":"bad synthetic-provider-secret"}'

        secret = "synthetic-provider-secret"
        client = ProviderClient(transport=transport, redactor=SecretRedactor([secret]))
        with self.assertRaisesRegex(ProviderError, "authentication") as raised:
            client.discover(self.provider, secret)
        self.assertNotIn(secret, str(raised.exception))

    def test_rejects_malformed_catalog(self) -> None:
        def transport(url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
            return 200, b'{"not_data": []}'

        with self.assertRaisesRegex(ProviderError, "catalog"):
            ProviderClient(transport=transport).discover(self.provider, "key")

    def test_uses_provider_specific_auth_headers(self) -> None:
        cases = (
            ("anthropic", "x-api-key", "anthropic-version"),
            ("gemini", "x-goog-api-key", None),
        )
        for provider_id, expected_key_header, expected_version_header in cases:
            with self.subTest(provider_id=provider_id):
                seen_headers: dict[str, str] = {}

                def transport(
                    url: str,
                    headers: dict[str, str],
                    timeout: float,
                    target: dict[str, str] = seen_headers,
                ) -> tuple[int, bytes]:
                    target.update(headers)
                    return 200, b'{"data":[{"id":"model-a"}]}'

                provider = ProviderConfig(
                    provider_id=provider_id,
                    kind=ProviderKind.OPENAI_COMPATIBLE,
                    base_url="https://models.example/v1",
                    credential_env="PROVIDER_API_KEY",
                    privacy="cloud",
                )
                ProviderClient(transport=transport).discover(provider, "synthetic-key")
                self.assertEqual(seen_headers[expected_key_header], "synthetic-key")
                self.assertNotIn("Authorization", seen_headers)
                if expected_version_header:
                    self.assertIn(expected_version_header, seen_headers)

    def test_validates_the_selected_model_against_discovery(self) -> None:
        def transport(url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
            return 200, b'{"data":[{"id":"available-model"}]}'

        client = ProviderClient(transport=transport)
        client.validate_model(self.provider, "key", "available-model")
        with self.assertRaisesRegex(ProviderError, "not available"):
            client.validate_model(self.provider, "key", "missing-model")


if __name__ == "__main__":
    unittest.main()
