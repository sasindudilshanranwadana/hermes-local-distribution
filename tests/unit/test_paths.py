import unittest
from pathlib import Path

from hermes_local_setup.paths import resolve_layout


class PathTests(unittest.TestCase):
    def test_windows_uses_local_app_data(self) -> None:
        layout = resolve_layout(
            platform_name="Windows",
            home=Path("C:/Users/Friend"),
            environ={"LOCALAPPDATA": "C:/Users/Friend/AppData/Local"},
        )
        self.assertEqual(
            layout.data_dir,
            Path("C:/Users/Friend/AppData/Local/HermesLocalDistribution"),
        )

    def test_macos_uses_application_support(self) -> None:
        layout = resolve_layout(platform_name="Darwin", home=Path("/Users/friend"), environ={})
        self.assertEqual(
            layout.data_dir,
            Path("/Users/friend/Library/Application Support/HermesLocalDistribution"),
        )

    def test_linux_honors_xdg(self) -> None:
        layout = resolve_layout(
            platform_name="Linux",
            home=Path("/home/friend"),
            environ={"XDG_DATA_HOME": "/mnt/user-data"},
        )
        self.assertEqual(layout.data_dir, Path("/mnt/user-data/hermes-local-distribution"))


if __name__ == "__main__":
    unittest.main()
