"""FastAPI 主应用"""
import os
import sys
import secrets
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager

# 确保能导入 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import init_database
from app.config import settings
from app.routers import modules, analysis, history, combinations, sys_settings, backup

def get_frontend_dist() -> Path:
    """获取前端构建产物路径，支持 PyInstaller 打包环境"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后，资源在 _MEIPASS 中
        return Path(sys._MEIPASS) / "frontend" / "dist"
    else:
        # 开发环境
        return settings.base_dir.parent / "frontend" / "dist"


# 前端构建产物目录
FRONTEND_DIST = get_frontend_dist()

# 本地会话令牌：应用启动时生成，前端首次加载通过 /api/session 获取
SESSION_TOKEN = secrets.token_urlsafe(32)
# 允许的 Host（防 DNS rebinding），由本地监听地址和端口构成
ALLOWED_HOSTS = {f"127.0.0.1:{settings.port}", f"localhost:{settings.port}"}
# 开发环境允许的来源（这些来源不强制会话令牌，方便调试）
DEV_ORIGINS = {"http://127.0.0.1:5173", "http://localhost:5173"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    # 启动时将未完成的分析标记为中断
    from app.database import get_db
    with get_db() as conn:
        conn.execute(
            "UPDATE analyses SET status='interrupted', error_message='应用重启时被中断' "
            "WHERE status IN ('pending', 'running')"
        )
    yield


app = FastAPI(
    title="股票分析助手 API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - 开发环境只允许前端dev server访问；生产环境同源不需要CORS
# （生产模式 Host=127.0.0.1:8765 时前端与API同源，浏览器不会发起跨域请求）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_check(request: Request, call_next):
    """对 /api/ 路径进行 Host 校验（防 DNS rebinding）和会话令牌校验"""
    path = request.url.path
    if path.startswith("/api/"):
        # Host 校验：拒绝非本地 Host，防止 DNS rebinding 攻击
        host = request.headers.get("host", "")
        if host not in ALLOWED_HOSTS:
            return JSONResponse(status_code=403, content={"detail": "Forbidden host"})
        # /api/session 是获取令牌的入口，无需校验令牌
        if path in ("/api/session", "/api/health"):
            return await call_next(request)
        # 开发环境（来自 dev server 的请求）不强制令牌，方便调试
        origin = request.headers.get("origin", "")
        if origin not in DEV_ORIGINS:
            token = request.headers.get("x-session-token", "")
            if token != SESSION_TOKEN:
                return JSONResponse(status_code=401, content={"detail": "Invalid session token"})
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """添加安全响应头：所有环境均生效"""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response

# 静态文件：图片访问
app.mount("/uploads", StaticFiles(directory=str(settings.assets_dir)), name="uploads")

# 注册路由
app.include_router(modules.router, prefix="/api/modules", tags=["模块"])
app.include_router(combinations.router, prefix="/api/combinations", tags=["常用组合"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["组合分析"])
app.include_router(history.router, prefix="/api/history", tags=["历史记录"])
app.include_router(sys_settings.router, prefix="/api/settings", tags=["系统设置"])
app.include_router(backup.router, prefix="/api/backup", tags=["备份恢复"])


@app.get("/api/session")
def get_session():
    """返回本地会话令牌（无需令牌即可访问，供前端首次获取）"""
    return {"token": SESSION_TOKEN}


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


# ---- 前端静态文件服务（生产模式）----
if FRONTEND_DIST.exists():
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str, request: Request):
        """SPA 回退：所有非 API 路由返回 index.html"""
        # 如果请求的是静态资源文件，直接返回
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        # 否则返回 index.html（Vue Router history 模式回退）
        index_path = FRONTEND_DIST / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"error": "前端文件未找到，请先构建前端（cd frontend && npm run build）"}
