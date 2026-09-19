"""UI-independent setup wizard state machine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WizardPage(StrEnum):
    WELCOME = "Welcome"
    PRIVACY = "Privacy"
    SYSTEM_CHECK = "System check"
    MODE = "Choose model mode"
    PROVIDERS = "Add model providers"
    OPTIONS = "Optional services"
    REVIEW = "Review"
    INSTALL = "Install"
    VERIFY = "Verify"
    FINISH = "Finish"


_PAGES = tuple(WizardPage)


@dataclass(frozen=True, slots=True)
class WizardState:
    index: int = 0

    @property
    def page(self) -> WizardPage:
        return _PAGES[self.index]

    @property
    def can_advance(self) -> bool:
        return self.index < len(_PAGES) - 1

    @property
    def can_go_back(self) -> bool:
        return self.index > 0

    def advance(self) -> WizardState:
        return WizardState(min(self.index + 1, len(_PAGES) - 1))

    def back(self) -> WizardState:
        return WizardState(max(self.index - 1, 0))
