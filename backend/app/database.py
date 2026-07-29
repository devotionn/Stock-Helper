"""数据库连接、初始化与可回退迁移。"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable, Generator

from .config import MODULES, settings

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
    source      TEXT NOT NULL DEFAULT 'user',
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
    module_ids  TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 分析记录表
CREATE TABLE IF NOT EXISTS analyses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    combination     TEXT NOT NULL,
    combination_name TEXT DEFAULT '',
    analysis_request TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending',
    result_json     TEXT,
    raw_result      TEXT,
    error_message   TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    started_at      TEXT,
    completed_at    TEXT,
    saved_to_review INTEGER NOT NULL DEFAULT 0,
    saved_to_advice INTEGER NOT NULL DEFAULT 0,
    review_content TEXT DEFAULT ''
);

-- 分析模块快照表
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

-- 数据库版本记录表
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    description TEXT,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""


class MigrationError(RuntimeError):
    """数据库迁移失败；原数据库保持不变。"""


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=FULL")
    return conn


def get_connection() -> sqlite3.Connection:
    """获取正式数据库连接。"""
    conn = _connect(settings.db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _index_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA index_list({table})").fetchall()}


def _ensure_common_indexes(conn: sqlite3.Connection) -> None:
    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_draft_assets_module ON draft_assets(module_id)",
        "CREATE INDEX IF NOT EXISTS idx_version_assets_version ON version_assets(module_version_id)",
        "CREATE INDEX IF NOT EXISTS idx_analyses_status ON analyses(status)",
        "CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_analysis_snapshots_analysis ON analysis_snapshots(analysis_id)",
        "CREATE INDEX IF NOT EXISTS idx_analysis_assets_analysis ON analysis_assets(analysis_id)",
    )
    for sql in indexes:
        conn.execute(sql)


def _migration_1(_conn: sqlite3.Connection) -> None:
    return


def _migration_2(conn: sqlite3.Connection) -> None:
    columns = _column_names(conn, "analyses")
    statements = {
        "saved_to_review": "ALTER TABLE analyses ADD COLUMN saved_to_review INTEGER NOT NULL DEFAULT 0",
        "saved_to_advice": "ALTER TABLE analyses ADD COLUMN saved_to_advice INTEGER NOT NULL DEFAULT 0",
        "review_content": "ALTER TABLE analyses ADD COLUMN review_content TEXT DEFAULT ''",
    }
    for column, sql in statements.items():
        if column not in columns:
            conn.execute(sql)


def _migration_3(conn: sqlite3.Connection) -> None:
    if "image_order_index" not in _column_names(conn, "analysis_assets"):
        conn.execute(
            "ALTER TABLE analysis_assets ADD COLUMN image_order_index "
            "INTEGER NOT NULL DEFAULT 0"
        )


def _migration_4(conn: sqlite3.Connection) -> None:
    if "idx_draft_assets_unique" in _index_names(conn, "draft_assets"):
        return
    conn.execute(
        "DELETE FROM draft_assets WHERE id NOT IN ("
        "SELECT MIN(id) FROM draft_assets GROUP BY module_id, asset_id)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX idx_draft_assets_unique "
        "ON draft_assets(module_id, asset_id)"
    )


MigrationFn = Callable[[sqlite3.Connection], None]
MIGRATIONS: tuple[tuple[int, str, MigrationFn], ...] = (
    (1, "初始版本", _migration_1),
    (2, "添加分析保存标记和复盘内容", _migration_2),
    (3, "添加图片排序字段", _migration_3),
    (4, "添加草稿图片唯一约束", _migration_4),
)


def target_schema_version() -> int:
    return max(version for version, _description, _migration in MIGRATIONS)


def _current_schema_version(path: Path) -> int:
    if not path.exists() or path.stat().st_size == 0:
        return 0
    conn = _connect(path)
    try:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'"
        ).fetchone()
        if not has_table:
            return 0
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        return int(row[0] or 0)
    finally:
        conn.close()


def _schema_needs_repair(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return True
    conn = _connect(path)
    try:
        required_tables = {
            "module_drafts",
            "analyses",
            "analysis_assets",
            "draft_assets",
            "settings",
            "schema_version",
        }
        actual_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if not required_tables.issubset(actual_tables):
            return True
        required_analysis_columns = {
            "saved_to_review",
            "saved_to_advice",
            "review_content",
        }
        if not required_analysis_columns.issubset(_column_names(conn, "analyses")):
            return True
        if "image_order_index" not in _column_names(conn, "analysis_assets"):
            return True
        return "idx_draft_assets_unique" not in _index_names(conn, "draft_assets")
    finally:
        conn.close()


def _sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    src = _connect(source)
    dst = _connect(destination)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        src.close()
        dst.close()


def _integrity_check(conn: sqlite3.Connection) -> None:
    result = conn.execute("PRAGMA integrity_check").fetchone()
    if not result or result[0] != "ok":
        detail = result[0] if result else "无返回结果"
        raise MigrationError(f"数据库完整性校验失败: {detail}")


def _apply_schema_and_migrations(path: Path, current_version: int) -> None:
    conn = _connect(path)
    try:
        conn.executescript(_SCHEMA)
        conn.execute("BEGIN IMMEDIATE")
        for version, description, migration in MIGRATIONS:
            migration(conn)
            if version > current_version:
                conn.execute(
                    "INSERT OR REPLACE INTO schema_version(version, description) VALUES (?, ?)",
                    (version, description),
                )
        _ensure_common_indexes(conn)
        conn.commit()
        _integrity_check(conn)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _prepare_database() -> Path | None:
    """迁移正式数据库；返回迁移前备份路径。无迁移时返回 None。"""
    db_path = settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    current_version = _current_schema_version(db_path)
    target_version = target_schema_version()
    needs_migration = current_version < target_version or _schema_needs_repair(db_path)
    if not needs_migration:
        conn = _connect(db_path)
        try:
            _integrity_check(conn)
        finally:
            conn.close()
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    migration_dir = settings.backup_dir / "migrations"
    migration_dir.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    candidate_path = db_path.with_name(
        f".{db_path.name}.migrating-{os.getpid()}-{timestamp}"
    )

    try:
        if db_path.exists() and db_path.stat().st_size > 0:
            backup_path = migration_dir / (
                f"stock_helper_pre_migration_v{current_version}_to_v{target_version}_{timestamp}.db"
            )
            _sqlite_backup(db_path, backup_path)
            _sqlite_backup(db_path, candidate_path)
        else:
            candidate_path.touch()

        _apply_schema_and_migrations(candidate_path, current_version)

        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(db_path) + suffix)
            if sidecar.exists():
                sidecar.unlink()
        os.replace(candidate_path, db_path)
        return backup_path
    except Exception as exc:
        if candidate_path.exists():
            candidate_path.unlink()
        backup_note = f"；原数据库备份：{backup_path}" if backup_path else ""
        raise MigrationError(
            f"数据库升级失败，未修改原数据库{backup_note}: {exc}"
        ) from exc


def _seed_defaults() -> None:
    with get_db() as conn:
        for module in MODULES:
            conn.execute(
                "INSERT OR IGNORE INTO module_drafts(module_id, text_content) VALUES (?, '')",
                (module["id"],),
            )

        defaults = {
            "ai_api_url": "",
            "ai_model": "",
            "backup_location": str(settings.backup_dir),
            "font_size": "18",
        }
        for key, value in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                (key, value),
            )

        row = conn.execute(
            "SELECT value FROM settings WHERE key='ai_api_key'"
        ).fetchone()
        if row and row["value"]:
            try:
                from .services.secret_store import get_secret_store

                store = get_secret_store()
                if not store.has_secret("ai_api_key"):
                    store.set_secret("ai_api_key", row["value"])
                if store.get_secret("ai_api_key"):
                    conn.execute("DELETE FROM settings WHERE key='ai_api_key'")
                    print("[迁移] AI密钥已从数据库迁移到系统安全存储")
            except Exception as exc:
                print(f"[迁移] AI密钥安全迁移暂未完成: {exc}")


def init_database() -> Path | None:
    """初始化数据库并执行带备份、原子替换和完整性校验的迁移。"""
    migration_backup = _prepare_database()
    _seed_defaults()
    return migration_backup
