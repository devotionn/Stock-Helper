"""数据备份与恢复 API"""
import os
import sqlite3
import shutil
import zipfile
import json
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from ..database import get_db, get_connection
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
        return BackupResult(
            success=False,
            path="",
            file_count=0,
            total_size=0,
            message=f"备份失败: {str(e)}",
        )


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

    try:
        with zipfile.ZipFile(temp_zip, "r") as zf:
            names = zf.namelist()
            if "manifest.json" not in names or "database.db" not in names:
                raise HTTPException(status_code=400, detail="无效的备份文件")

            # 先创建恢复前备份
            pre_restore_backup = create_backup()
            if not pre_restore_backup.success:
                raise HTTPException(status_code=500, detail="恢复前备份失败，已中止恢复")

            # 解压数据库
            extract_dir = settings.temp_dir / "restore_extract"
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            extract_dir.mkdir()

            zf.extract("database.db", extract_dir)

            # 替换数据库
            shutil.copy2(extract_dir / "database.db", settings.db_path)

            # 解压图片
            if any(n.startswith("assets/") for n in names):
                for name in names:
                    if name.startswith("assets/") and not name.endswith("/"):
                        rel = name[len("assets/"):]
                        target = settings.assets_dir / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(name) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)

            shutil.rmtree(extract_dir, ignore_errors=True)

        return {"message": "恢复成功", "pre_restore_backup": pre_restore_backup.path}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"恢复失败: {str(e)}")
    finally:
        if temp_zip.exists():
            temp_zip.unlink()
