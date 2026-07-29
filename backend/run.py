"""启动脚本"""
import sys
import webbrowser
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn
from app.config import settings
from app.main import app


def open_browser():
    time.sleep(1.5)
    webbrowser.open(f"http://127.0.0.1:{settings.port}")


if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run(app, host=settings.host, port=settings.port)
