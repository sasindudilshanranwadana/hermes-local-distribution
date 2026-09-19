"""Command-line surface for automation, repair, and support."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .capabilities import bind_capabilities
from .config_io import load_answers
from .diagnostics import create_support_bundle
from .health import HealthCheck, HealthLevel, HealthReport
from .installer import Installer, InstallReport
from .paths import AppLayout, resolve_layout
from .redaction import SecretRedactor
from .secrets import SecretStore


def _layout() -> AppLayout:
    return resolve_layout(
        platform_name=platform.system(),
        home=Path.home(),
        environ=os.environ,
    )


def _report_payload(report: InstallReport) -> dict[str, object]:
    return {
        "completed": list(report.completed),
        "desired_state_hash": report.desired_state_hash,
        "actions": list(report.actions),
        "dry_run": report.dry_run,
    }


def _run_plan(args: argparse.Namespace) -> int:
    answers, models = load_answers(args.answers)
    report = Installer(dry_run=True).install(
        answers=answers,
        binding=bind_capabilities(models),
        layout=_layout(),
    )
    if args.json:
        print(json.dumps(_report_payload(report), indent=2, sort_keys=True))
    else:
        print(report.as_text())
    return 0


def _run_install(args: argparse.Namespace) -> int:
    if not args.apply and not args.dry_run:
        print("install requires either --dry-run or explicit --apply", file=sys.stderr)
        return 2
    answers, models = load_answers(args.answers)
    credentials = (
        SecretStore(args.secrets_file).get_many()
        if args.apply and args.secrets_file is not None
        else {}
    )
    report = Installer(dry_run=not args.apply).install(
        answers=answers,
        binding=bind_capabilities(models),
        layout=_layout(),
        credentials=credentials,
    )
    print(report.as_text())
    return 0


def _run_repair(args: argparse.Namespace) -> int:
    if not args.apply and not args.dry_run:
        print("repair requires either --dry-run or explicit --apply", file=sys.stderr)
        return 2
    answers, models = load_answers(args.answers)
    credentials = (
        SecretStore(args.secrets_file).get_many()
        if args.apply and args.secrets_file is not None
        else {}
    )
    report = Installer(dry_run=not args.apply).repair(
        answers=answers,
        binding=bind_capabilities(models),
        layout=_layout(),
        credentials=credentials,
    )
    print(report.as_text())
    return 0


def _doctor_report() -> HealthReport:
    checks = (
        HealthCheck(
            "Hermes executable",
            HealthLevel.HEALTHY if shutil.which("hermes") else HealthLevel.ACTION_REQUIRED,
            "available" if shutil.which("hermes") else "Hermes must be installed",
        ),
        HealthCheck(
            "Docker",
            HealthLevel.HEALTHY if shutil.which("docker") else HealthLevel.ACTION_REQUIRED,
            "available" if shutil.which("docker") else "Docker Desktop must be installed",
        ),
    )
    return HealthReport(checks=checks)


def _run_doctor(args: argparse.Namespace) -> int:
    report = _doctor_report()
    payload = {
        "overall": report.overall.value,
        "checks": [asdict(check) for check in report.checks],
    }
    print(json.dumps(payload, indent=2, default=lambda value: value.value))
    return 0 if report.overall in {HealthLevel.HEALTHY, HealthLevel.DEGRADED} else 1


def _run_support_bundle(args: argparse.Namespace) -> int:
    create_support_bundle(
        args.output,
        report=_doctor_report(),
        versions={"kit": __version__, "python": platform.python_version()},
        redactor=SecretRedactor(),
    )
    print(f"Support bundle created: {args.output}")
    return 0


def _run_uninstall_plan(args: argparse.Namespace) -> int:
    print("Uninstall plan (no changes made):")
    print("- Stop the hermes-local-distribution Compose project")
    print("- Preserve model-provider credentials unless explicitly requested")
    print("- Preserve memories and Docker volumes by default")
    print("- Remove only generated application files")
    return 0


def _run_gui(args: argparse.Namespace) -> int:
    from .gui import launch

    launch()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hermes-local-setup")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="show a secret-free installation plan")
    plan.add_argument("--answers", type=Path, required=True)
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(handler=_run_plan)

    install = subparsers.add_parser("install", help="install or dry-run the local system")
    install.add_argument("--answers", type=Path, required=True)
    install.add_argument("--dry-run", action="store_true")
    install.add_argument("--apply", action="store_true")
    install.add_argument(
        "--secrets-file",
        type=Path,
        help="owner-only environment file; values are never accepted as command arguments",
    )
    install.set_defaults(handler=_run_install)

    repair = subparsers.add_parser("repair", help="restore the declared local system state")
    repair.add_argument("--answers", type=Path, required=True)
    repair.add_argument("--dry-run", action="store_true")
    repair.add_argument("--apply", action="store_true")
    repair.add_argument("--secrets-file", type=Path)
    repair.set_defaults(handler=_run_repair)

    doctor = subparsers.add_parser("doctor", help="check prerequisites and service health")
    doctor.set_defaults(handler=_run_doctor)

    bundle = subparsers.add_parser("support-bundle", help="create a redacted diagnostic ZIP")
    bundle.add_argument("--output", type=Path, required=True)
    bundle.set_defaults(handler=_run_support_bundle)

    uninstall = subparsers.add_parser("uninstall-plan", help="show preservation-first removal")
    uninstall.set_defaults(handler=_run_uninstall_plan)

    gui = subparsers.add_parser("gui", help="launch the setup wizard")
    gui.set_defaults(handler=_run_gui)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    if argv is None and len(sys.argv) == 1:
        argv = ["gui"]
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Setup could not continue: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
