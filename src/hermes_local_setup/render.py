"""Render portable OmniRoute policy and validate generated text."""

from __future__ import annotations

import json
import re

from .models import Capability, CapabilityBinding, ModelCandidate


_ROLE_POOLS = {
    Capability.CODING: "pool-coding-complex",
    Capability.AGENTIC: "pool-agentic-complex",
    Capability.REASONING: "pool-reasoning-complex",
    Capability.FAST: "pool-conversation-simple",
    Capability.LONG_CONTEXT: "pool-long-context",
    Capability.VISION: "pool-vision",
}

_FORBIDDEN_MARKERS = ("100.81.25.128", "/root", "sasivps")
_INLINE_SECRET = re.compile(
    r"(?i)\b[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*\s*=\s*[^$\s][^\s]*"
)


def validate_portable_text(text: str) -> None:
    marker = next((value for value in _FORBIDDEN_MARKERS if value in text), None)
    if marker:
        raise ValueError(f"generated text contains forbidden host marker: {marker}")
    if _INLINE_SECRET.search(text):
        raise ValueError("generated text contains an inline secret")


def _model_entry(model: ModelCandidate) -> dict[str, object]:
    return {
        "kind": "model",
        "providerId": model.provider_id,
        "model": f"{model.provider_id}/{model.model_id}",
        "weight": 0,
    }


def render_routing_policy(binding: CapabilityBinding) -> str:
    combos: list[dict[str, object]] = []
    for role, pool_name in _ROLE_POOLS.items():
        primary = binding.primary.get(role)
        if primary is None:
            continue
        members = (primary, *binding.fallbacks.get(role, ()))
        combos.append(
            {
                "name": pool_name,
                "description": f"Generated {role.value} route; managed by Hermes Local Distribution.",
                "strategy": "priority",
                "models": [_model_entry(model) for model in members],
            }
        )
    rendered = json.dumps({"schema_version": 1, "combos": combos}, indent=2, sort_keys=True)
    validate_portable_text(rendered)
    return f"{rendered}\n"

