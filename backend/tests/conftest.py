import pytest
import sys
import os
from pathlib import Path

# 确保能导入 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

@pytest.fixture
def client():
    """测试用FastAPI客户端，自动携带安全头"""
    from fastapi.testclient import TestClient
    from app.main import app, SESSION_TOKEN

    # 使用临时数据库
    os.environ['STOCK_DATA_DIR'] = str(Path(__file__).resolve().parent / 'test_data')
    from app.database import init_database
    init_database()

    # 配置测试客户端的安全头：Host 校验 + 会话令牌
    with TestClient(
        app,
        headers={
            "Host": "127.0.0.1:8765",
            "X-Session-Token": SESSION_TOKEN,
        },
    ) as c:
        yield c

    # 清理
    import shutil
    test_data = Path(__file__).resolve().parent / 'test_data'
    if test_data.exists():
        shutil.rmtree(test_data, ignore_errors=True)
