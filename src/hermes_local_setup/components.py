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
    "https://github.com/obra/superpowers/archive/b36e0829c6d0140e93cfef2ca599b1b07d4a7797.tar.gz"
)
SUPERPOWERS_SHA256 = "7c3ae7db406f8d92cf55329aa9e9a41e53f6cef00bdb68e1325713be97ef5d7c"
MEM0_REVISION = "19cb89aff472325c707f64b2f34ae6afdbf7faf7"
MEM0_URL = f"https://github.com/mem0ai/mem0/archive/{MEM0_REVISION}.tar.gz"
MEM0_SHA256 = "2114561af9fca851089d0461f22bc023b26ea25ab24ee5515a632277f16b090b"


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


def install_superpowers_archive(data: bytes, *, expected_sha256: str, destination: Path) -> None:
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


def install_mem0_server_archive(
    data: bytes, *, expected_sha256: str, destination: Path
) -> None:
    """Install only the pinned Mem0 server subtree from an upstream archive."""
    actual = hashlib.sha256(data).hexdigest()
    if not secrets_compare(actual, expected_sha256):
        raise ValueError("Mem0 archive checksum mismatch")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".mem0-server.", dir=destination.parent))
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive.getmembers():
                source_path = PurePosixPath(member.name)
                if source_path.is_absolute() or ".." in source_path.parts:
                    raise ValueError("unsafe Mem0 archive path")
                if len(source_path.parts) < 3 or source_path.parts[1] != "server":
                    continue
                relative = Path(*source_path.parts[2:])
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError("unsafe non-file entry in Mem0 server archive")
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("could not read Mem0 server archive entry")
                target = temporary / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("wb") as handle:
                    shutil.copyfileobj(source, handle)
        if not (temporary / "Dockerfile").is_file() or not (temporary / "main.py").is_file():
            raise ValueError("Mem0 archive is missing required server files")
        (temporary / ".archive-sha256").write_text(expected_sha256 + "\n", encoding="utf-8")
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
    # URL is an immutable HTTPS constant with a pinned content checksum.
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        data = response.read(10_000_001)
    if len(data) > 10_000_000:
        raise ValueError("Superpowers archive exceeds the expected size limit")
    install_superpowers_archive(
        data,
        expected_sha256=SUPERPOWERS_SHA256,
        destination=hermes_home / "plugins" / "superpowers",
    )


def download_and_install_mem0_server(destination: Path) -> None:
    marker = destination / ".archive-sha256"
    if (
        (destination / "Dockerfile").is_file()
        and (destination / "main.py").is_file()
        and marker.is_file()
        and marker.read_text(encoding="utf-8").strip() == MEM0_SHA256
    ):
        return
    request = urllib.request.Request(
        MEM0_URL,
        headers={"User-Agent": "Hermes-Local-Distribution/0.1"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        data = response.read(30_000_001)
    if len(data) > 30_000_000:
        raise ValueError("Mem0 archive exceeds the expected size limit")
    install_mem0_server_archive(
        data,
        expected_sha256=MEM0_SHA256,
        destination=destination,
    )
