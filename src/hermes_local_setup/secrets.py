"""Atomic dotenv-style secret storage."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Mapping


_SECRET_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


class SecretStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __repr__(self) -> str:
        return f"SecretStore(path={self.path!s}, keys={self.names()!r})"

    @staticmethod
    def _validate(name: str, value: str) -> None:
        if not _SECRET_NAME.fullmatch(name):
            raise ValueError("secret names must be uppercase environment variable names")
        if not value or "\n" in value or "\r" in value or "\x00" in value:
            raise ValueError("secret values must be non-empty single-line strings")

    def _ensure_safe_target(self) -> None:
        if self.path.is_symlink():
            raise ValueError("secret file cannot be a symlink")
        if self.path.exists() and not self.path.is_file():
            raise ValueError("secret path must be a regular file")

    def _read(self) -> dict[str, str]:
        self._ensure_safe_target()
        if not self.path.exists():
            return {}
        values: dict[str, str] = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if _SECRET_NAME.fullmatch(name):
                values[name] = value
        return values

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._read()))

    def get_many(self, names: tuple[str, ...] | None = None) -> dict[str, str]:
        """Return requested values for an immediate privileged operation.

        Callers must not log, serialize, or include the returned mapping in
        command arguments.
        """
        values = self._read()
        if names is None:
            return values
        return {name: values[name] for name in names if name in values}

    def set(self, name: str, value: str) -> None:
        self.set_many({name: value})

    def set_many(self, values: Mapping[str, str]) -> None:
        for name, value in values.items():
            self._validate(name, value)
        self._ensure_safe_target()
        current = self._read()
        current.update(values)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=self.path.parent, text=True
        )
        temporary_path = Path(temporary_name)
        try:
            os.chmod(temporary_path, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                for key in sorted(current):
                    handle.write(f"{key}={current[key]}\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._ensure_safe_target()
            os.replace(temporary_path, self.path)
            if os.name != "nt":
                os.chmod(self.path, 0o600)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
