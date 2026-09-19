import json
import unittest
from pathlib import Path

from hermes_local_setup.hermes_config import build_hermes_actions, load_golden_policy


ROOT = Path(__file__).resolve().parents[2]


class HermesConfigTests(unittest.TestCase):
    def test_golden_policy_is_personal_data_free(self) -> None:
        path = ROOT / "policies" / "golden-policy.json"
        policy = load_golden_policy(path)
        serialized = json.dumps(policy, sort_keys=True)
        for marker in (
            "100.81.25.128",
            "/root",
            "sasivps",
            "discord",
            "telegram",
            "SOUL.md",
        ):
            self.assertNotIn(marker, serialized)

    def test_actions_use_supported_commands_and_secret_reference(self) -> None:
        policy = load_golden_policy(ROOT / "policies" / "golden-policy.json")
        actions = build_hermes_actions(policy)
        self.assertIn(
            ("hermes", "config", "set", "approvals.mode", "smart"),
            actions,
        )
        flattened = "\n".join(" ".join(action) for action in actions)
        self.assertIn("${HERMES_LOCAL_ROUTER_KEY}", flattened)
        self.assertNotIn("synthetic-secret", flattened)


if __name__ == "__main__":
    unittest.main()

