"""Non-secret resumable installation state."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


_SECRET_SHAPE = re.compile(r"(?:sk-|ghp_|github_pat_|Bearer\s+)[A-Za-z0-9_\-]{12,}")


@dataclass(frozen=True, slots=True)
class InstallState:
    phase: str
    completed: tuple[str, ...]
    credential_names: tuple[str, ...]
    desired_state_hash: str = ""


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def save(self, state: InstallState) -> None:
        serialized = json.dumps(asdict(state), indent=2, sort_keys=True)
        if _SECRET_SHAPE.search(serialized):
            raise ValueError("installation state cannot contain secret values")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=self.path.parent, text=True
        )
        temporary_path = Path(temporary_name)
        try:
            os.chmod(temporary_path, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(serialized)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def load(self) -> InstallState | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return InstallState(
            phase=str(payload["phase"]),
            completed=tuple(payload.get("completed", ())),
            credential_names=tuple(payload.get("credential_names", ())),
            desired_state_hash=str(payload.get("desired_state_hash", "")),
        )

