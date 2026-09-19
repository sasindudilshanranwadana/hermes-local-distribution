import tempfile
import unittest
from pathlib import Path

from hermes_local_setup.state import InstallState, StateStore


class StateStoreTests(unittest.TestCase):
    def test_round_trip_contains_key_names_but_not_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = StateStore(path)
            state = InstallState(
                phase="providers",
                completed=("preflight",),
                credential_names=("OPENROUTER_API_KEY",),
            )
            store.save(state)
            loaded = store.load()
            self.assertEqual(loaded, state)
            self.assertNotIn("secret-value", path.read_text(encoding="utf-8"))

    def test_rejects_secret_shaped_state_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(Path(tmp) / "state.json")
            with self.assertRaisesRegex(ValueError, "secret"):
                store.save(
                    InstallState(
                        phase="bad",
                        completed=("sk-abcdefghijklmnopqrstuvwxyz",),
                        credential_names=(),
                    )
                )


if __name__ == "__main__":
    unittest.main()
