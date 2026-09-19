"""Resumable, dry-run-first installation orchestration."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .commands import CommandRunner
from .hermes_config import build_hermes_actions, load_golden_policy
from .models import CapabilityBinding, InstallAnswers
from .omniroute import OmniRouteClient
from .paths import AppLayout
from .render import render_routing_policy
from .secrets import SecretStore
from .state import InstallState, StateStore


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
    def __init__(
        self,
        *,
        dry_run: bool = True,
        runner: Any | None = None,
        resource_root: Path | None = None,
        token_factory: Callable[[], str] | None = None,
        omniroute_client: Any | None = None,
    ) -> None:
        self.dry_run = dry_run
        self.runner = runner or CommandRunner(dry_run=dry_run, timeout=360.0)
        self.resource_root = resource_root or Path(__file__).resolve().parents[2]
        self.token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self.omniroute_client = omniroute_client

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
        self,
        *,
        answers: InstallAnswers,
        binding: CapabilityBinding,
        layout: AppLayout,
        credentials: Mapping[str, str] | None = None,
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
        report = InstallReport(
            completed=_PHASES,
            desired_state_hash=desired_hash,
            actions=actions,
            dry_run=self.dry_run,
        )
        if self.dry_run:
            return report

        supplied_credentials = dict(credentials or {})
        required_names = {
            provider.credential_env
            for provider in answers.providers
            if provider.credential_env is not None
        }
        missing = sorted(name for name in required_names if not supplied_credentials.get(name))
        if missing:
            raise ValueError("missing provider credentials: " + ", ".join(missing))

        layout.data_dir.mkdir(parents=True, exist_ok=True)
        layout.config_dir.mkdir(parents=True, exist_ok=True)
        source_services = self.resource_root / "services"
        if not (source_services / "compose.yaml").is_file():
            raise ValueError(f"packaged services are missing from {source_services}")
        shutil.copytree(
            source_services,
            layout.services_dir,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("example.env", "runtime.env", "__pycache__", "*.pyc"),
        )
        routing_path = layout.services_dir / "routing-policy.json"
        routing_path.write_text(routing_policy, encoding="utf-8")

        router_key = self.token_factory()
        internal_key = self.token_factory()
        generated = {
            "HERMES_LOCAL_SECRETS_FILE": str(layout.secrets_file),
            "HERMES_LOCAL_ROUTER_KEY": router_key,
            "CLIENT_API_KEYS": router_key,
            "OMNIROUTE_API_KEY": internal_key,
            "OMNIROUTE_INTERNAL_SERVICE_TOKEN": internal_key,
            "OMNIROUTE_MGMT_API_KEY": self.token_factory(),
            "POSTGRES_DB": "mem0",
            "POSTGRES_USER": "mem0",
            "POSTGRES_PASSWORD": self.token_factory(),
            "JWT_SECRET": self.token_factory(),
            "MEM0_ADMIN_API_KEY": self.token_factory(),
        }
        generated.update(supplied_credentials)
        SecretStore(layout.secrets_file).set_many(generated)

        compose_command = [
            "docker",
            "compose",
            "--env-file",
            str(layout.secrets_file),
            "-f",
            str(layout.services_dir / "compose.yaml"),
        ]
        if answers.enable_mem0:
            compose_command.extend(("--profile", "mem0"))
        compose_command.extend(("up", "-d", "--build", "--wait", "--wait-timeout", "180"))
        self._run_checked(compose_command)

        env_path_result = self._run_checked(("hermes", "config", "env-path"))
        hermes_env_path = Path(env_path_result.stdout.strip()).expanduser()
        if not str(hermes_env_path):
            raise RuntimeError("Hermes did not report its secret environment path")
        SecretStore(hermes_env_path).set("HERMES_LOCAL_ROUTER_KEY", router_key)
        policy = load_golden_policy(self.resource_root / "policies" / "golden-policy.json")
        for action in build_hermes_actions(policy):
            self._run_checked(action)

        management_token = generated["OMNIROUTE_MGMT_API_KEY"]
        client = self.omniroute_client or OmniRouteClient(
            base_url="http://127.0.0.1:20128",
            management_token=management_token,
        )
        for provider in answers.providers:
            if provider.credential_env is None:
                continue
            client.add_provider(
                provider=provider.provider_id,
                name=provider.provider_id,
                url=provider.base_url,
                api_key=generated[provider.credential_env],
            )
        for combo in json.loads(routing_policy)["combos"]:
            client.apply_combo(combo)

        self._run_checked(
            (
                "docker",
                "compose",
                "--env-file",
                str(layout.secrets_file),
                "-f",
                str(layout.services_dir / "compose.yaml"),
                "ps",
            )
        )
        state = InstallState(
            phase="complete",
            completed=_PHASES,
            credential_names=tuple(sorted(required_names)),
            desired_state_hash=desired_hash,
        )
        StateStore(layout.state_file).save(state)
        return report

    def _run_checked(self, argv: Any):
        result = self.runner.run(argv)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise RuntimeError(f"command failed ({' '.join(result.argv)}): {detail}")
        return result

    def repair(
        self,
        *,
        answers: InstallAnswers,
        binding: CapabilityBinding,
        layout: AppLayout,
        credentials: Mapping[str, str] | None = None,
    ) -> InstallReport:
        return self.install(
            answers=answers,
            binding=binding,
            layout=layout,
            credentials=credentials,
        )
