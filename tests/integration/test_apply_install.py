import tempfile
import unittest
from pathlib import Path

from hermes_local_setup.capabilities import bind_capabilities
from hermes_local_setup.commands import CommandResult
from hermes_local_setup.installer import Installer
from hermes_local_setup.models import (
    Capability,
    InstallAnswers,
    InstallMode,
    ModelCandidate,
    ProviderConfig,
    ProviderKind,
)
from hermes_local_setup.paths import resolve_layout
from hermes_local_setup.state import StateStore


ROOT = Path(__file__).resolve().parents[2]


class FakeRunner:
    def __init__(self, hermes_env_path: Path) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.hermes_env_path = hermes_env_path

    def run(self, argv, **kwargs):
        command = tuple(str(item) for item in argv)
        self.commands.append(command)
        stdout = f"{self.hermes_env_path}\n" if command[-2:] == ("config", "env-path") else "ok\n"
        return CommandResult(command, 0, stdout, "")


class FakeOmniRoute:
    def __init__(self) -> None:
        self.providers: list[dict[str, str]] = []
        self.combos: list[dict[str, object]] = []

    def add_provider(self, **kwargs):
        self.providers.append(kwargs)
        return f"provider-{len(self.providers)}"

    def apply_combo(self, combo):
        self.combos.append(combo)


class ApplyInstallTests(unittest.TestCase):
    def test_apply_renders_secrets_configures_services_and_persists_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layout = resolve_layout(platform_name="Linux", home=root, environ={})
            runner = FakeRunner(root / ".hermes" / ".env")
            omniroute = FakeOmniRoute()
            provider = ProviderConfig(
                provider_id="example",
                kind=ProviderKind.OPENAI_COMPATIBLE,
                base_url="https://models.example/v1",
                credential_env="EXAMPLE_API_KEY",
                privacy="cloud",
            )
            answers = InstallAnswers(mode=InstallMode.CLOUD, providers=(provider,))
            model = ModelCandidate(
                provider_id="example",
                model_id="strong",
                capabilities=frozenset(
                    {
                        Capability.FAST,
                        Capability.CODING,
                        Capability.AGENTIC,
                        Capability.REASONING,
                    }
                ),
                context_window=128000,
                supports_tools=True,
            )
            installer = Installer(
                dry_run=False,
                runner=runner,
                resource_root=ROOT,
                token_factory=lambda: "generated-safe-token-123456",
                omniroute_client=omniroute,
            )
            report = installer.install(
                answers=answers,
                binding=bind_capabilities((model,)),
                layout=layout,
                credentials={"EXAMPLE_API_KEY": "synthetic-provider-key"},
            )

            self.assertFalse(report.dry_run)
            self.assertTrue((layout.services_dir / "compose.yaml").is_file())
            self.assertTrue((layout.services_dir / "routing-policy.json").is_file())
            secret_text = layout.secrets_file.read_text(encoding="utf-8")
            self.assertIn("EXAMPLE_API_KEY=synthetic-provider-key", secret_text)
            self.assertIn("HERMES_LOCAL_ROUTER_KEY=generated-safe-token-123456", secret_text)
            hermes_env = (root / ".hermes" / ".env").read_text(encoding="utf-8")
            self.assertIn("HERMES_LOCAL_ROUTER_KEY=generated-safe-token-123456", hermes_env)
            self.assertTrue(any(command[:2] == ("docker", "compose") for command in runner.commands))
            self.assertTrue(any(command[:3] == ("hermes", "config", "set") for command in runner.commands))
            self.assertEqual(omniroute.providers[0]["api_key"], "synthetic-provider-key")
            self.assertGreaterEqual(len(omniroute.combos), 7)
            state = StateStore(layout.state_file).load()
            self.assertIsNotNone(state)
            self.assertEqual(state.desired_state_hash, report.desired_state_hash)


if __name__ == "__main__":
    unittest.main()
