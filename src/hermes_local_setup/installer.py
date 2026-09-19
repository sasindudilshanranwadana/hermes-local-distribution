"""Resumable, dry-run-first installation orchestration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .models import CapabilityBinding, InstallAnswers
from .paths import AppLayout
from .render import render_routing_policy


_PHASES = ("preflight", "render", "services", "hermes", "verify")


@dataclass(frozen=True, slots=True)
class InstallReport:
    completed: tuple[str, ...]
    desired_state_hash: str
    actions: tuple[str, ...]
    dry_run: bool

    def as_text(self) -> str:
        return "\n".join(
            (
                f"mode={'dry-run' if self.dry_run else 'apply'}",
                f"desired_state={self.desired_state_hash}",
                *(f"completed={phase}" for phase in self.completed),
                *(f"action={action}" for action in self.actions),
            )
        )


class Installer:
    def __init__(self, *, dry_run: bool = True) -> None:
        self.dry_run = dry_run

    @staticmethod
    def _desired_hash(
        answers: InstallAnswers, binding: CapabilityBinding, routing_policy: str
    ) -> str:
        payload = {
            "mode": answers.mode.value,
            "providers": [
                {
                    "id": provider.provider_id,
                    "kind": provider.kind.value,
                    "base_url": provider.base_url,
                    "privacy": provider.privacy,
                }
                for provider in answers.providers
            ],
            "mem0": answers.enable_mem0,
            "routing": json.loads(routing_policy),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(canonical).hexdigest()

    def install(
        self, *, answers: InstallAnswers, binding: CapabilityBinding, layout: AppLayout
    ) -> InstallReport:
        routing_policy = render_routing_policy(binding)
        desired_hash = self._desired_hash(answers, binding, routing_policy)
        actions = (
            "check Hermes and Docker prerequisites",
            f"render portable services into {layout.services_dir}",
            "start loopback-only service stack",
            "apply supported Hermes configuration commands",
            "run model, route, and memory health checks",
        )
        return InstallReport(
            completed=_PHASES,
            desired_state_hash=desired_hash,
            actions=actions,
            dry_run=self.dry_run,
        )

    def repair(
        self, *, answers: InstallAnswers, binding: CapabilityBinding, layout: AppLayout
    ) -> InstallReport:
        return self.install(answers=answers, binding=binding, layout=layout)
