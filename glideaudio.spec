# -*- mode: python ; coding: utf-8 -*-

"""PyInstaller specification file for GlideAudio."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

ROOT = Path(globals().get("SPECPATH", ".")).resolve()
PRODUCT_NAME = "GlideAudio"
ICON_FILE = ROOT / "glideaudio.ico"
VERSION_FILE = ROOT / "file_version_info.txt"

datas = collect_data_files("customtkinter") + collect_data_files("tkinterdnd2")

branding_assets = [
    "glideaudio.ico",
    "glideaudio-logo.png",
    "README.md",
    "PRODUCT-BRIEF.md",
]
for name in branding_assets:
    path = ROOT / name
    if path.exists():
        datas.append((str(path), "."))

binaries = []
ffmpeg_path = ROOT / "ffmpeg" / "bin"
if ffmpeg_path.exists():
    for filename in ("ffmpeg.exe", "ffprobe.exe"):
        source = ffmpeg_path / filename
        if source.exists():
            binaries.append((str(source), "ffmpeg/bin"))

a = Analysis(
    ["glideaudio.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=["customtkinter", "tkinterdnd2"],
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

exe_kwargs = dict(
    name=PRODUCT_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version_file=str(VERSION_FILE) if VERSION_FILE.exists() else None,
)

if ICON_FILE.exists():
    exe_kwargs["icon"] = str(ICON_FILE)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    **exe_kwargs,
)
