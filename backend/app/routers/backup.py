"""数据备份与恢复 API"""
import os
import sqlite3
import shutil
import zipfile
import json
import threading
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from ..database import get_db, get_connection, init_database
from ..config import settings
from ..schemas import BackupResult

APP_VERSION = os.environ.get("STOCK_APP_VERSION", "1.0.0")

_restore_lock = threading.Lock()

router = APIRouter()


def _get_backup_location() -> Path:
    """从设置中获取备份位置"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key='backup_location'"
        ).fetchone()
        if row and row["value"]:
            return Path(row["value"])
    return settings.backup_dir


@router.post("", response_model=BackupResult)
def create_backup():
    """一键备份：数据库 + 图片 + 设置 + 历史结果 + 组合配置"""
    backup_dir = _get_backup_location()
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"stock_helper_backup_{timestamp}"
    backup_path = backup_dir / f"{backup_name}.shbackup"
    temp_path = backup_dir / f"{backup_name}.tmp"

    file_count = 0
    total_size = 0

    try:
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1. 数据库一致快照（使用SQLite在线备份API）
            temp_db = backup_dir / f"{backup_name}_temp.db"
            dest = sqlite3.connect(str(temp_db))
            src_conn = get_connection()
            src_conn.backup(dest)
            src_conn.close()
            dest.close()
            zf.write(temp_db, "database.db")
            file_count += 1
            total_size += temp_db.stat().st_size
            temp_db.unlink()

            # 2. 图片文件
            if settings.assets_dir.exists():
                for root, dirs, files in os.walk(settings.assets_dir):
                    for f in files:
                        abs_path = Path(root) / f
                        rel_path = abs_path.relative_to(settings.assets_dir)
                        zf.write(abs_path, f"assets/{rel_path}")
                        file_count += 1
                        total_size += abs_path.stat().st_size

            # 读取当前迁移版本
            with get_db() as conn:
                row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
                db_schema_version = row[0] if row[0] else 0

            # 3. manifest
            manifest = {
                "app_version": APP_VERSION,
                "schema_version": db_schema_version,
                "created_at": datetime.now().isoformat(),
                "file_count": file_count,
                "total_size": total_size,
            }
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        # 原子rename
        os.replace(str(temp_path), str(backup_path))

        # 记录备份
        with get_db() as conn:
            conn.execute(
                "INSERT INTO backup_runs (backup_path, file_count, total_size, status) "
                "VALUES (?,?,?, 'success')",
                (str(backup_path), file_count, total_size),
            )

        return BackupResult(
            success=True,
            path=str(backup_path),
            file_count=file_count,
            total_size=total_size,
            message=f"备份成功，共 {file_count} 个文件，大小 {total_size / 1024 / 1024:.1f}MB",
        )
    except Exception as e:
        if temp_path.exists():
            temp_path.unlink()
        raise HTTPException(status_code=500, detail=f"备份失败: {str(e)}")


@router.get("", response_model=list)
def list_backups():
    """列出备份记录"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM backup_runs ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        return [{
            "id": r["id"],
            "backup_path": r["backup_path"],
            "file_count": r["file_count"],
            "total_size": r["total_size"],
            "status": r["status"],
            "created_at": r["created_at"],
        } for r in rows]


