import json
import unittest

from hermes_local_setup.omniroute import OmniRouteClient, OmniRouteError
from hermes_local_setup.redaction import SecretRedactor


class OmniRouteClientTests(unittest.TestCase):
    def test_add_provider_posts_to_management_api_without_logging_key(self) -> None:
        calls: list[tuple[str, str, dict[str, str], bytes | None]] = []

        def transport(
            method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float
        ) -> tuple[int, bytes]:
            calls.append((method, url, headers, body))
            return 201, b'{"id":"provider-1"}'

        provider_key = "synthetic-upstream-provider-key"
        management_key = "synthetic-management-key"
        client = OmniRouteClient(
            base_url="http://127.0.0.1:20128",
            management_token=management_key,
            transport=transport,
            redactor=SecretRedactor([provider_key, management_key]),
        )
        identifier = client.add_provider(
            provider="openai",
            name="My OpenAI",
            url="https://api.openai.com/v1",
            api_key=provider_key,
        )
        self.assertEqual(identifier, "provider-1")
        method, url, headers, body = calls[0]
        self.assertEqual((method, url), ("POST", "http://127.0.0.1:20128/api/providers"))
        self.assertEqual(headers["Authorization"], f"Bearer {management_key}")
        self.assertEqual(json.loads(body or b"{}")["apiKey"], provider_key)
        self.assertNotIn(provider_key, repr(client))
        self.assertNotIn(management_key, repr(client))

    def test_error_is_redacted(self) -> None:
        def transport(
            method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float
        ) -> tuple[int, bytes]:
            return 400, b'{"error":"synthetic-upstream-provider-key is invalid"}'

        secret = "synthetic-upstream-provider-key"
        client = OmniRouteClient(
            base_url="http://127.0.0.1:20128",
            management_token="management",
            transport=transport,
            redactor=SecretRedactor([secret]),
        )
        with self.assertRaises(OmniRouteError) as raised:
            client.add_provider(
                provider="openai", name="OpenAI", url="https://api.openai.com/v1", api_key=secret
            )
        self.assertNotIn(secret, str(raised.exception))

    def test_ensure_provider_and_combo_update_existing_resources(self) -> None:
        methods: list[tuple[str, str]] = []

        def transport(
            method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float
        ) -> tuple[int, bytes]:
            methods.append((method, url))
            if method == "GET" and url.endswith("/api/providers"):
                return 200, b'{"connections":[{"id":"p1","provider":"openai","name":"OpenAI"}]}'
            if method == "GET" and url.endswith("/api/combos"):
                return 200, b'{"combos":[{"id":"c1","name":"pool-chat"}]}'
            return 200, b"{}"

        client = OmniRouteClient(
            base_url="http://127.0.0.1:20128",
            management_token="management",
            transport=transport,
        )
        identifier = client.ensure_provider(
            provider="openai", name="OpenAI", url="https://api.openai.com/v1", api_key="key"
        )
        client.ensure_combo({"name": "pool-chat", "models": []})
        self.assertEqual(identifier, "p1")
        self.assertIn(("PATCH", "http://127.0.0.1:20128/api/providers/p1"), methods)
        self.assertIn(("PUT", "http://127.0.0.1:20128/api/combos/c1"), methods)


if __name__ == "__main__":
    unittest.main()
