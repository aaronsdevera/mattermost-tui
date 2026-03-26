# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for one-file CLI builds (local + CI)."""

from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas: list = []
binaries: list = []
hiddenimports: list = []

for pkg in ("textual", "rich", "httpx", "certifi", "socksio"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except ImportError:
        pass

hiddenimports += [
    "mattermost_tui",
    "mattermost_tui.api",
    "mattermost_tui.api.auth",
    "mattermost_tui.api.client",
    "mattermost_tui.api.errors",
    "mattermost_tui.api.models",
    "mattermost_tui.api.channel_labels",
    "mattermost_tui.tui_app",
    "mattermost_tui.user_agent",
]

a = Analysis(
    ["mattermost_tui/cli.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="mattermost-tui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
