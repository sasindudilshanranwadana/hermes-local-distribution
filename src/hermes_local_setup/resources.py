"""Resolve bundled resources in source checkouts and PyInstaller builds."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_root() -> Path:
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(str(bundle))
    return Path(__file__).resolve().parents[2]
