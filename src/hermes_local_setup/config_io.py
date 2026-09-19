"""Strict loading of non-secret wizard answers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import (
    Capability,
    InstallAnswers,
    InstallMode,
    ModelCandidate,
    ProviderConfig,
    ProviderKind,
)


_ROOT_FIELDS = {"mode", "enable_mem0", "providers", "models"}
_PROVIDER_FIELDS = {
    "provider_id",
    "kind",
    "base_url",
    "credential_env",
    "privacy",
}
_MODEL_FIELDS = {
    "provider_id",
    "model_id",
    "capabilities",
    "context_window",
    "supports_tools",
}


def _reject_unknown(payload: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"unknown {label} fields: {', '.join(unknown)}")


def load_answers(path: Path) -> tuple[InstallAnswers, tuple[ModelCandidate, ...]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("answers must be a JSON object")
    _reject_unknown(payload, _ROOT_FIELDS, "answer")
    raw_providers = payload.get("providers")
    raw_models = payload.get("models")
    if not isinstance(raw_providers, list) or not isinstance(raw_models, list):
        raise ValueError("providers and models must be arrays")
    providers: list[ProviderConfig] = []
    for entry in raw_providers:
        if not isinstance(entry, dict):
            raise ValueError("provider entries must be objects")
        _reject_unknown(entry, _PROVIDER_FIELDS, "provider")
        providers.append(
            ProviderConfig(
                provider_id=str(entry["provider_id"]),
                kind=ProviderKind(str(entry["kind"])),
                base_url=str(entry["base_url"]),
                credential_env=(
                    None if entry.get("credential_env") is None else str(entry["credential_env"])
                ),
                privacy=str(entry["privacy"]),
            )
        )
    models: list[ModelCandidate] = []
    for entry in raw_models:
        if not isinstance(entry, dict):
            raise ValueError("model entries must be objects")
        _reject_unknown(entry, _MODEL_FIELDS, "model")
        raw_capabilities = entry.get("capabilities")
        if not isinstance(raw_capabilities, list):
            raise ValueError("model capabilities must be an array")
        models.append(
            ModelCandidate(
                provider_id=str(entry["provider_id"]),
                model_id=str(entry["model_id"]),
                capabilities=frozenset(Capability(str(item)) for item in raw_capabilities),
                context_window=int(entry["context_window"]),
                supports_tools=bool(entry["supports_tools"]),
            )
        )
    answers = InstallAnswers(
        mode=InstallMode(str(payload["mode"])),
        providers=tuple(providers),
        enable_mem0=bool(payload.get("enable_mem0", False)),
    )
    provider_ids = {provider.provider_id for provider in providers}
    unknown_model_providers = sorted(
        {model.provider_id for model in models if model.provider_id not in provider_ids}
    )
    if unknown_model_providers:
        raise ValueError(
            "models reference unknown providers: " + ", ".join(unknown_model_providers)
        )
    if not models:
        raise ValueError("at least one model is required")
    return answers, tuple(models)

