"""Provider discovery with narrow, redacted error handling."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from .models import ProviderConfig
from .redaction import SecretRedactor


Transport = Callable[[str, dict[str, str], float], tuple[int, bytes]]


class ProviderError(RuntimeError):
    """A user-actionable provider validation failure."""


def _default_transport(url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(1_000_000)
    except urllib.error.HTTPError as error:
        return error.code, error.read(100_000)


class ProviderClient:
    def __init__(
        self,
        *,
        transport: Transport = _default_transport,
        redactor: SecretRedactor | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._transport = transport
        self._redactor = redactor or SecretRedactor()
        self._timeout = timeout

    def __repr__(self) -> str:
        return f"ProviderClient(timeout={self._timeout!r})"

    def discover(self, provider: ProviderConfig, credential: str | None) -> tuple[str, ...]:
        headers = {"Accept": "application/json"}
        if credential:
            headers["Authorization"] = f"Bearer {credential}"
        url = f"{provider.base_url.rstrip('/')}/models"
        try:
            status, raw = self._transport(url, headers, self._timeout)
        except (OSError, TimeoutError) as error:
            detail = self._redactor.redact(str(error))
            raise ProviderError(f"Could not reach {provider.provider_id}: {detail}") from None
        if status in {401, 403}:
            raise ProviderError(
                f"{provider.provider_id} authentication failed; check the credential and try again"
            )
        if status == 429:
            raise ProviderError(f"{provider.provider_id} is rate limited; wait and try again")
        if status < 200 or status >= 300:
            raise ProviderError(f"{provider.provider_id} returned HTTP {status}")
        try:
            payload: Any = json.loads(raw)
            entries = payload["data"]
            identifiers = tuple(
                sorted(
                    {
                        entry["id"]
                        for entry in entries
                        if isinstance(entry, dict)
                        and isinstance(entry.get("id"), str)
                        and entry["id"]
                    }
                )
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            raise ProviderError(f"{provider.provider_id} returned an invalid model catalog") from None
        if not identifiers:
            raise ProviderError(f"{provider.provider_id} returned an empty model catalog")
        return identifiers

