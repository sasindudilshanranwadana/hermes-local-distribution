"""Checksum-verified installation of curated third-party runtime components."""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath


SUPERPOWERS_URL = (
    "https://github.com/obra/superpowers/archive/"
    "b36e0829c6d0140e93cfef2ca599b1b07d4a7797.tar.gz"
)
SUPERPOWERS_SHA256 = "7c3ae7db406f8d92cf55329aa9e9a41e53f6cef00bdb68e1325713be97ef5d7c"


def _runtime_relative_path(name: str) -> Path | None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or len(path.parts) < 2:
        raise ValueError("unsafe archive path")
    relative = path.parts[1:]
    if relative[0] == ".hermes-plugin" and len(relative) > 1:
        return Path(*relative[1:])
    if relative[0] == "skills" and len(relative) > 1:
        return Path(*relative)
    if relative == ("LICENSE",):
        return Path("LICENSE")
    return None


def install_superpowers_archive(
    data: bytes, *, expected_sha256: str, destination: Path
) -> None:
    actual = hashlib.sha256(data).hexdigest()
    if not secrets_compare(actual, expected_sha256):
        raise ValueError("Superpowers archive checksum mismatch")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".superpowers.", dir=destination.parent))
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive.getmembers():
                relative = _runtime_relative_path(member.name)
                if relative is None or member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError("unsafe non-file entry in Superpowers archive")
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("could not read Superpowers archive entry")
                target = temporary / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("wb") as handle:
                    shutil.copyfileobj(source, handle)
        if not (temporary / "plugin.yaml").is_file() or not (temporary / "LICENSE").is_file():
            raise ValueError("Superpowers archive is missing required runtime files")
        backup = destination.with_name(f".{destination.name}.previous")
        if backup.exists():
            shutil.rmtree(backup)
        if destination.exists():
            os.replace(destination, backup)
        os.replace(temporary, destination)
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def secrets_compare(actual: str, expected: str) -> bool:
    import secrets

    return secrets.compare_digest(actual, expected)


def download_and_install_superpowers(hermes_home: Path) -> None:
    request = urllib.request.Request(
        SUPERPOWERS_URL,
        headers={"User-Agent": "Hermes-Local-Distribution/0.1"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(10_000_001)
    if len(data) > 10_000_000:
        raise ValueError("Superpowers archive exceeds the expected size limit")
    install_superpowers_archive(
        data,
        expected_sha256=SUPERPOWERS_SHA256,
        destination=hermes_home / "plugins" / "superpowers",
    )
