# -*- mode: python ; coding: utf-8 -*-
import sys


analysis = Analysis(
    ["src/hermes_local_setup/packaged_entry.py"],
    pathex=["src"],
    binaries=[],
    datas=[
        ("services", "services"),
        ("policies", "policies"),
        ("manifests", "manifests"),
        ("vendor", "vendor"),
    ],
    hiddenimports=["tkinter", "tomllib"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="Hermes-Local-Setup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=sys.platform == "darwin",
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if sys.platform == "darwin":
    app = BUNDLE(
        executable,
        name="Hermes Local Setup.app",
        icon=None,
        bundle_identifier="ai.hermes.local-setup",
    )

