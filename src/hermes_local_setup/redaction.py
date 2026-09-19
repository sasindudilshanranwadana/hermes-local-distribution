"""Central redaction for logs, errors, command output, and support bundles."""

from __future__ import annotations

import re
from collections.abc import Iterable


class SecretRedactor:
    _PATTERNS = (
        re.compile(r"(?i)(authorization\s*:\s*bearer\s+)([^\s,;]+)"),
        re.compile(
            r"(?i)\b([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)\s*=\s*([^\s]+)"
        ),
        re.compile(r"\b(?:sk|ghp|github_pat)_[A-Za-z0-9_\-]{16,}\b"),
    )

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        self._secrets = tuple(sorted({value for value in secrets if value}, key=len, reverse=True))

    def contains_registered_secret(self, text: str) -> bool:
        return any(secret in text for secret in self._secrets)

    def redact(self, text: str) -> str:
        redacted = text
        for secret in self._secrets:
            redacted = redacted.replace(secret, "[REDACTED]")
        redacted = self._PATTERNS[0].sub(r"\1[REDACTED]", redacted)
        redacted = self._PATTERNS[1].sub(r"\1=[REDACTED]", redacted)
        redacted = self._PATTERNS[2].sub("[REDACTED]", redacted)
        return redacted
