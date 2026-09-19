import tempfile
import unittest
from pathlib import Path

from hermes_local_setup.capabilities import bind_capabilities
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


class InstallPlanTests(unittest.TestCase):
    def _inputs(self, root: Path):
        provider = ProviderConfig(
            provider_id="ollama",
            kind=ProviderKind.OLLAMA,
            base_url="http://127.0.0.1:11434/v1",
            credential_env=None,
            privacy="local",
        )
        answers = InstallAnswers(mode=InstallMode.LOCAL, providers=(provider,))
        model = ModelCandidate(
            provider_id="ollama",
            model_id="qwen-local",
            capabilities=frozenset(
                {Capability.FAST, Capability.CODING, Capability.AGENTIC, Capability.REASONING}
            ),
            context_window=128000,
            supports_tools=True,
        )
        layout = resolve_layout(platform_name="Linux", home=root, environ={})
        return answers, bind_capabilities((model,)), layout

    def test_dry_run_plan_is_ordered_and_vps_free(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            answers, binding, layout = self._inputs(Path(tmp))
            installer = Installer(dry_run=True)
            report = installer.install(answers=answers, binding=binding, layout=layout)
            self.assertEqual(
                report.completed,
                ("preflight", "render", "services", "hermes", "verify"),
            )
            text = report.as_text()
            self.assertNotIn("100.81.25.128", text)
            self.assertNotIn("sasivps", text)

    def test_repair_uses_same_desired_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            answers, binding, layout = self._inputs(Path(tmp))
            installer = Installer(dry_run=True)
            first = installer.install(answers=answers, binding=binding, layout=layout)
            repaired = installer.repair(answers=answers, binding=binding, layout=layout)
            self.assertEqual(first.desired_state_hash, repaired.desired_state_hash)


if __name__ == "__main__":
    unittest.main()

