"""应用配置"""
import os
import sys
from pathlib import Path
from pydantic import model_validator
from pydantic_settings import BaseSettings


def _get_data_dir() -> Path:
    """根据操作系统选择数据目录。可通过 STOCK_DATA_DIR 环境变量覆盖（开发时用）。"""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Stock Helper"
    elif sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return Path(local) / "Stock Helper"
    else:
        return Path.home() / ".local" / "share" / "stock-helper"


class Settings(BaseSettings):
    # 基础路径
    base_dir: Path = Path(__file__).resolve().parent.parent  # 后端代码目录，用于找前端 dist 等
    data_dir: Path = _get_data_dir()
    db_path: Path = data_dir / "stock_helper.db"
    assets_dir: Path = data_dir / "assets"
    temp_dir: Path = data_dir / "temp"
    backup_dir: Path = data_dir / "backups"

    @model_validator(mode="after")
    def _rederive_paths(self):
        """当 STOCK_DATA_DIR 覆盖 data_dir 后，重新派生子路径，保证一致"""
        self.db_path = self.data_dir / "stock_helper.db"
        self.assets_dir = self.data_dir / "assets"
        self.temp_dir = self.data_dir / "temp"
        self.backup_dir = self.data_dir / "backups"
        return self

    # 服务器配置
    host: str = "127.0.0.1"
    port: int = 8765

    # 图片限制
    max_image_size: int = 20 * 1024 * 1024  # 20MB
    max_image_dimension: int = 8000  # 最大像素边长
    max_total_pixels: int = 50_000_000  # 总像素上限
    thumbnail_size: int = 300
    allowed_image_types: list = ["jpeg", "png", "webp", "gif", "bmp"]

    # AI 配置
    ai_api_url: str = ""
    ai_api_key: str = ""
    ai_model: str = ""
    ai_timeout: int = 120  # 秒
    ai_max_retries: int = 1
    ai_max_images: int = 16
    ai_image_max_long_edge: int = 2048
    ai_image_quality: int = 85

    # 备份配置
    max_auto_backups: int = 10

    class Config:
        env_file = ".env"
        env_prefix = "STOCK_"


settings = Settings()

# 确保目录存在
for d in [settings.data_dir, settings.assets_dir, settings.temp_dir, settings.backup_dir]:
    d.mkdir(parents=True, exist_ok=True)

# 12个模块定义
MODULES = [
    {"id": 0, "name": "一周策略", "desc": "本周整体操作思路、仓位安排、重点关注方向"},
    {"id": 1, "name": "股票1", "desc": "第一只关注股票的相关资料"},
    {"id": 2, "name": "股票2", "desc": "第二只关注股票的相关资料"},
    {"id": 3, "name": "股票3", "desc": "第三只关注股票的相关资料"},
    {"id": 4, "name": "股票4", "desc": "第四只关注股票的相关资料"},
    {"id": 5, "name": "技术派观点", "desc": "技术分析相关观点、指标解读、图形分析"},
    {"id": 6, "name": "钱说观点", "desc": "特定信息来源的观点记录"},
    {"id": 7, "name": "大盘走势", "desc": "大盘指数走势、宏观市场情况"},
    {"id": 8, "name": "反向操作", "desc": "反向思维、风险提示、对立观点"},
    {"id": 9, "name": "AI复盘", "desc": "保存历史分析后的复盘内容"},
    {"id": 10, "name": "行业板块", "desc": "行业和板块相关资料"},
    {"id": 11, "name": "操作建议", "desc": "保存AI生成或客户修改后的操作参考"},
]
