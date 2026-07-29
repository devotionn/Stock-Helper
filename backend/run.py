"""股票分析助手后端启动入口。"""
from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn

from app.config import settings
from app.main import app


def _should_open_browser() -> bool:
    """源码独立运行时可自动开浏览器；打包版由 Swift 启动器统一负责。"""
    if getattr(sys, "frozen", False):
        return False
    return os.environ.get("STOCK_OPEN_BROWSER", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _open_browser() -> None:
    time.sleep(1.5)
    webbrowser.open(f"http://127.0.0.1:{settings.port}")


if __name__ == "__main__":
    if _should_open_browser():
        threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(app, host=settings.host, port=settings.port)
