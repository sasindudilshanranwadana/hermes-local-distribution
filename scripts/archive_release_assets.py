#!/usr/bin/env python3
"""Create release ZIPs while restoring executable permissions lost by artifacts."""

from __future__ import annotations

import argparse
import shutil
import stat
import zipfile
from pathlib import Path

EXECUTABLES = {
    "hermes-local-setup-linux": (Path("Hermes-Local-Setup"),),
    "hermes-local-setup-macos": (
        Path("Hermes-Local-Setup"),
        Path("Hermes Local Setup.app/Contents/MacOS/Hermes-Local-Setup"),
    ),
    "hermes-local-setup-windows": (),
}


def write_archive(directory: Path, executable_paths: tuple[Path, ...]) -> Path:
    archive_path = directory.with_suffix(".zip")
    executable_names = {path.as_posix() for path in executable_paths}
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in sorted(candidate for candidate in directory.rglob("*") if candidate.is_file()):
            relative_name = path.relative_to(directory).as_posix()
            mode = 0o755 if relative_name in executable_names else 0o644
            info = zipfile.ZipInfo.from_file(path, arcname=relative_name)
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
                shutil.copyfileobj(source, target)
    return archive_path


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

        archives.append(write_archive(directory, executable_paths))
    return archives


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_assets", type=Path)
    arguments = parser.parse_args()
    archive_release_assets(arguments.release_assets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