@router.post("/restore")
async def restore_backup(file: UploadFile = File(...)):
    """从备份文件恢复"""
    if not _restore_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="正在执行恢复操作，请等待")
    temp_zip = settings.temp_dir / "restore.zip"
    extract_dir = settings.temp_dir / "restore_extract"
    assets_rollback_dir = settings.temp_dir / "assets_rollback"
    db_rollback_path = settings.temp_dir / "db_rollback.db"

    MAX_TOTAL_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
    MAX_FILE_COUNT = 100000
    MAX_SINGLE_FILE_SIZE = 100 * 1024 * 1024  # 单文件100MB

    try:
        if not file.filename.endswith(".shbackup"):
            raise HTTPException(status_code=400, detail="请上传 .shbackup 备份文件")

        content = await file.read()
        if len(content) > 2 * 1024 * 1024 * 1024:  # 2GB
            raise HTTPException(status_code=400, detail="备份文件过大")
        temp_zip.write_bytes(content)

        # ===== 阶段1：解压前校验（读取ZIP信息，不实际解压）=====
        with zipfile.ZipFile(temp_zip, "r") as zf:
            names = zf.namelist()
            if "manifest.json" not in names or "database.db" not in names:
                raise HTTPException(status_code=400, detail="无效的备份文件")

            # 1. 先读取ZIP信息，不解压
            total_uncompressed = sum(i.file_size for i in zf.infolist())
            file_count = len(names)
            if total_uncompressed > MAX_TOTAL_SIZE:
                raise HTTPException(status_code=400, detail="备份文件过大")
            if file_count > MAX_FILE_COUNT:
                raise HTTPException(status_code=400, detail="备份文件数量过多")

            # 2. 检查路径安全
            for name in names:
                if ".." in name or name.startswith("/"):
                    raise HTTPException(status_code=400, detail="备份文件包含不安全路径")

            # 3. 检查单文件大小
            for info in zf.infolist():
                if info.file_size > MAX_SINGLE_FILE_SIZE:
                    raise HTTPException(status_code=400, detail=f"文件过大: {info.filename}")

        # ===== 阶段2：解压到临时目录 extract_dir =====
        if extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)
        extract_dir.mkdir(parents=True)
        with zipfile.ZipFile(temp_zip, "r") as zf:
            zf.extractall(extract_dir)

        # ===== 阶段3：校验 manifest.json =====
        manifest_path = extract_dir / "manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        if not isinstance(manifest, dict) or "schema_version" not in manifest:
            raise HTTPException(status_code=400, detail="manifest.json格式无效")

        # ===== 阶段4：校验 database.db (PRAGMA integrity_check) =====
        backup_db_path = extract_dir / "database.db"
        integrity_conn = sqlite3.connect(str(backup_db_path))
        try:
            integrity_result = integrity_conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            integrity_conn.close()
        if integrity_result[0] != "ok":
            raise HTTPException(
                status_code=400,
                detail=f"备份数据库完整性校验失败: {integrity_result[0]}",
            )

        # ===== 阶段5：创建恢复前备份（在zip关闭后执行，避免占用句柄）=====
        pre_restore_backup = create_backup()

        # ===== 阶段6：记录原始数据库路径和assets路径（settings.db_path / settings.assets_dir）=====

        # ===== 阶段7：移动当前 assets 到 assets_rollback 目录 =====
        if assets_rollback_dir.exists():
            shutil.rmtree(assets_rollback_dir, ignore_errors=True)
        if settings.assets_dir.exists():
            shutil.move(str(settings.assets_dir), str(assets_rollback_dir))
        settings.assets_dir.mkdir(parents=True, exist_ok=True)

        try:
            # ===== 阶段8：复制备份 assets 到正式 assets 目录 =====
            backup_assets_dir = extract_dir / "assets"
            if backup_assets_dir.exists():
                shutil.copytree(
                    str(backup_assets_dir), str(settings.assets_dir), dirs_exist_ok=True
                )

            # ===== 阶段9：移动当前数据库到 db_rollback.db =====
            if db_rollback_path.exists():
                db_rollback_path.unlink()
            if settings.db_path.exists():
                shutil.move(str(settings.db_path), str(db_rollback_path))

            # ===== 阶段10：复制备份数据库到正式路径，删除 WAL/SHM 文件 =====
            shutil.copy2(backup_db_path, settings.db_path)
            for suffix in ["-wal", "-shm"]:
                wal_path = Path(str(settings.db_path) + suffix)
                if wal_path.exists():
                    wal_path.unlink()

            # ===== 阶段11：重新初始化数据库 (init_database) =====
            init_database()

            # ===== 阶段12：验证：检查新数据库是否能正常打开和查询 =====
            verify_conn = sqlite3.connect(str(settings.db_path))
            try:
                verify_result = verify_conn.execute("PRAGMA integrity_check").fetchone()
                verify_conn.execute("SELECT COUNT(*) FROM module_drafts").fetchone()
            finally:
                verify_conn.close()
            if verify_result[0] != "ok":
                raise RuntimeError(f"恢复后数据库验证失败: {verify_result[0]}")

        except Exception as e:
            # ===== 阶段14：失败回滚 =====
            # 把 db_rollback.db 移回正式路径（仅当数据库已移出时）
            if db_rollback_path.exists():
                try:
                    if settings.db_path.exists():
                        settings.db_path.unlink()
                except Exception:
                    pass
                shutil.move(str(db_rollback_path), str(settings.db_path))
            # 把 assets_rollback 移回正式路径（仅当图片已移出时）
            if assets_rollback_dir.exists():
                if settings.assets_dir.exists():
                    shutil.rmtree(settings.assets_dir, ignore_errors=True)
                shutil.move(str(assets_rollback_dir), str(settings.assets_dir))
            # 删除临时解压目录
            shutil.rmtree(extract_dir, ignore_errors=True)
            # 重新初始化数据库
            try:
                init_database()
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=f"恢复失败，已回滚: {str(e)}")

        # ===== 阶段13：成功，删除回滚目录 =====
        if db_rollback_path.exists():
            db_rollback_path.unlink()
        shutil.rmtree(assets_rollback_dir, ignore_errors=True)

        return {"message": "恢复成功", "pre_restore_backup": pre_restore_backup.path}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"恢复失败: {str(e)}")
    finally:
        _restore_lock.release()
        if temp_zip.exists():
            temp_zip.unlink()
        if extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)
