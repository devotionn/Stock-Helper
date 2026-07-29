"""按投研日期管理 12 个模块、图片与日历状态。"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ..config import MODULES
from ..database import get_db
from ..schemas import AssetCaptionUpdate, AssetOut, ModuleDraftUpdate
from ..services.image import save_uploaded_image

router = APIRouter()
MODULE_MAP = {module["id"]: module for module in MODULES}
DEFAULT_COPY_MODULE_IDS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10]


class CopyWorkspaceRequest(BaseModel):
    source_date: str
    module_ids: list[int] = Field(default_factory=lambda: DEFAULT_COPY_MODULE_IDS.copy())
    overwrite: bool = False


def _parse_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="日期格式必须为 YYYY-MM-DD") from exc


def _parse_month(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m")
        return value
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="月份格式必须为 YYYY-MM") from exc


def _text_summary(text: str, max_len: int = 50) -> str:
    normalized = (text or "").strip().replace("\n", " ")
    if not normalized:
        return ""
    return normalized[:max_len] + ("..." if len(normalized) > max_len else "")


def _ensure_entries(conn, record_date: str) -> None:
    for module in MODULES:
        conn.execute(
            "INSERT OR IGNORE INTO module_entries(record_date, module_id) VALUES (?, ?)",
            (record_date, module["id"]),
        )


def _entry_row(conn, record_date: str, module_id: int):
    if module_id not in MODULE_MAP:
        raise HTTPException(status_code=404, detail="模块不存在")
    _ensure_entries(conn, record_date)
    return conn.execute(
        "SELECT * FROM module_entries WHERE record_date=? AND module_id=?",
        (record_date, module_id),
    ).fetchone()


def _entry_has_content(row, image_count: int) -> bool:
    return bool(
        (row["text_content"] or "").strip()
        or (row["display_title"] or "").strip()
        or image_count > 0
    )


def _module_payload(conn, row) -> dict[str, Any]:
    image_count = conn.execute(
        "SELECT COUNT(*) FROM entry_assets WHERE module_entry_id=?",
        (row["id"],),
    ).fetchone()[0]
    module = MODULE_MAP[row["module_id"]]
    has_content = _entry_has_content(row, image_count)
    return {
        "entry_id": row["id"],
        "record_date": row["record_date"],
        "module_id": row["module_id"],
        "module_name": module["name"],
        "module_desc": module["desc"],
        "display_title": row["display_title"] or "",
        "text_content": row["text_content"] or "",
        "revision": row["revision"],
        "status": row["status"] or "draft",
        "period_start": row["period_start"],
        "period_end": row["period_end"],
        "updated_at": row["updated_at"],
        "image_count": image_count,
        "has_content": has_content,
        "text_summary": _text_summary(row["text_content"]),
    }


@router.get("/calendar")
def get_calendar(month: str = Query(..., description="YYYY-MM")):
    """一次返回整月的录入完成度和 AI 分析状态。"""
    month = _parse_month(month)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT e.record_date, e.module_id, e.text_content, e.display_title, "
            "COUNT(ea.id) AS image_count "
            "FROM module_entries e "
            "LEFT JOIN entry_assets ea ON ea.module_entry_id=e.id "
            "WHERE e.record_date LIKE ? "
            "GROUP BY e.id ORDER BY e.record_date, e.module_id",
            (month + "-%",),
        ).fetchall()
        analyses = conn.execute(
            "SELECT record_date, COUNT(*) AS analysis_count FROM analyses "
            "WHERE record_date LIKE ? GROUP BY record_date",
            (month + "-%",),
        ).fetchall()

    days: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = days.setdefault(
            row["record_date"],
            {
                "date": row["record_date"],
                "completed_count": 0,
                "total_count": len(MODULES),
                "analysis_count": 0,
                "status": "empty",
            },
        )
        if (
            (row["text_content"] or "").strip()
            or (row["display_title"] or "").strip()
            or row["image_count"] > 0
        ):
            item["completed_count"] += 1

    for row in analyses:
        item = days.setdefault(
            row["record_date"],
            {
                "date": row["record_date"],
                "completed_count": 0,
                "total_count": len(MODULES),
                "analysis_count": 0,
                "status": "empty",
            },
        )
        item["analysis_count"] = row["analysis_count"]

    for item in days.values():
        if item["analysis_count"] > 0:
            item["status"] = "analyzed"
        elif item["completed_count"] >= len(MODULES):
            item["status"] = "complete"
        elif item["completed_count"] > 0:
            item["status"] = "partial"

    return {"month": month, "days": sorted(days.values(), key=lambda item: item["date"])}


@router.get("/{record_date}")
def get_workspace(record_date: str):
    """获取指定投研日期的完整 12 模块工作区。"""
    record_date = _parse_date(record_date)
    with get_db() as conn:
        _ensure_entries(conn, record_date)
        rows = conn.execute(
            "SELECT * FROM module_entries WHERE record_date=? ORDER BY module_id",
            (record_date,),
        ).fetchall()
        cards = [_module_payload(conn, row) for row in rows]
        analysis_count = conn.execute(
            "SELECT COUNT(*) FROM analyses WHERE record_date=?",
            (record_date,),
        ).fetchone()[0]

    completed_count = sum(1 for card in cards if card["has_content"])
    status = "empty"
    if analysis_count > 0:
        status = "analyzed"
    elif completed_count >= len(MODULES):
        status = "complete"
    elif completed_count > 0:
        status = "partial"
    return {
        "record_date": record_date,
        "completed_count": completed_count,
        "total_count": len(MODULES),
        "analysis_count": analysis_count,
        "status": status,
        "cards": cards,
    }


@router.post("/{target_date}/copy")
def copy_workspace(target_date: str, body: CopyWorkspaceRequest):
    """复制上一日或任意来源日期的选定模块；默认不覆盖已有内容。"""
    target_date = _parse_date(target_date)
    source_date = _parse_date(body.source_date)
    if target_date == source_date:
        raise HTTPException(status_code=400, detail="来源日期和目标日期不能相同")

    module_ids = list(dict.fromkeys(body.module_ids))
    invalid = [module_id for module_id in module_ids if module_id not in MODULE_MAP]
    if invalid:
        raise HTTPException(status_code=422, detail=f"存在无效模块：{invalid}")

    copied: list[int] = []
    skipped: list[int] = []
    with get_db() as conn:
        source_count = conn.execute(
            "SELECT COUNT(*) FROM module_entries WHERE record_date=?",
            (source_date,),
        ).fetchone()[0]
        if source_count == 0:
            raise HTTPException(status_code=404, detail="来源日期没有可复制的数据")

        _ensure_entries(conn, target_date)
        for module_id in module_ids:
            source = conn.execute(
                "SELECT * FROM module_entries WHERE record_date=? AND module_id=?",
                (source_date, module_id),
            ).fetchone()
            target = conn.execute(
                "SELECT * FROM module_entries WHERE record_date=? AND module_id=?",
                (target_date, module_id),
            ).fetchone()
            if not source or not target:
                skipped.append(module_id)
                continue

            target_image_count = conn.execute(
                "SELECT COUNT(*) FROM entry_assets WHERE module_entry_id=?",
                (target["id"],),
            ).fetchone()[0]
            if _entry_has_content(target, target_image_count) and not body.overwrite:
                skipped.append(module_id)
                continue

            conn.execute(
                "UPDATE module_entries SET display_title=?, text_content=?, status='draft', "
                "period_start=?, period_end=?, revision=revision+1, "
                "updated_at=datetime('now','localtime') WHERE id=?",
                (
                    source["display_title"],
                    source["text_content"],
                    source["period_start"],
                    source["period_end"],
                    target["id"],
                ),
            )
            conn.execute(
                "DELETE FROM entry_assets WHERE module_entry_id=?",
                (target["id"],),
            )
            conn.execute(
                "INSERT INTO entry_assets(module_entry_id, asset_id, order_index, caption) "
                "SELECT ?, asset_id, order_index, caption FROM entry_assets "
                "WHERE module_entry_id=? ORDER BY order_index",
                (target["id"], source["id"]),
            )
            copied.append(module_id)

        conn.execute(
            "INSERT INTO settings(key, value, updated_at) VALUES "
            "('active_record_date', ?, datetime('now','localtime')) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (target_date,),
        )

    return {
        "message": f"已复制 {len(copied)} 个模块，跳过 {len(skipped)} 个模块",
        "source_date": source_date,
        "target_date": target_date,
        "copied_module_ids": copied,
        "skipped_module_ids": skipped,
    }


@router.get("/{record_date}/modules/{module_id}")
def get_module(record_date: str, module_id: int):
    record_date = _parse_date(record_date)
    with get_db() as conn:
        row = _entry_row(conn, record_date, module_id)
        return _module_payload(conn, row)


@router.put("/{record_date}/modules/{module_id}")
def update_module(record_date: str, module_id: int, body: ModuleDraftUpdate):
    record_date = _parse_date(record_date)
    with get_db() as conn:
        row = _entry_row(conn, record_date, module_id)
        if body.revision != row["revision"]:
            raise HTTPException(status_code=409, detail="内容已在另一个页面更新，请先刷新")
        conn.execute(
            "UPDATE module_entries SET text_content=?, display_title=?, period_start=?, "
            "period_end=?, status=?, revision=revision+1, "
            "updated_at=datetime('now','localtime') WHERE id=?",
            (
                body.text_content,
                body.display_title or "",
                body.period_start,
                body.period_end,
                body.status or "draft",
                row["id"],
            ),
        )
        conn.execute(
            "INSERT INTO settings(key, value, updated_at) VALUES "
            "('active_record_date', ?, datetime('now','localtime')) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (record_date,),
        )
    return {"revision": body.revision + 1, "message": "保存成功"}


@router.get("/{record_date}/modules/{module_id}/images", response_model=list[AssetOut])
def get_images(record_date: str, module_id: int):
    record_date = _parse_date(record_date)
    with get_db() as conn:
        entry = _entry_row(conn, record_date, module_id)
        rows = conn.execute(
            "SELECT a.*, ea.order_index, ea.caption FROM entry_assets ea "
            "JOIN assets a ON a.id=ea.asset_id WHERE ea.module_entry_id=? "
            "ORDER BY ea.order_index, ea.id",
            (entry["id"],),
        ).fetchall()
    return [
        AssetOut(
            id=row["id"],
            sha256=row["sha256"],
            original_filename=row["original_filename"],
            relative_path=row["relative_path"],
            thumbnail_path=row["thumbnail_path"],
            file_size=row["file_size"],
            width=row["width"],
            height=row["height"],
            order_index=row["order_index"],
            caption=row["caption"],
        )
        for row in rows
    ]


@router.post("/{record_date}/modules/{module_id}/images", response_model=AssetOut)
async def upload_image(
    record_date: str,
    module_id: int,
    file: UploadFile = File(...),
):
    record_date = _parse_date(record_date)
    info = await save_uploaded_image(file)
    with get_db() as conn:
        entry = _entry_row(conn, record_date, module_id)
        asset = conn.execute(
            "SELECT * FROM assets WHERE sha256=?",
            (info["sha256"],),
        ).fetchone()
        if asset:
            asset_id = asset["id"]
        else:
            cursor = conn.execute(
                "INSERT INTO assets(sha256, original_filename, relative_path, thumbnail_path, "
                "file_size, width, height, mime_type, format) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    info["sha256"],
                    info["original_filename"],
                    info["relative_path"],
                    info["thumbnail_path"],
                    info["file_size"],
                    info["width"],
                    info["height"],
                    info["mime_type"],
                    info["format"],
                ),
            )
            asset_id = cursor.lastrowid

        existing = conn.execute(
            "SELECT order_index, caption FROM entry_assets "
            "WHERE module_entry_id=? AND asset_id=?",
            (entry["id"], asset_id),
        ).fetchone()
        if existing:
            order_index = existing["order_index"]
            caption = existing["caption"]
        else:
            max_order = conn.execute(
                "SELECT COALESCE(MAX(order_index), 0) FROM entry_assets WHERE module_entry_id=?",
                (entry["id"],),
            ).fetchone()[0]
            order_index = max_order + 1
            caption = ""
            conn.execute(
                "INSERT INTO entry_assets(module_entry_id, asset_id, order_index, caption) "
                "VALUES (?, ?, ?, '')",
                (entry["id"], asset_id, order_index),
            )
            conn.execute(
                "UPDATE module_entries SET revision=revision+1, "
                "updated_at=datetime('now','localtime') WHERE id=?",
                (entry["id"],),
            )

    return AssetOut(
        id=asset_id,
        sha256=info["sha256"],
        original_filename=info["original_filename"],
        relative_path=info["relative_path"],
        thumbnail_path=info["thumbnail_path"],
        file_size=info["file_size"],
        width=info["width"],
        height=info["height"],
        order_index=order_index,
        caption=caption,
    )


@router.delete("/{record_date}/modules/{module_id}/images/{asset_id}")
def delete_image(record_date: str, module_id: int, asset_id: int):
    record_date = _parse_date(record_date)
    with get_db() as conn:
        entry = _entry_row(conn, record_date, module_id)
        conn.execute(
            "DELETE FROM entry_assets WHERE module_entry_id=? AND asset_id=?",
            (entry["id"], asset_id),
        )
        conn.execute(
            "UPDATE module_entries SET revision=revision+1, "
            "updated_at=datetime('now','localtime') WHERE id=?",
            (entry["id"],),
        )
        refs = conn.execute(
            "SELECT COUNT(*) FROM entry_assets WHERE asset_id=? "
            "UNION ALL SELECT COUNT(*) FROM draft_assets WHERE asset_id=? "
            "UNION ALL SELECT COUNT(*) FROM version_assets WHERE asset_id=? "
            "UNION ALL SELECT COUNT(*) FROM analysis_assets WHERE asset_id=?",
            (asset_id, asset_id, asset_id, asset_id),
        ).fetchall()
        if sum(row[0] for row in refs) == 0:
            conn.execute(
                "UPDATE assets SET is_orphan=1, orphan_since=datetime('now','localtime') WHERE id=?",
                (asset_id,),
            )
    return {"message": "已移除"}


@router.put("/{record_date}/modules/{module_id}/images/{asset_id}")
def update_image(
    record_date: str,
    module_id: int,
    asset_id: int,
    body: AssetCaptionUpdate,
):
    record_date = _parse_date(record_date)
    with get_db() as conn:
        entry = _entry_row(conn, record_date, module_id)
        if body.order_index is None:
            conn.execute(
                "UPDATE entry_assets SET caption=? WHERE module_entry_id=? AND asset_id=?",
                (body.caption, entry["id"], asset_id),
            )
        else:
            conn.execute(
                "UPDATE entry_assets SET caption=?, order_index=? "
                "WHERE module_entry_id=? AND asset_id=?",
                (body.caption, body.order_index, entry["id"], asset_id),
            )
    return {"message": "已更新"}


@router.put("/{record_date}/modules/{module_id}/images/reorder")
def reorder_images(record_date: str, module_id: int, asset_ids: list[int]):
    record_date = _parse_date(record_date)
    with get_db() as conn:
        entry = _entry_row(conn, record_date, module_id)
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT asset_id FROM entry_assets WHERE module_entry_id=?",
                (entry["id"],),
            ).fetchall()
        }
        if set(asset_ids) != existing:
            raise HTTPException(status_code=422, detail="图片列表与当前模块不一致，请刷新后重试")
        for index, asset_id in enumerate(asset_ids, start=1):
            conn.execute(
                "UPDATE entry_assets SET order_index=? WHERE module_entry_id=? AND asset_id=?",
                (index, entry["id"], asset_id),
            )
    return {"message": "排序已更新"}
