# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

block_cipher = None

sv_ttk_datas, sv_ttk_binaries, sv_ttk_hidden = collect_all('sv_ttk')

a = Analysis(
    ['dl.py'],
    pathex=[],
    binaries=[*sv_ttk_binaries],
    datas=[
        ('yt-dlp.exe', '.'),
        ('ffmpeg.exe', '.'),
        ('ffprobe.exe', '.'),
        ('icon.ico', '.'),
        *sv_ttk_datas,
    ],
    hiddenimports=[*sv_ttk_hidden],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='YouTube下載器',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico'
)
