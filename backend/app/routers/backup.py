"""数据备份与恢复 API。"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..config import settings
from ..database import get_connection, get_db, init_database
from ..schemas import BackupResult
from ..time_dimension import TIME_SCHEMA_VERSION, init_time_dimension

APP_VERSION = os.environ.get("STOCK_APP_VERSION", "1.0.0")
_restore_lock = threading.Lock()
router = APIRouter()

MAX_TOTAL_SIZE = 2 * 1024 * 1024 * 1024
MAX_FILE_COUNT = 100000
MAX_SINGLE_FILE_SIZE = 100 * 1024 * 1024


def _get_backup_location() -> Path:
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key='backup_location'"
        ).fetchone()
        if row and row["value"]:
            return Path(row["value"])
    return settings.backup_dir


def _database_schema_version(path: Path | None = None) -> int:
    if path is None:
        with get_db() as conn:
            row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
            return int(row[0] or 0)
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        return int(row[0] or 0)
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def _validate_restored_database(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise RuntimeError(f"数据库完整性校验失败: {integrity[0] if integrity else '无结果'}")
        required_tables = {
            "module_drafts",
            "module_entries",
            "entry_assets",
            "analyses",
            "schema_version",
        }
        actual_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = required_tables - actual_tables
        if missing:
            raise RuntimeError(f"恢复后缺少必要数据表: {sorted(missing)}")
        conn.execute("SELECT COUNT(*) FROM module_entries").fetchone()
    finally:
        conn.close()


@router.post("", response_model=BackupResult)
def create_backup():
    """一键备份数据库、图片、历史、组合及所有投研日期数据。"""
    backup_dir = _get_backup_location()
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"stock_helper_backup_{timestamp}"
    backup_path = backup_dir / f"{backup_name}.shbackup"
    temp_path = backup_dir / f"{backup_name}.tmp"
    temp_db = backup_dir / f"{backup_name}_temp.db"
    file_count = 0
    total_size = 0

    try:
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as archive:
            destination = sqlite3.connect(str(temp_db))
            source = get_connection()
            try:
                source.backup(destination)
            finally:
                source.close()
                destination.close()
            archive.write(temp_db, "database.db")
            file_count += 1
            total_size += temp_db.stat().st_size
            temp_db.unlink()

            if settings.assets_dir.exists():
                for root, _dirs, files in os.walk(settings.assets_dir):
                    for filename in files:
                        absolute_path = Path(root) / filename
                        relative_path = absolute_path.relative_to(settings.assets_dir)
                        archive.write(absolute_path, f"assets/{relative_path}")
                        file_count += 1
                        total_size += absolute_path.stat().st_size

            manifest = {
                "app_version": APP_VERSION,
                "schema_version": _database_schema_version(),
                "created_at": datetime.now().isoformat(),
                "file_count": file_count,
                "total_size": total_size,
                "contains_time_dimension": True,
            }
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )

        os.replace(str(temp_path), str(backup_path))
        with get_db() as conn:
            conn.execute(
                "INSERT INTO backup_runs (backup_path, file_count, total_size, status) "
                "VALUES (?, ?, ?, 'success')",
                (str(backup_path), file_count, total_size),
            )
        return BackupResult(
            success=True,
            path=str(backup_path),
            file_count=file_count,
            total_size=total_size,
            message=(
                f"备份成功，共 {file_count} 个文件，"
                f"大小 {total_size / 1024 / 1024:.1f}MB"
            ),
        )
    except Exception as exc:
        for path in (temp_path, temp_db):
            if path.exists():
                path.unlink()
        raise HTTPException(status_code=500, detail=f"备份失败: {exc}") from exc


@router.get("", response_model=list)
def list_backups():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM backup_runs ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    return [
        {
            "id": row["id"],
            "backup_path": row["backup_path"],
            "file_count": row["file_count"],
            "total_size": row["total_size"],
            "status": row["status"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


@router.post("/restore")
async def restore_backup(file: UploadFile = File(...)):
    """恢复备份；校验版本、完整性并在失败时恢复数据库和图片。"""
    if not _restore_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="正在执行恢复操作，请等待")

    restore_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    temp_zip = settings.temp_dir / f"restore_{restore_id}.zip"
    extract_dir = settings.temp_dir / f"restore_extract_{restore_id}"
    assets_rollback_dir = settings.temp_dir / f"assets_rollback_{restore_id}"
    db_rollback_path = settings.temp_dir / f"db_rollback_{restore_id}.db"

    try:
        if not (file.filename or "").endswith(".shbackup"):
            raise HTTPException(status_code=400, detail="请上传 .shbackup 备份文件")

        content = await file.read()
        if len(content) > MAX_TOTAL_SIZE:
            raise HTTPException(status_code=400, detail="备份文件过大")
        temp_zip.write_bytes(content)

        with zipfile.ZipFile(temp_zip, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if "manifest.json" not in names or "database.db" not in names:
                raise HTTPException(status_code=400, detail="无效的备份文件")
            if len(infos) > MAX_FILE_COUNT:
                raise HTTPException(status_code=400, detail="备份文件数量过多")
            if sum(info.file_size for info in infos) > MAX_TOTAL_SIZE:
                raise HTTPException(status_code=400, detail="备份解压后体积过大")
            for info in infos:
                path = Path(info.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise HTTPException(status_code=400, detail="备份文件包含不安全路径")
                if info.file_size > MAX_SINGLE_FILE_SIZE:
                    raise HTTPException(
                        status_code=400,
                        detail=f"文件过大: {info.filename}",
                    )

            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            if not isinstance(manifest, dict) or "schema_version" not in manifest:
                raise HTTPException(status_code=400, detail="manifest.json 格式无效")
            backup_schema = int(manifest.get("schema_version") or 0)
            if backup_schema > TIME_SCHEMA_VERSION:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"备份数据版本 {backup_schema} 高于当前程序支持版本 "
                        f"{TIME_SCHEMA_VERSION}，请先升级应用"
                    ),
                )

            extract_dir.mkdir(parents=True, exist_ok=False)
            archive.extractall(extract_dir)

        backup_db_path = extract_dir / "database.db"
        integrity_conn = sqlite3.connect(str(backup_db_path))
        try:
            integrity = integrity_conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            integrity_conn.close()
        if not integrity or integrity[0] != "ok":
            raise HTTPException(
                status_code=400,
                detail=f"备份数据库完整性校验失败: {integrity[0] if integrity else '无结果'}",
            )

        pre_restore_backup = create_backup()

        if assets_rollback_dir.exists():
            shutil.rmtree(assets_rollback_dir, ignore_errors=True)
        if settings.assets_dir.exists():
            shutil.move(str(settings.assets_dir), str(assets_rollback_dir))
        settings.assets_dir.mkdir(parents=True, exist_ok=True)

        try:
            backup_assets_dir = extract_dir / "assets"
            if backup_assets_dir.exists():
                shutil.copytree(
                    str(backup_assets_dir),
                    str(settings.assets_dir),
                    dirs_exist_ok=True,
                )

            if db_rollback_path.exists():
                db_rollback_path.unlink()
            if settings.db_path.exists():
                shutil.move(str(settings.db_path), str(db_rollback_path))

            shutil.copy2(backup_db_path, settings.db_path)
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(settings.db_path) + suffix)
                if sidecar.exists():
                    sidecar.unlink()

            init_database()
            init_time_dimension()
            _validate_restored_database(settings.db_path)
        except Exception as exc:
            if db_rollback_path.exists():
                if settings.db_path.exists():
                    settings.db_path.unlink()
                shutil.move(str(db_rollback_path), str(settings.db_path))
            if assets_rollback_dir.exists():
                if settings.assets_dir.exists():
                    shutil.rmtree(settings.assets_dir, ignore_errors=True)
                shutil.move(str(assets_rollback_dir), str(settings.assets_dir))
            try:
                init_database()
                init_time_dimension()
            except Exception:
                pass
            raise HTTPException(
                status_code=500,
                detail=f"恢复失败，已回滚: {exc}",
            ) from exc

        if db_rollback_path.exists():
            db_rollback_path.unlink()
        shutil.rmtree(assets_rollback_dir, ignore_errors=True)
        return {
            "message": "恢复成功",
            "pre_restore_backup": pre_restore_backup.path,
            "schema_version": _database_schema_version(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"恢复失败: {exc}") from exc
    finally:
        _restore_lock.release()
        if temp_zip.exists():
            temp_zip.unlink()
        if extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)
