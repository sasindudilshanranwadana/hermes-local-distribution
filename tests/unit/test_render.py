import json
import unittest

from hermes_local_setup.capabilities import bind_capabilities
from hermes_local_setup.models import Capability, ModelCandidate
from hermes_local_setup.render import render_routing_policy, validate_portable_text


class RenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        models = (
            ModelCandidate(
                provider_id="provider-one",
                model_id="strong-coder",
                capabilities=frozenset(
                    {Capability.CODING, Capability.AGENTIC, Capability.REASONING}
                ),
                context_window=128000,
                supports_tools=True,
            ),
            ModelCandidate(
                provider_id="provider-two",
                model_id="fast-model",
                capabilities=frozenset({Capability.FAST}),
                context_window=32000,
                supports_tools=True,
            ),
        )
        self.binding = bind_capabilities(models)

    def test_routing_policy_contains_generated_roles(self) -> None:
        policy = json.loads(render_routing_policy(self.binding))
        names = {combo["name"] for combo in policy["combos"]}
        self.assertIn("pool-coding-complex", names)
        self.assertIn("pool-agentic-complex", names)
        self.assertIn("pool-reasoning-complex", names)
        serialized = json.dumps(policy)
        self.assertNotIn("100.81.25.128", serialized)
        self.assertNotIn("/root", serialized)

    def test_portability_validator_rejects_vps_markers_and_secrets(self) -> None:
        for unsafe in (
            "http://100.81.25.128:8801",
            "/root/.hermes",
            "sasivps",
            "OPENAI_API_KEY=real-value",
        ):
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                validate_portable_text(unsafe)


if __name__ == "__main__":
    unittest.main()
