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


def infer_model_candidate(
    *, provider_id: str, model_id: str, context_window: int = 64_000
) -> ModelCandidate:
    """Create a conservative initial profile from a discovered model identifier.

    The wizard shows the resulting roles before installation. Users can change
    the context size and tool-support choice when provider metadata is absent.
    """
    lowered = model_id.lower()
    capabilities: set[Capability] = {Capability.REASONING}
    if any(token in lowered for token in ("flash", "mini", "haiku", "small", "1.5b", "3b")):
        capabilities.add(Capability.FAST)
    if any(
        token in lowered
        for token in ("coder", "codex", "claude", "gpt", "qwen", "gemini", "deepseek")
    ):
        capabilities.update({Capability.CODING, Capability.AGENTIC})
    if any(token in lowered for token in ("vision", "vl", "multimodal", "gpt-4o")):
        capabilities.add(Capability.VISION)
    if context_window >= 128_000:
        capabilities.add(Capability.LONG_CONTEXT)
    if Capability.FAST not in capabilities:
        capabilities.add(Capability.FAST)
    supports_tools = Capability.AGENTIC in capabilities
    return ModelCandidate(
        provider_id=provider_id,
        model_id=model_id,
        capabilities=frozenset(capabilities),
        context_window=context_window,
        supports_tools=supports_tools,
    )
