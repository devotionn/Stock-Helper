"""备份恢复测试。"""
import io
import json
import sqlite3
import zipfile
from pathlib import Path


def test_create_backup_contains_time_dimension(client, tmp_path):
    response = client.post("/api/backup")
    assert response.status_code == 200
    data = response.json()
    backup_path = Path(data["path"])
    assert backup_path.exists()
    assert data["file_count"] >= 1

    with zipfile.ZipFile(backup_path, "r") as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["schema_version"] >= 5
        assert manifest["contains_time_dimension"] is True
        extracted_db = tmp_path / "backup.db"
        extracted_db.write_bytes(archive.read("database.db"))

    conn = sqlite3.connect(str(extracted_db))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {"module_entries", "entry_assets"}.issubset(tables)
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def test_list_backups(client):
    response = client.post("/api/backup")
    assert response.status_code == 200, f"备份创建失败: {response.text}"
    response = client.get("/api/backup")
    assert response.status_code == 200
    assert len(response.json()) >= 1


def test_restore_with_bad_zip(client):
    fake_zip = io.BytesIO(b"not a zip file")
    response = client.post(
        "/api/backup/restore",
        files={"file": ("test.shbackup", fake_zip, "application/octet-stream")},
    )
    assert response.status_code in [400, 500]
