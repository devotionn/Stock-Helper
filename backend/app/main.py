"""FastAPI 主应用。"""
from __future__ import annotations

import os
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.database import get_db, init_database
from app.routers import analysis, backup, combinations, history, modules, sys_settings, workspaces
from app.time_dimension import init_time_dimension


def get_frontend_dist() -> Path:
    """获取前端构建产物路径，支持 PyInstaller 打包环境。"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "frontend" / "dist"
    return settings.base_dir.parent / "frontend" / "dist"


FRONTEND_DIST = get_frontend_dist()
SESSION_TOKEN = secrets.token_urlsafe(32)
INSTANCE_ID = secrets.token_urlsafe(16)
ALLOWED_HOSTS = {f"127.0.0.1:{settings.port}", f"localhost:{settings.port}"}
DEV_ORIGINS = {"http://127.0.0.1:5173", "http://localhost:5173"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    migration_backup = init_database()
    if migration_backup:
        print(f"[数据库] 升级完成，升级前备份：{migration_backup}")
    migrated_date = init_time_dimension()
    if migrated_date:
        print(f"[数据库] 旧版模块数据已迁移到投研日期：{migrated_date}")

    with get_db() as conn:
        conn.execute(
            "UPDATE analyses SET status='interrupted', error_message='应用重启时被中断' "
            "WHERE status IN ('pending', 'running')"
        )
    yield


app = FastAPI(
    title="股票分析助手 API",
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(DEV_ORIGINS),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Session-Token"],
)


@app.middleware("http")
async def security_check(request: Request, call_next):
    """API Host 与本地会话校验，防止 DNS rebinding 与跨站调用。"""
    path = request.url.path
    if path.startswith("/api/"):
        host = request.headers.get("host", "")
        if host not in ALLOWED_HOSTS:
            return JSONResponse(status_code=403, content={"detail": "Forbidden host"})

        if path in ("/api/session", "/api/health"):
            return await call_next(request)

        origin = request.headers.get("origin", "")
        if origin not in DEV_ORIGINS:
            token = request.headers.get("x-session-token", "")
            if not secrets.compare_digest(token, SESSION_TOKEN):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid session token"},
                )
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path == "/api/session":
        response.headers["Cache-Control"] = "no-store"
    return response


app.mount("/uploads", StaticFiles(directory=str(settings.assets_dir)), name="uploads")
app.include_router(workspaces.router, prefix="/api/workspaces", tags=["投研日期工作区"])
app.include_router(modules.router, prefix="/api/modules", tags=["模块（兼容旧版）"])
app.include_router(combinations.router, prefix="/api/combinations", tags=["常用组合"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["组合分析"])
app.include_router(history.router, prefix="/api/history", tags=["历史记录"])
app.include_router(sys_settings.router, prefix="/api/settings", tags=["系统设置"])
app.include_router(backup.router, prefix="/api/backup", tags=["备份恢复"])


@app.get("/api/session")
def get_session():
    return {"token": SESSION_TOKEN}


@app.get("/api/health")
def health_check():
    """无敏感信息的本地身份与健康检查，供启动器和冒烟测试使用。"""
    return {
        "status": "ok",
        "app": "stock-helper",
        "version": settings.app_version,
        "instance_id": INSTANCE_ID,
        "pid": os.getpid(),
    }


if FRONTEND_DIST.exists():

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str, _request: Request):
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        index_path = FRONTEND_DIST / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"error": "前端文件未找到，请先构建前端（cd frontend && npm run build）"}
