"""历史记录 API。"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

from ..database import get_db
from ..schemas import AnalysisNoteUpdate

router = APIRouter()


@router.get("")
def list_history(
    date_from: str = Query(None),
    date_to: str = Query(None),
    combination_name: str = Query(None),
    stock_name: str = Query(None),
    module_id: int = Query(None),
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """查询历史分析记录；日期条件按投研日期而不是实际创建时间。"""
    conditions: list[str] = []
    params: list[object] = []

    if date_from:
        conditions.append("COALESCE(a.record_date, date(a.created_at)) >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("COALESCE(a.record_date, date(a.created_at)) <= ?")
        params.append(date_to)
    if combination_name:
        conditions.append("a.combination_name LIKE ?")
        params.append(f"%{combination_name}%")
    if keyword:
        conditions.append(
            "(a.analysis_request LIKE ? OR a.raw_result LIKE ? OR EXISTS("
            "SELECT 1 FROM analysis_snapshots s "
            "WHERE s.analysis_id=a.id AND (s.text_content LIKE ? OR s.display_title LIKE ?)))"
        )
        params.extend([f"%{keyword}%"] * 4)
    if module_id is not None:
        conditions.append(
            "EXISTS(SELECT 1 FROM analysis_snapshots s "
            "WHERE s.analysis_id=a.id AND s.module_id=?)"
        )
        params.append(module_id)
    if stock_name:
        conditions.append(
            "EXISTS(SELECT 1 FROM analysis_snapshots s WHERE s.analysis_id=a.id "
            "AND (s.display_title LIKE ? OR s.text_content LIKE ?))"
        )
        params.extend([f"%{stock_name}%", f"%{stock_name}%"])

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * page_size

    with get_db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM analyses a WHERE {where}",
            params,
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT a.* FROM analyses a WHERE {where} "
            "ORDER BY COALESCE(a.record_date, date(a.created_at)) DESC, a.created_at DESC "
            "LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()

        items = []
        for row in rows:
            snapshots = conn.execute(
                "SELECT module_id, module_name, display_title FROM analysis_snapshots "
                "WHERE analysis_id=? ORDER BY order_index",
                (row["id"],),
            ).fetchall()
            items.append(
                {
                    "id": row["id"],
                    "combination": json.loads(row["combination"]),
                    "combination_name": row["combination_name"] or "",
                    "analysis_request": row["analysis_request"] or "",
                    "record_date": row["record_date"] or row["created_at"][:10],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "completed_at": row["completed_at"],
                    "modules": [
                        {
                            "module_id": snapshot["module_id"],
                            "module_name": snapshot["module_name"],
                            "display_title": snapshot["display_title"] or "",
                        }
                        for snapshot in snapshots
                    ],
                }
            )

    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/{analysis_id}/detail")
def get_history_detail(analysis_id: int):
    with get_db() as conn:
        analysis = conn.execute(
            "SELECT * FROM analyses WHERE id=?",
            (analysis_id,),
        ).fetchone()
        if not analysis:
            raise HTTPException(status_code=404, detail="记录不存在")

        snapshots = conn.execute(
            "SELECT * FROM analysis_snapshots WHERE analysis_id=? ORDER BY order_index",
            (analysis_id,),
        ).fetchall()
        snapshot_list = []
        for snapshot in snapshots:
            images = conn.execute(
                "SELECT relative_path, thumbnail_path FROM analysis_assets "
                "WHERE analysis_id=? AND module_id=? ORDER BY image_order_index",
                (analysis_id, snapshot["module_id"]),
            ).fetchall()
            snapshot_list.append(
                {
                    "module_id": snapshot["module_id"],
                    "order_index": snapshot["order_index"],
                    "module_name": snapshot["module_name"],
                    "display_title": snapshot["display_title"] or "",
                    "text_content": snapshot["text_content"],
                    "images": [
                        {
                            "relative_path": image["relative_path"],
                            "thumbnail_path": image["thumbnail_path"],
                        }
                        for image in images
                    ],
                }
            )

        notes = conn.execute(
            "SELECT * FROM analysis_notes WHERE analysis_id=? ORDER BY created_at DESC",
            (analysis_id,),
        ).fetchall()
        return {
            "analysis": {
                "id": analysis["id"],
                "combination": json.loads(analysis["combination"]),
                "combination_name": analysis["combination_name"] or "",
                "analysis_request": analysis["analysis_request"] or "",
                "record_date": analysis["record_date"] or analysis["created_at"][:10],
                "status": analysis["status"],
                "result_json": analysis["result_json"],
                "raw_result": analysis["raw_result"],
                "error_message": analysis["error_message"],
                "created_at": analysis["created_at"],
                "started_at": analysis["started_at"],
                "completed_at": analysis["completed_at"],
                "saved_to_review": analysis["saved_to_review"],
                "saved_to_advice": analysis["saved_to_advice"],
                "review_content": analysis["review_content"] or "",
            },
            "snapshots": snapshot_list,
            "notes": [
                {"id": row["id"], "note": row["note"], "created_at": row["created_at"]}
                for row in notes
            ],
        }


@router.put("/{analysis_id}/note")
def update_note(analysis_id: int, body: AnalysisNoteUpdate):
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM analysis_notes WHERE analysis_id=?",
            (analysis_id,),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE analysis_notes SET note=? WHERE analysis_id=?",
                (body.note, analysis_id),
            )
        else:
            conn.execute(
                "INSERT INTO analysis_notes (analysis_id, note) VALUES (?, ?)",
                (analysis_id, body.note),
            )
    return {"message": "备注已保存"}


@router.delete("/{analysis_id}")
def delete_history(
    analysis_id: int,
    confirm: str = Query(..., description="必须传入 '确认删除' 以确认"),
):
    if confirm != "确认删除":
        raise HTTPException(status_code=400, detail="请确认删除操作")
    with get_db() as conn:
        conn.execute("DELETE FROM analyses WHERE id=?", (analysis_id,))
    return {"message": "已删除"}
