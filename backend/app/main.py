"""FastAPI 主应用"""
import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

# 确保能导入 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import init_database
from app.config import settings
from app.routers import modules, analysis, history, combinations, sys_settings, backup

# 前端构建产物目录
FRONTEND_DIST = settings.base_dir.parent / "frontend" / "dist"


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
