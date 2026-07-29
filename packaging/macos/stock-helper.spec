# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Stock Helper backend (macOS arm64)."""

from pathlib import Path

block_cipher = None

# build_app.sh 始终从仓库根目录调用 PyInstaller；spec 执行环境不保证定义 __file__。
project_root = Path.cwd().resolve()
backend_dir = project_root / "backend"
frontend_dist = project_root / "frontend" / "dist"

if not (backend_dir / "run.py").is_file():
    raise SystemExit(f"找不到后端入口: {backend_dir / 'run.py'}")
if not (frontend_dist / "index.html").is_file():
    raise SystemExit(f"找不到前端构建产物: {frontend_dist}")

a = Analysis(
    [str(backend_dir / "run.py")],
    pathex=[str(backend_dir)],
    binaries=[],
    datas=[(str(frontend_dist), "frontend/dist")],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "PIL._tkinter_finder",
        "app.main",
        "app.config",
        "app.database",
        "app.schemas",
        "app.routers.modules",
        "app.routers.analysis",
        "app.routers.combinations",
        "app.routers.history",
        "app.routers.sys_settings",
        "app.routers.backup",
        "app.services.ai",
        "app.services.image",
        "app.services.secret_store",
        "keyring.backends.macOS",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="stock-helper-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="arm64",
    codesign_identity=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="stock-helper-server",
)
