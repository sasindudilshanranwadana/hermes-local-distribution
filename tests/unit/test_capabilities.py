import unittest

from hermes_local_setup.capabilities import bind_capabilities, infer_model_candidate
from hermes_local_setup.models import Capability, ModelCandidate


class CapabilityBindingTests(unittest.TestCase):
    def test_prefers_tool_capable_long_context_model_for_complex_coding(self) -> None:
        models = (
            ModelCandidate(
                provider_id="fast",
                model_id="small",
                capabilities=frozenset({Capability.FAST}),
                context_window=16000,
                supports_tools=False,
            ),
            ModelCandidate(
                provider_id="strong",
                model_id="coder",
                capabilities=frozenset({Capability.CODING, Capability.REASONING}),
                context_window=128000,
                supports_tools=True,
            ),
        )
        binding = bind_capabilities(models)
        self.assertEqual(binding.primary[Capability.CODING].model_id, "coder")
        self.assertEqual(binding.primary[Capability.AGENTIC].model_id, "coder")

    def test_reports_optional_degradation_but_requires_primary_route(self) -> None:
        models = (
            ModelCandidate(
                provider_id="only",
                model_id="general",
                capabilities=frozenset({Capability.REASONING}),
                context_window=64000,
                supports_tools=True,
            ),
        )
        binding = bind_capabilities(models)
        self.assertIn(Capability.VISION, binding.degraded)
        self.assertIn(Capability.FAST, binding.primary)

    def test_rejects_empty_model_catalog(self) -> None:
        with self.assertRaisesRegex(ValueError, "model"):
            bind_capabilities(())

    def test_infers_common_model_roles_conservatively(self) -> None:
        coder = infer_model_candidate(
            provider_id="local", model_id="qwen-coder-vl", context_window=131072
        )
        self.assertIn(Capability.CODING, coder.capabilities)
        self.assertIn(Capability.AGENTIC, coder.capabilities)
        self.assertIn(Capability.VISION, coder.capabilities)
        self.assertIn(Capability.LONG_CONTEXT, coder.capabilities)
        self.assertTrue(coder.supports_tools)

        small = infer_model_candidate(
            provider_id="local", model_id="tiny-small-3b", context_window=16000
        )
        self.assertIn(Capability.FAST, small.capabilities)
        self.assertFalse(small.supports_tools)


if __name__ == "__main__":
    unittest.main()
