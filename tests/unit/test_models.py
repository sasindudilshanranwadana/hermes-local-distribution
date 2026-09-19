import unittest

from hermes_local_setup.models import (
    Capability,
    InstallAnswers,
    InstallMode,
    ModelCandidate,
    ProviderConfig,
    ProviderKind,
)


class ModelContractTests(unittest.TestCase):
    def test_cloud_provider_requires_https_endpoint(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            ProviderConfig(
                provider_id="openrouter",
                kind=ProviderKind.OPENAI_COMPATIBLE,
                base_url="http://openrouter.example/v1",
                credential_env="OPENROUTER_API_KEY",
                privacy="cloud",
            )

    def test_local_provider_allows_loopback_http(self) -> None:
        provider = ProviderConfig(
            provider_id="ollama",
            kind=ProviderKind.OLLAMA,
            base_url="http://127.0.0.1:11434/v1",
            credential_env=None,
            privacy="local",
        )
        self.assertEqual(provider.provider_id, "ollama")

    def test_local_mode_rejects_cloud_provider(self) -> None:
        provider = ProviderConfig(
            provider_id="openrouter",
            kind=ProviderKind.OPENAI_COMPATIBLE,
            base_url="https://openrouter.ai/api/v1",
            credential_env="OPENROUTER_API_KEY",
            privacy="cloud",
        )
        with self.assertRaisesRegex(ValueError, "local-only"):
            InstallAnswers(mode=InstallMode.LOCAL, providers=(provider,))

    def test_model_candidate_is_immutable(self) -> None:
        candidate = ModelCandidate(
            provider_id="ollama",
            model_id="qwen-test",
            capabilities=frozenset({Capability.CODING}),
            context_window=65536,
            supports_tools=True,
        )
        with self.assertRaises((AttributeError, TypeError)):
            candidate.model_id = "changed"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()

