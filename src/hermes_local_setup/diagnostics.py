"""Allowlisted, secret-redacted support bundle generation."""

from __future__ import annotations

import json
import zipfile
from collections.abc import Mapping
from pathlib import Path

from .health import HealthReport
from .redaction import SecretRedactor


def create_support_bundle(
    output: Path,
    *,
    report: HealthReport,
    versions: Mapping[str, str],
    redactor: SecretRedactor,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    health_payload = {
        "overall": report.overall.value,
        "checks": [
            {
                "name": check.name,
                "level": check.level.value,
                "message": redactor.redact(check.message),
            }
            for check in report.checks
        ],
    }
    files = {
        "health.json": json.dumps(health_payload, indent=2, sort_keys=True) + "\n",
        "versions.json": json.dumps(dict(versions), indent=2, sort_keys=True) + "\n",
    }
    for contents in files.values():
        if redactor.redact(contents) != contents:
            raise ValueError("support bundle still contains a registered secret")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, contents in files.items():
            archive.writestr(name, contents)
