"""Health status primitives shared by the wizard, CLI, and diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HealthLevel(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    ACTION_REQUIRED = "action-required"
    UNAVAILABLE = "unavailable"


_SEVERITY = {
    HealthLevel.HEALTHY: 0,
    HealthLevel.DEGRADED: 1,
    HealthLevel.ACTION_REQUIRED: 2,
    HealthLevel.UNAVAILABLE: 3,
}


@dataclass(frozen=True, slots=True)
class HealthCheck:
    name: str
    level: HealthLevel
    message: str


@dataclass(frozen=True, slots=True)
class HealthReport:
    checks: tuple[HealthCheck, ...]

    @property
    def overall(self) -> HealthLevel:
        if not self.checks:
            return HealthLevel.UNAVAILABLE
        return max((check.level for check in self.checks), key=_SEVERITY.__getitem__)

