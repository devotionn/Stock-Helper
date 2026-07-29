"""数据备份与恢复 API"""
import os
import sqlite3
import shutil
import zipfile
import json
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from ..database import get_db, get_connection, init_database
from ..config import settings
from ..schemas import BackupResult

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
            db_buf = sqlite3.connect(":memory:")
            src_conn = get_connection()
            src_conn.backup(db_buf)
            src_conn.close()

            db_bytes = db_buf.dump() if hasattr(db_buf, 'dump') else None
            # 使用 backup 到临时文件
            temp_db = backup_dir / f"{backup_name}_temp.db"
            with sqlite3.connect(str(temp_db)) as dest:
                src_conn2 = get_connection()
                src_conn2.backup(dest)
                src_conn2.close()
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

            # 3. manifest
            manifest = {
                "app_version": "1.0.0",
                "schema_version": 1,
                "created_at": datetime.now().isoformat(),
                "file_count": file_count,
                "total_size": total_size,
            }
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        # 原子rename
        temp_path.rename(backup_path)

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
    if not file.filename.endswith(".shbackup"):
        raise HTTPException(status_code=400, detail="请上传 .shbackup 备份文件")

    data = await file.read()
    temp_zip = settings.temp_dir / "restore.zip"
    temp_zip.write_bytes(data)

    extract_dir = settings.temp_dir / "restore_extract"
    assets_temp_dir = settings.temp_dir / "assets_pre_restore"

    MAX_TOTAL_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
    MAX_FILE_COUNT = 100000

    try:
        with zipfile.ZipFile(temp_zip, "r") as zf:
            names = zf.namelist()
            if "manifest.json" not in names or "database.db" not in names:
                raise HTTPException(status_code=400, detail="无效的备份文件")

            # ZIP路径穿越防护
            for name in names:
                if ".." in name or name.startswith("/"):
                    raise HTTPException(status_code=400, detail=f"非法文件路径: {name}")

            # 解压到临时目录
            if extract_dir.exists():
                shutil.rmtree(extract_dir, ignore_errors=True)
            extract_dir.mkdir(parents=True)

            total_size = 0
            file_count = 0
            for name in names:
                zf.extract(name, extract_dir)
                extracted_path = extract_dir / name
                if extracted_path.is_file():
                    total_size += extracted_path.stat().st_size
                    file_count += 1
                    if total_size > MAX_TOTAL_SIZE:
                        raise HTTPException(status_code=400, detail="解压后总大小超过2GB限制")
                    if file_count > MAX_FILE_COUNT:
                        raise HTTPException(status_code=400, detail="解压后文件数超过100000限制")

            # 校验manifest
            manifest_path = extract_dir / "manifest.json"
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            if not isinstance(manifest, dict) or "schema_version" not in manifest:
                raise HTTPException(status_code=400, detail="manifest.json格式无效")

            # SQLite完整性校验
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

        # 创建恢复前备份（在zip关闭后执行，避免占用句柄）
        pre_restore_backup = create_backup()

        # 原子替换：移动当前assets到临时目录
        if assets_temp_dir.exists():
            shutil.rmtree(assets_temp_dir, ignore_errors=True)
        if settings.assets_dir.exists():
            shutil.move(str(settings.assets_dir), str(assets_temp_dir))
        settings.assets_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 将备份assets复制到正式目录
            backup_assets_dir = extract_dir / "assets"
            if backup_assets_dir.exists():
                shutil.copytree(
                    str(backup_assets_dir), str(settings.assets_dir), dirs_exist_ok=True
                )

            # 替换数据库文件
            shutil.copy2(backup_db_path, settings.db_path)
            # 删除可能的WAL和SHM文件（属于旧数据库）
            for suffix in ["-wal", "-shm"]:
                wal_path = Path(str(settings.db_path) + suffix)
                if wal_path.exists():
                    wal_path.unlink()

            # 重新初始化数据库（应用迁移）
            init_database()
        except Exception as e:
            # 回滚：恢复原assets
            if settings.assets_dir.exists():
                shutil.rmtree(settings.assets_dir, ignore_errors=True)
            shutil.move(str(assets_temp_dir), str(settings.assets_dir))
            raise HTTPException(status_code=500, detail=f"恢复失败，已回滚: {str(e)}")

        # 清理临时assets备份
        shutil.rmtree(assets_temp_dir, ignore_errors=True)

        return {"message": "恢复成功", "pre_restore_backup": pre_restore_backup.path}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"恢复失败: {str(e)}")
    finally:
        if temp_zip.exists():
            temp_zip.unlink()
        if extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)
