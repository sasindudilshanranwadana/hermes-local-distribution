#!/usr/bin/env python3
"""Create release ZIPs while restoring executable permissions lost by artifacts."""

from __future__ import annotations

import argparse
import shutil
import stat
from pathlib import Path

EXECUTABLES = {
    "hermes-local-setup-linux": (Path("Hermes-Local-Setup"),),
    "hermes-local-setup-macos": (
        Path("Hermes-Local-Setup"),
        Path("Hermes Local Setup.app/Contents/MacOS/Hermes-Local-Setup"),
    ),
    "hermes-local-setup-windows": (),
}


def archive_release_assets(release_assets: Path) -> list[Path]:
    if not release_assets.is_dir():
        raise NotADirectoryError(f"release asset directory does not exist: {release_assets}")

    archives: list[Path] = []
    for directory_name, executable_paths in EXECUTABLES.items():
        directory = release_assets / directory_name
        if not directory.is_dir():
            raise FileNotFoundError(f"missing platform artifact: {directory}")

        for relative_path in executable_paths:
            executable = directory / relative_path
            if not executable.is_file():
                raise FileNotFoundError(f"missing platform executable: {executable}")
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        archive = Path(shutil.make_archive(str(directory), "zip", root_dir=directory))
        archives.append(archive)
    return archives


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_assets", type=Path)
    arguments = parser.parse_args()
    archive_release_assets(arguments.release_assets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
