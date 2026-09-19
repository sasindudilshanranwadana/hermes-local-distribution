"""Translate the sanitized golden policy into supported Hermes CLI actions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .render import validate_portable_text


def load_golden_policy(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    validate_portable_text(text)
    payload = json.loads(text)
    if payload.get("schema_version") != 1 or not isinstance(payload.get("settings"), dict):
        raise ValueError("unsupported golden policy schema")
    return payload


def _stringify(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    return str(value)


def build_hermes_actions(policy: dict[str, Any]) -> tuple[tuple[str, ...], ...]:
    actions: list[tuple[str, ...]] = []
    settings = policy.get("settings")
    if not isinstance(settings, dict):
        raise ValueError("golden policy settings must be an object")
    for key, value in settings.items():
        actions.append(("hermes", "config", "set", str(key), _stringify(value)))
    toolsets = policy.get("toolsets", {})
    for name in toolsets.get("enable", []):
        actions.append(("hermes", "tools", "enable", str(name)))
    for name in toolsets.get("disable", []):
        actions.append(("hermes", "tools", "disable", str(name)))
    actions.append(("hermes", "config", "check"))
    return tuple(actions)

