"""Render portable OmniRoute policy and validate generated text."""

from __future__ import annotations

import ipaddress
import json
import re

from .models import Capability, CapabilityBinding, ModelCandidate

_ROLE_POOLS = (
    (Capability.CODING, "pool-coding-simple"),
    (Capability.CODING, "pool-coding-complex"),
    (Capability.AGENTIC, "pool-agentic-simple"),
    (Capability.AGENTIC, "pool-agentic-complex"),
    (Capability.REASONING, "pool-reasoning-simple"),
    (Capability.REASONING, "pool-reasoning-complex"),
    (Capability.FAST, "pool-chat"),
    (Capability.LONG_CONTEXT, "pool-long-context"),
    (Capability.VISION, "pool-vision"),
)

_INLINE_SECRET = re.compile(
    r"(?i)\b[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*\s*=\s*[^$\s][^\s]*"
)


def validate_portable_text(text: str) -> None:
    if re.search(r"/(?:root)(?:/|$)", text):
        raise ValueError("generated text contains a privileged home path")
    if re.search(r"\b[a-z][a-z0-9-]*vps\b", text, flags=re.IGNORECASE):
        raise ValueError("generated text contains a host-specific VPS name")
    for raw_address in re.findall(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])", text):
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError:
            continue
        if not address.is_loopback:
            raise ValueError("generated text contains a non-loopback IP address")
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
    for role, pool_name in _ROLE_POOLS:
        primary = binding.primary.get(role)
        if primary is None:
            continue
        members = (primary, *binding.fallbacks.get(role, ()))
        combos.append(
            {
                "name": pool_name,
                "description": (
                    f"Generated {role.value} route; managed by Hermes Local Distribution."
                ),
                "strategy": "priority",
                "models": [_model_entry(model) for model in members],
            }
        )
    rendered = json.dumps({"schema_version": 1, "combos": combos}, indent=2, sort_keys=True)
    validate_portable_text(rendered)
    return f"{rendered}\n"
