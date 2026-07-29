"""按投研日期组织 12 个模块的数据结构与兼容迁移。"""
from __future__ import annotations

from datetime import date
import sqlite3

from .config import MODULES
from .database import get_db

TIME_SCHEMA_VERSION = 5

_TIME_SCHEMA = """
CREATE TABLE IF NOT EXISTS module_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    record_date     TEXT NOT NULL,
    module_id       INTEGER NOT NULL,
    display_title   TEXT NOT NULL DEFAULT '',
    text_content    TEXT NOT NULL DEFAULT '',
    revision        INTEGER NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'draft',
    period_start    TEXT,
    period_end      TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE(record_date, module_id)
);

CREATE TABLE IF NOT EXISTS entry_assets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    module_entry_id INTEGER NOT NULL,
    asset_id        INTEGER NOT NULL,
    order_index     INTEGER NOT NULL DEFAULT 0,
    caption         TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (module_entry_id) REFERENCES module_entries(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
    UNIQUE(module_entry_id, asset_id)
);

CREATE INDEX IF NOT EXISTS idx_module_entries_date
ON module_entries(record_date, module_id);
CREATE INDEX IF NOT EXISTS idx_entry_assets_entry
ON entry_assets(module_entry_id, order_index);
"""


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    ddl: str,
) -> None:
    if column not in _column_names(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def _legacy_workspace_date(conn: sqlite3.Connection) -> str:
    stored = conn.execute(
        "SELECT value FROM settings WHERE key='active_record_date'"
    ).fetchone()
    if stored and stored["value"]:
        return stored["value"]

    row = conn.execute(
        "SELECT MAX(date(updated_at)) AS d FROM module_drafts"
    ).fetchone()
    return (row["d"] if row and row["d"] else None) or date.today().isoformat()


def _migrate_legacy_workspace(conn: sqlite3.Connection) -> str | None:
    migrated = conn.execute(
        "SELECT value FROM settings WHERE key='time_dimension_migrated'"
    ).fetchone()
    if migrated and migrated["value"] == "1":
        return None

    workspace_date = _legacy_workspace_date(conn)
    existing_count = conn.execute(
        "SELECT COUNT(*) FROM module_entries"
    ).fetchone()[0]

    if existing_count == 0:
        for module in MODULES:
            legacy = conn.execute(
                "SELECT text_content, revision, updated_at FROM module_drafts WHERE module_id=?",
                (module["id"],),
            ).fetchone()
            text_content = legacy["text_content"] if legacy else ""
            revision = int(legacy["revision"] if legacy else 1)
            updated_at = legacy["updated_at"] if legacy else None
            conn.execute(
                "INSERT INTO module_entries "
                "(record_date, module_id, text_content, revision, updated_at) "
                "VALUES (?, ?, ?, ?, COALESCE(?, datetime('now','localtime')))",
                (workspace_date, module["id"], text_content, revision, updated_at),
            )

        conn.execute(
            "INSERT OR IGNORE INTO entry_assets "
            "(module_entry_id, asset_id, order_index, caption) "
            "SELECT e.id, da.asset_id, da.order_index, COALESCE(da.caption, '') "
            "FROM draft_assets da "
            "JOIN module_entries e ON e.record_date=? AND e.module_id=da.module_id",
            (workspace_date,),
        )

    conn.execute(
        "INSERT INTO settings(key, value, updated_at) VALUES "
        "('active_record_date', ?, datetime('now','localtime')) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (workspace_date,),
    )
    conn.execute(
        "INSERT INTO settings(key, value, updated_at) VALUES "
        "('time_dimension_migrated', '1', datetime('now','localtime')) "
        "ON CONFLICT(key) DO UPDATE SET value='1', updated_at=excluded.updated_at"
    )
    return workspace_date


def init_time_dimension() -> str | None:
    """创建时间维度结构，将旧版单工作区安全迁移到一个投研日期。"""
    with get_db() as conn:
        conn.executescript(_TIME_SCHEMA)

        _add_column_if_missing(
            conn, "analyses", "record_date", "record_date TEXT"
        )
        _add_column_if_missing(
            conn,
            "analysis_snapshots",
            "display_title",
            "display_title TEXT NOT NULL DEFAULT ''",
        )
        _add_column_if_missing(
            conn, "module_versions", "record_date", "record_date TEXT"
        )
        _add_column_if_missing(
            conn,
            "module_versions",
            "display_title",
            "display_title TEXT NOT NULL DEFAULT ''",
        )
        _add_column_if_missing(
            conn, "module_versions", "module_entry_id", "module_entry_id INTEGER"
        )

        legacy_date = _migrate_legacy_workspace(conn)
        conn.execute(
            "UPDATE analyses SET record_date=COALESCE(record_date, date(created_at))"
        )
        conn.execute(
            "UPDATE module_versions SET record_date=COALESCE(record_date, date(created_at))"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_analyses_record_date ON analyses(record_date)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_versions_record_date "
            "ON module_versions(record_date, module_id)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_version(version, description) VALUES (?, ?)",
            (TIME_SCHEMA_VERSION, "增加投研日期工作区、日历与日期快照"),
        )
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise RuntimeError(f"时间维度迁移后数据库校验失败: {integrity}")
        return legacy_date
