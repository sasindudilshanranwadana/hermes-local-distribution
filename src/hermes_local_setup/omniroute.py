"""Narrow OmniRoute management client for provider and routing setup."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from .redaction import SecretRedactor


Transport = Callable[[str, str, dict[str, str], bytes | None, float], tuple[int, bytes]]


class OmniRouteError(RuntimeError):
    pass


def _transport(
    method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers=headers, data=body, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(1_000_000)
    except urllib.error.HTTPError as error:
        return error.code, error.read(100_000)


class OmniRouteClient:
    def __init__(
        self,
        *,
        base_url: str,
        management_token: str,
        transport: Transport = _transport,
        redactor: SecretRedactor | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._management_token = management_token
        self._transport = transport
        self._redactor = redactor or SecretRedactor([management_token])
        self._timeout = timeout

    def __repr__(self) -> str:
        return f"OmniRouteClient(base_url={self._base_url!r}, timeout={self._timeout!r})"

    def _request(self, method: str, path: str, payload: object | None = None) -> Any:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._management_token}",
            "Content-Type": "application/json",
        }
        try:
            status, raw = self._transport(
                method, f"{self._base_url}{path}", headers, body, self._timeout
            )
        except (OSError, TimeoutError) as error:
            raise OmniRouteError(self._redactor.redact(f"OmniRoute unavailable: {error}")) from None
        if status < 200 or status >= 300:
            detail = self._redactor.redact(raw.decode("utf-8", errors="replace")[:500])
            raise OmniRouteError(f"OmniRoute returned HTTP {status}: {detail}")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise OmniRouteError("OmniRoute returned an invalid JSON response") from None

    def add_provider(self, *, provider: str, name: str, url: str, api_key: str) -> str:
        response = self._request(
            "POST",
            "/api/providers",
            {"provider": provider, "name": name, "url": url, "apiKey": api_key},
        )
        identifier = response.get("id") if isinstance(response, dict) else None
        if not isinstance(identifier, str) or not identifier:
            raise OmniRouteError("OmniRoute created a provider without returning its identifier")
        return identifier

    def ensure_provider(self, *, provider: str, name: str, url: str, api_key: str) -> str:
        response = self._request("GET", "/api/providers")
        connections = response.get("connections", []) if isinstance(response, dict) else response
        for connection in connections if isinstance(connections, list) else []:
            if not isinstance(connection, dict):
                continue
            if connection.get("provider") == provider and connection.get("name") == name:
                identifier = connection.get("id")
                if not isinstance(identifier, str) or not identifier:
                    continue
                self._request(
                    "PATCH",
                    f"/api/providers/{identifier}",
                    {"provider": provider, "name": name, "url": url, "apiKey": api_key},
                )
                return identifier
        return self.add_provider(provider=provider, name=name, url=url, api_key=api_key)

    def apply_combo(self, combo: dict[str, object]) -> None:
        self._request("POST", "/api/combos", combo)

    def ensure_combo(self, combo: dict[str, object]) -> None:
        response = self._request("GET", "/api/combos")
        items = response.get("combos", []) if isinstance(response, dict) else response
        for current in items if isinstance(items, list) else []:
            if not isinstance(current, dict) or current.get("name") != combo.get("name"):
                continue
            identifier = current.get("id")
            if isinstance(identifier, str) and identifier:
                self._request("PUT", f"/api/combos/{identifier}", combo)
                return
        self.apply_combo(combo)
