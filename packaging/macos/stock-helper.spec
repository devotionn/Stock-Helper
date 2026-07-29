# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Stock Helper backend (macOS arm64)"""

import sys
from pathlib import Path

block_cipher = None

# 后端代码目录
backend_dir = str(Path(__file__).resolve().parent.parent.parent / 'backend')
# 前端构建产物
frontend_dist = str(Path(__file__).resolve().parent.parent.parent / 'frontend' / 'dist')

a = Analysis(
    [backend_dir + '/run.py'],
    pathex=[backend_dir],
    binaries=[],
    datas=[
        (frontend_dist, 'frontend/dist'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'PIL._tkinter_finder',
    ],
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
    [],
    exclude_binaries=True,
    name='stock-helper-server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='arm64',
    codesign_identity=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='stock-helper-server',
)
