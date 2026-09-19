"""Immutable domain models for installation and routing decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from ipaddress import ip_address
from types import MappingProxyType
from typing import Mapping
from urllib.parse import urlparse


class InstallMode(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"
    HYBRID = "hybrid"


class ProviderKind(str, Enum):
    OPENAI_COMPATIBLE = "openai-compatible"
    OLLAMA = "ollama"
    LM_STUDIO = "lm-studio"
    OAUTH = "oauth"


class Capability(str, Enum):
    FAST = "fast"
    CODING = "coding"
    AGENTIC = "agentic"
    REASONING = "reasoning"
    LONG_CONTEXT = "long-context"
    VISION = "vision"


def _is_loopback(hostname: str | None) -> bool:
    if not hostname:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    provider_id: str
    kind: ProviderKind
    base_url: str
    credential_env: str | None
    privacy: str

    def __post_init__(self) -> None:
        if not self.provider_id or not self.provider_id.replace("-", "").isalnum():
            raise ValueError("provider_id must contain only letters, numbers, and hyphens")
        if self.privacy not in {"local", "cloud"}:
            raise ValueError("privacy must be 'local' or 'cloud'")
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base_url must be an HTTP(S) URL")
        if self.privacy == "cloud" and parsed.scheme != "https":
            raise ValueError("cloud providers require an HTTPS endpoint")
        if self.privacy == "local" and not _is_loopback(parsed.hostname):
            raise ValueError("local providers must use a loopback endpoint")


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    provider_id: str
    model_id: str
    capabilities: frozenset[Capability]
    context_window: int
    supports_tools: bool

    def __post_init__(self) -> None:
        if not self.provider_id or not self.model_id:
            raise ValueError("provider_id and model_id are required")
        if self.context_window < 1:
            raise ValueError("context_window must be positive")


@dataclass(frozen=True, slots=True)
class CapabilityBinding:
    primary: Mapping[Capability, ModelCandidate]
    fallbacks: Mapping[Capability, tuple[ModelCandidate, ...]]
    degraded: frozenset[Capability] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "primary", MappingProxyType(dict(self.primary)))
        object.__setattr__(self, "fallbacks", MappingProxyType(dict(self.fallbacks)))


@dataclass(frozen=True, slots=True)
class InstallAnswers:
    mode: InstallMode
    providers: tuple[ProviderConfig, ...]
    enable_mem0: bool = False

    def __post_init__(self) -> None:
        if not self.providers:
            raise ValueError("at least one provider is required")
        if self.mode is InstallMode.LOCAL and any(
            provider.privacy != "local" for provider in self.providers
        ):
            raise ValueError("local-only mode cannot include a cloud provider")

