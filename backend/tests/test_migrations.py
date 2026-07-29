import sqlite3
from pathlib import Path

import pytest


def configure_paths(database, tmp_path: Path) -> None:
    database.settings.data_dir = tmp_path
    database.settings.db_path = tmp_path / "stock_helper.db"
    database.settings.assets_dir = tmp_path / "assets"
    database.settings.temp_dir = tmp_path / "temp"
    database.settings.backup_dir = tmp_path / "backups"
    for directory in (
        database.settings.data_dir,
        database.settings.assets_dir,
        database.settings.temp_dir,
        database.settings.backup_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def make_old_v1_database(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE module_drafts (
            module_id INTEGER PRIMARY KEY,
            text_content TEXT NOT NULL DEFAULT '',
            revision INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            combination TEXT NOT NULL,
            combination_name TEXT DEFAULT '',
            analysis_request TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            result_json TEXT,
            raw_result TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at TEXT,
            completed_at TEXT
        );
        CREATE TABLE analysis_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id INTEGER NOT NULL,
            module_id INTEGER NOT NULL,
            order_index INTEGER NOT NULL,
            asset_id INTEGER,
            relative_path TEXT NOT NULL,
            thumbnail_path TEXT
        );
        CREATE TABLE draft_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id INTEGER NOT NULL,
            asset_id INTEGER NOT NULL,
            order_index INTEGER NOT NULL DEFAULT 0,
            caption TEXT DEFAULT ''
        );
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE schema_version (
            version INTEGER PRIMARY KEY,
            description TEXT,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO schema_version(version, description) VALUES (1, 'old');
        INSERT INTO module_drafts(module_id, text_content) VALUES (0, '必须保留的数据');
        INSERT INTO analyses(combination, status) VALUES ('[0]', 'completed');
        INSERT INTO draft_assets(module_id, asset_id, order_index) VALUES (0, 7, 1);
        INSERT INTO draft_assets(module_id, asset_id, order_index) VALUES (0, 7, 2);
        """
    )
    conn.commit()
    conn.close()


def test_fresh_database_is_initialized(tmp_path):
    from app import database

    configure_paths(database, tmp_path)
    backup = database.init_database()
    assert backup is None
    with database.get_db() as conn:
        assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM module_drafts").fetchone()[0] == 12
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_old_database_is_backed_up_migrated_and_preserved(tmp_path):
    from app import database

    configure_paths(database, tmp_path)
    make_old_v1_database(database.settings.db_path)
    backup = database.init_database()

    assert backup is not None and backup.exists()
    with database.get_db() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(analyses)")}
        assert {"saved_to_review", "saved_to_advice", "review_content"} <= columns
        assert "image_order_index" in {
            row[1] for row in conn.execute("PRAGMA table_info(analysis_assets)")
        }
        assert conn.execute(
            "SELECT text_content FROM module_drafts WHERE module_id=0"
        ).fetchone()[0] == "必须保留的数据"
        assert conn.execute("SELECT COUNT(*) FROM draft_assets").fetchone()[0] == 1
        assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 4

    backup_conn = sqlite3.connect(backup)
    try:
        assert backup_conn.execute(
            "SELECT text_content FROM module_drafts WHERE module_id=0"
        ).fetchone()[0] == "必须保留的数据"
    finally:
        backup_conn.close()


def test_false_version_record_is_repaired(tmp_path):
    from app import database

    configure_paths(database, tmp_path)
    make_old_v1_database(database.settings.db_path)
    conn = sqlite3.connect(database.settings.db_path)
    conn.execute("INSERT INTO schema_version(version, description) VALUES (4, '错误标记')")
    conn.commit()
    conn.close()

    backup = database.init_database()
    assert backup is not None
    conn = sqlite3.connect(database.settings.db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(analyses)")}
        assert "review_content" in columns
    finally:
        conn.close()


def test_failed_migration_leaves_live_database_untouched(tmp_path, monkeypatch):
    from app import database

    configure_paths(database, tmp_path)
    database.init_database()
    with database.get_db() as conn:
        conn.execute("UPDATE module_drafts SET text_content='原始数据' WHERE module_id=0")

    original_migrations = database.MIGRATIONS

    def fail(_conn):
        raise sqlite3.OperationalError("forced migration failure")

    monkeypatch.setattr(
        database,
        "MIGRATIONS",
        original_migrations + ((5, "故意失败", fail),),
    )

    with pytest.raises(database.MigrationError):
        database.init_database()

    conn = sqlite3.connect(database.settings.db_path)
    try:
        assert conn.execute(
            "SELECT text_content FROM module_drafts WHERE module_id=0"
        ).fetchone()[0] == "原始数据"
        assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 4
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()
