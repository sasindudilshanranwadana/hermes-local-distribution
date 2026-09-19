"""Deterministic model-to-role binding for OmniRoute pool generation."""

from __future__ import annotations

from .models import Capability, CapabilityBinding, ModelCandidate


_REQUIRES_TOOLS = {Capability.CODING, Capability.AGENTIC}


def _score(model: ModelCandidate, role: Capability) -> int:
    score = 0
    if role in model.capabilities:
        score += 100
    if Capability.REASONING in model.capabilities:
        score += 25
    if model.supports_tools:
        score += 15
    if model.context_window >= 64_000:
        score += 10
    if role is Capability.FAST:
        score += max(0, 20 - model.context_window // 16_000)
    if role is Capability.LONG_CONTEXT:
        score += min(model.context_window // 8_000, 40)
    if role in _REQUIRES_TOOLS and not model.supports_tools:
        score -= 1_000
    if role is Capability.VISION and Capability.VISION not in model.capabilities:
        score -= 1_000
    return score


def bind_capabilities(models: tuple[ModelCandidate, ...]) -> CapabilityBinding:
    if not models:
        raise ValueError("at least one model is required")
    primary: dict[Capability, ModelCandidate] = {}
    fallbacks: dict[Capability, tuple[ModelCandidate, ...]] = {}
    degraded: set[Capability] = set()
    for role in Capability:
        ranked = tuple(
            sorted(models, key=lambda model: (-_score(model, role), model.provider_id, model.model_id))
        )
        viable = tuple(model for model in ranked if _score(model, role) >= 0)
        if viable:
            primary[role] = viable[0]
            fallbacks[role] = viable[1:]
        if not any(role in model.capabilities for model in models):
            degraded.add(role)
    for required in (Capability.FAST, Capability.CODING, Capability.AGENTIC, Capability.REASONING):
        if required not in primary:
            raise ValueError(f"no viable model for required capability: {required.value}")
    return CapabilityBinding(primary=primary, fallbacks=fallbacks, degraded=frozenset(degraded))
