import pytest
import sys
import os
from pathlib import Path

# 在任何 app 模块导入前设置环境变量
_TEST_DATA_DIR = str(Path(__file__).resolve().parent / 'test_data')
os.environ['STOCK_DATA_DIR'] = _TEST_DATA_DIR

# 确保能导入 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def client():
    """测试用FastAPI客户端，自动携带安全头"""
    from fastapi.testclient import TestClient
    from app.main import app, SESSION_TOKEN
    from app.database import init_database
    from app.config import settings

    # 确保测试数据目录存在（前一个测试可能删除了它）
    Path(_TEST_DATA_DIR).mkdir(parents=True, exist_ok=True)

    # 删除旧数据库文件，确保每个测试都是干净的
    for suffix in ['', '-wal', '-shm']:
        p = Path(_TEST_DATA_DIR) / f'stock_helper.db{suffix}'
        if p.exists():
            p.unlink()

    # 重新派生 settings 路径（防止前一个测试清理后路径失效）
    settings.data_dir = Path(_TEST_DATA_DIR)
    settings.db_path = Path(_TEST_DATA_DIR) / 'stock_helper.db'
    settings.assets_dir = Path(_TEST_DATA_DIR) / 'assets'
    settings.temp_dir = Path(_TEST_DATA_DIR) / 'temp'
    settings.backup_dir = Path(_TEST_DATA_DIR) / 'backups'
    for d in [settings.data_dir, settings.assets_dir, settings.temp_dir, settings.backup_dir]:
        d.mkdir(parents=True, exist_ok=True)

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

    # 清理数据库文件（不删除整个目录，防止后续测试路径失效）
    for suffix in ['', '-wal', '-shm']:
        p = Path(_TEST_DATA_DIR) / f'stock_helper.db{suffix}'
        if p.exists():
            p.unlink()


@pytest.fixture(scope="session", autouse=True)
def cleanup():
    """会话结束后清理测试数据目录"""
    yield
    import shutil
    test_data = Path(_TEST_DATA_DIR)
    if test_data.exists():
        shutil.rmtree(test_data, ignore_errors=True)
