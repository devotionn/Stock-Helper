"""数据库连接与初始化"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from .config import settings, MODULES

_SCHEMA = """
-- 模块草稿表（当前编辑中的内容）
CREATE TABLE IF NOT EXISTS module_drafts (
    module_id   INTEGER PRIMARY KEY,
    text_content TEXT NOT NULL DEFAULT '',
    revision    INTEGER NOT NULL DEFAULT 1,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 模块版本表（明确保存的快照）
CREATE TABLE IF NOT EXISTS module_versions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    module_id   INTEGER NOT NULL,
    text_content TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'user',  -- user / ai_review / ai_advice
    note        TEXT DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (module_id) REFERENCES module_drafts(module_id)
);

-- 图片资源表
CREATE TABLE IF NOT EXISTS assets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256          TEXT NOT NULL UNIQUE,
    original_filename TEXT,
    relative_path   TEXT NOT NULL,
    thumbnail_path  TEXT,
    file_size       INTEGER NOT NULL,
    width           INTEGER,
    height          INTEGER,
    mime_type       TEXT,
    format          TEXT,
    is_orphan       INTEGER NOT NULL DEFAULT 0,
    orphan_since    TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 草稿图片关联表
CREATE TABLE IF NOT EXISTS draft_assets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    module_id   INTEGER NOT NULL,
    asset_id    INTEGER NOT NULL,
    order_index INTEGER NOT NULL DEFAULT 0,
    caption     TEXT DEFAULT '',
    FOREIGN KEY (module_id) REFERENCES module_drafts(module_id),
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
    UNIQUE(module_id, asset_id)
);

-- 版本图片关联表
CREATE TABLE IF NOT EXISTS version_assets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    module_version_id INTEGER NOT NULL,
    asset_id        INTEGER NOT NULL,
    order_index     INTEGER NOT NULL DEFAULT 0,
    caption         TEXT DEFAULT '',
    FOREIGN KEY (module_version_id) REFERENCES module_versions(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

-- 常用组合表
CREATE TABLE IF NOT EXISTS combinations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    module_ids  TEXT NOT NULL,  -- JSON数组，如 "[0,1,7,8]"
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 分析记录表
CREATE TABLE IF NOT EXISTS analyses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    combination     TEXT NOT NULL,      -- JSON数组，模块ID顺序
    combination_name TEXT DEFAULT '',   -- 组合名称（如有）
    analysis_request TEXT DEFAULT '',   -- 用户填写的分析要求
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending/running/completed/failed/interrupted
    result_json     TEXT,               -- 结构化结果JSON
    raw_result      TEXT,               -- AI原始返回
    error_message   TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    started_at      TEXT,
    completed_at    TEXT,
    saved_to_review INTEGER NOT NULL DEFAULT 0,   -- 是否已保存到AI复盘(9号)
    saved_to_advice INTEGER NOT NULL DEFAULT 0,   -- 是否已保存到操作建议(11号)
    review_content TEXT DEFAULT ''                -- 后续复盘内容
);

-- 分析模块快照表（分析时各模块的内容快照）
CREATE TABLE IF NOT EXISTS analysis_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL,
    module_id   INTEGER NOT NULL,
    order_index INTEGER NOT NULL,
    module_name TEXT NOT NULL,
    text_content TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);

-- 分析图片快照表
CREATE TABLE IF NOT EXISTS analysis_assets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL,
    module_id   INTEGER NOT NULL,
    order_index INTEGER NOT NULL,
    image_order_index INTEGER NOT NULL DEFAULT 0,
    asset_id    INTEGER,
    relative_path TEXT NOT NULL,
    thumbnail_path TEXT,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);

-- 历史备注表
CREATE TABLE IF NOT EXISTS analysis_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL,
    note        TEXT DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);

-- 系统设置表
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 备份记录表
CREATE TABLE IF NOT EXISTS backup_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_path TEXT NOT NULL,
    file_count  INTEGER,
    total_size  INTEGER,
    status      TEXT NOT NULL DEFAULT 'success',
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 数据库版本记录表（用于增量迁移）
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    description TEXT,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_draft_assets_module ON draft_assets(module_id);
CREATE INDEX IF NOT EXISTS idx_version_assets_version ON version_assets(module_version_id);
CREATE INDEX IF NOT EXISTS idx_analyses_status ON analyses(status);
CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at);
CREATE INDEX IF NOT EXISTS idx_analysis_snapshots_analysis ON analysis_snapshots(analysis_id);
CREATE INDEX IF NOT EXISTS idx_analysis_assets_analysis ON analysis_assets(analysis_id);
"""


def get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(
        str(settings.db_path),
        timeout=10,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=FULL")
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """数据库连接上下文管理器"""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


MIGRATIONS = [
    (1, "初始版本", []),
    (2, "添加分析保存标记和复盘内容", [
        "ALTER TABLE analyses ADD COLUMN saved_to_review INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE analyses ADD COLUMN saved_to_advice INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE analyses ADD COLUMN review_content TEXT DEFAULT ''",
    ]),
    (3, "添加图片排序字段", [
        "ALTER TABLE analysis_assets ADD COLUMN image_order_index INTEGER NOT NULL DEFAULT 0",
    ]),
    (4, "添加草稿图片唯一约束", [
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_draft_assets_unique ON draft_assets(module_id, asset_id)",
    ]),
]


def init_database():
    """初始化数据库：建表 + 迁移 + 插入12个模块草稿"""
    with get_db() as conn:
        conn.executescript(_SCHEMA)
        # 执行增量迁移（基于 schema_version 表）
        current_version = conn.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()[0] or 0
        for version, desc, sqls in MIGRATIONS:
            if version > current_version:
                for sql in sqls:
                    try:
                        conn.execute(sql)
                    except sqlite3.OperationalError:
                        pass  # 字段已存在
                conn.execute(
                    "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                    (version, desc),
                )
        # 初始化12个模块草稿行
        for m in MODULES:
            conn.execute(
                "INSERT OR IGNORE INTO module_drafts (module_id, text_content) VALUES (?, '')",
                (m["id"],),
            )
        # 初始化默认设置
        defaults = {
            "ai_api_url": "",
            "ai_api_key": "",
            "ai_model": "",
            "backup_location": str(settings.backup_dir),
            "font_size": "18",
        }
        for k, v in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (k, v),
            )
