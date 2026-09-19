"""Shell-free subprocess execution with bounded output and redaction."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .redaction import SecretRedactor


@dataclass(frozen=True, slots=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    dry_run: bool = False


class CommandRunner:
    def __init__(
        self,
        *,
        dry_run: bool = False,
        redactor: SecretRedactor | None = None,
        timeout: float = 120.0,
        max_output_chars: int = 100_000,
    ) -> None:
        self.dry_run = dry_run
        self.redactor = redactor or SecretRedactor()
        self.timeout = timeout
        self.max_output_chars = max_output_chars

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str | os.PathLike[str] | None = None,
        env: Mapping[str, str] | None = None,
        stdin: str | None = None,
    ) -> CommandResult:
        if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence):
            raise TypeError("argv must be a sequence of strings, never a shell command")
        normalized = tuple(str(item) for item in argv)
        if not normalized or any(not item for item in normalized):
            raise ValueError("argv cannot be empty")
        if any(self.redactor.contains_registered_secret(item) for item in normalized):
            raise ValueError("secret values must not appear in command argv")
        if self.dry_run:
            return CommandResult(normalized, 0, "dry-run", "", True)
        completed = subprocess.run(  # noqa: S603 - argv is structured and shell is disabled.
            normalized,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=self.timeout,
            check=False,
            shell=False,
        )
        stdout = self.redactor.redact(completed.stdout[: self.max_output_chars])
        stderr = self.redactor.redact(completed.stderr[: self.max_output_chars])
        return CommandResult(normalized, completed.returncode, stdout, stderr)
