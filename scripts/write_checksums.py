#!/usr/bin/env python3
"""Write a deterministic SHA-256 manifest for a release directory."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

MANIFEST_NAME = "SHA256SUMS.txt"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(distribution: Path) -> Path:
    if not distribution.is_dir():
        raise NotADirectoryError(f"release directory does not exist: {distribution}")

    manifest = distribution / MANIFEST_NAME
    files = sorted(
        (path for path in distribution.rglob("*") if path.is_file() and path != manifest),
        key=lambda path: path.relative_to(distribution).as_posix(),
    )
    lines = [f"{sha256(path)}  {path.relative_to(distribution).as_posix()}" for path in files]

    temporary_manifest = manifest.with_suffix(".tmp")
    temporary_manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary_manifest, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("distribution", type=Path)
    arguments = parser.parse_args()
    write_manifest(arguments.distribution)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
