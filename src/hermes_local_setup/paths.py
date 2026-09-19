"""Cross-platform application paths with injectable inputs for testing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppLayout:
    data_dir: Path
    config_dir: Path
    secrets_file: Path
    state_file: Path
    services_dir: Path


def resolve_layout(*, platform_name: str, home: Path, environ: Mapping[str, str]) -> AppLayout:
    if platform_name == "Windows":
        base = Path(environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        data_dir = base / "HermesLocalDistribution"
        config_dir = data_dir / "config"
    elif platform_name == "Darwin":
        data_dir = home / "Library" / "Application Support" / "HermesLocalDistribution"
        config_dir = home / "Library" / "Preferences" / "HermesLocalDistribution"
    else:
        data_base = Path(environ.get("XDG_DATA_HOME", str(home / ".local" / "share")))
        config_base = Path(environ.get("XDG_CONFIG_HOME", str(home / ".config")))
        data_dir = data_base / "hermes-local-distribution"
        config_dir = config_base / "hermes-local-distribution"
    return AppLayout(
        data_dir=data_dir,
        config_dir=config_dir,
        secrets_file=config_dir / "secrets.env",
        state_file=config_dir / "install-state.json",
        services_dir=data_dir / "services",
    )
