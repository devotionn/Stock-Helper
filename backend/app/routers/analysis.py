"""组合分析 API。"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from ..config import MODULES, settings
from ..database import get_db
from ..schemas import AnalysisCreate, AnalysisOut, SaveToModuleRequest
from ..services.ai import call_ai

router = APIRouter()
MODULE_MAP = {module["id"]: module for module in MODULES}


def _normalize_record_date(value: str | None) -> str:
    if not value:
        return date.today().isoformat()
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="投研日期格式必须为 YYYY-MM-DD") from exc


def _ensure_entry(conn, record_date: str, module_id: int):
    if module_id not in MODULE_MAP:
        raise HTTPException(status_code=422, detail=f"模块 {module_id} 不存在")
    conn.execute(
        "INSERT OR IGNORE INTO module_entries(record_date, module_id) VALUES (?, ?)",
        (record_date, module_id),
    )
    return conn.execute(
        "SELECT * FROM module_entries WHERE record_date=? AND module_id=?",
        (record_date, module_id),
    ).fetchone()


def _collect_module_snapshot(conn, record_date: str, module_id: int) -> dict:
    """收集指定日期的模块内容作为不可变分析快照。"""
    entry = _ensure_entry(conn, record_date, module_id)
    images = conn.execute(
        "SELECT a.id, a.relative_path, a.thumbnail_path, ea.order_index "
        "FROM entry_assets ea JOIN assets a ON a.id=ea.asset_id "
        "WHERE ea.module_entry_id=? ORDER BY ea.order_index, ea.id",
        (entry["id"],),
    ).fetchall()
    return {
        "record_date": record_date,
        "module_id": module_id,
        "display_title": entry["display_title"] or "",
        "text_content": entry["text_content"] or "",
        "assets": [str(settings.assets_dir / row["relative_path"]) for row in images],
        "image_rows": images,
    }


@router.post("", status_code=202)
async def create_analysis(body: AnalysisCreate, background_tasks: BackgroundTasks):
    """创建分析记录并立即返回，AI 分析在后台异步执行。"""
    if not body.module_ids:
        raise HTTPException(status_code=400, detail="请至少选择一个模块")
    module_ids = list(dict.fromkeys(body.module_ids))
    invalid = [module_id for module_id in module_ids if module_id not in MODULE_MAP]
    if invalid:
        raise HTTPException(status_code=422, detail=f"存在无效模块：{invalid}")

    record_date = _normalize_record_date(body.record_date)
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO analyses "
            "(combination, combination_name, analysis_request, record_date, status) "
            "VALUES (?, ?, ?, ?, 'pending')",
            (
                json.dumps(module_ids),
                body.combination_name,
                body.analysis_request,
                record_date,
            ),
        )
        analysis_id = cursor.lastrowid

        snapshots = []
        for order_index, module_id in enumerate(module_ids):
            snapshot = _collect_module_snapshot(conn, record_date, module_id)
            snapshot["order_index"] = order_index
            snapshot["module_name"] = MODULE_MAP[module_id]["name"]
            conn.execute(
                "INSERT INTO analysis_snapshots "
                "(analysis_id, module_id, order_index, module_name, display_title, text_content) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    analysis_id,
                    module_id,
                    order_index,
                    snapshot["module_name"],
                    snapshot["display_title"],
                    snapshot["text_content"],
                ),
            )
            for image_index, image in enumerate(snapshot.pop("image_rows")):
                conn.execute(
                    "INSERT INTO analysis_assets "
                    "(analysis_id, module_id, order_index, image_order_index, asset_id, "
                    "relative_path, thumbnail_path) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        analysis_id,
                        module_id,
                        order_index,
                        image_index,
                        image["id"],
                        image["relative_path"],
                        image["thumbnail_path"],
                    ),
                )
            snapshots.append(snapshot)

    background_tasks.add_task(
        _run_analysis_background,
        analysis_id,
        snapshots,
        body.analysis_request,
    )
    return {"id": analysis_id, "status": "pending", "record_date": record_date}


async def _run_analysis_background(
    analysis_id: int,
    snapshots: list[dict],
    analysis_request: str,
):
    with get_db() as conn:
        conn.execute(
            "UPDATE analyses SET status='running', started_at=datetime('now','localtime') "
            "WHERE id=?",
            (analysis_id,),
        )

    result = await call_ai(snapshots, analysis_request)
    with get_db() as conn:
        if result.get("error"):
            conn.execute(
                "UPDATE analyses SET status='failed', error_message=?, raw_result=?, "
                "completed_at=datetime('now','localtime') WHERE id=?",
                (result["error"], result.get("raw_result"), analysis_id),
            )
        elif result.get("warning"):
            conn.execute(
                "UPDATE analyses SET status='completed_with_warning', result_json=NULL, "
                "raw_result=?, completed_at=datetime('now','localtime') WHERE id=?",
                (result["raw_result"], analysis_id),
            )
        else:
            conn.execute(
                "UPDATE analyses SET status='completed', result_json=?, raw_result=?, "
                "completed_at=datetime('now','localtime') WHERE id=?",
                (result["result_json"], result["raw_result"], analysis_id),
            )


def get_analysis_by_id_impl(analysis_id: int) -> AnalysisOut:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="分析记录不存在")
        return AnalysisOut(
            id=row["id"],
            combination=json.loads(row["combination"]),
            combination_name=row["combination_name"] or "",
            analysis_request=row["analysis_request"] or "",
            record_date=row["record_date"],
            status=row["status"],
            result_json=row["result_json"],
            raw_result=row["raw_result"],
            error_message=row["error_message"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )


@router.get("/{analysis_id}", response_model=AnalysisOut)
def get_analysis(analysis_id: int):
    return get_analysis_by_id_impl(analysis_id)


@router.get("/{analysis_id}/detail")
def get_analysis_detail(analysis_id: int):
    with get_db() as conn:
        analysis = conn.execute(
            "SELECT * FROM analyses WHERE id=?",
            (analysis_id,),
        ).fetchone()
        if not analysis:
            raise HTTPException(status_code=404, detail="分析记录不存在")

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
                            "relative_path": row["relative_path"],
                            "thumbnail_path": row["thumbnail_path"],
                        }
                        for row in images
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
                "record_date": analysis["record_date"],
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


@router.post("/save-to-module")
def save_to_module(body: SaveToModuleRequest):
    """将分析结果保存到该分析所属日期的 AI 复盘或操作建议。"""
    if body.module_id not in (9, 11):
        raise HTTPException(status_code=400, detail="只能保存到9号(AI复盘)或11号(操作建议)模块")

    with get_db() as conn:
        analysis = conn.execute(
            "SELECT record_date FROM analyses WHERE id=?",
            (body.analysis_id,),
        ).fetchone()
        if not analysis:
            raise HTTPException(status_code=404, detail="分析记录不存在")
        record_date = analysis["record_date"] or date.today().isoformat()
        entry = _ensure_entry(conn, record_date, body.module_id)
        existing = entry["text_content"] or ""
        prefix = f"【来自 {record_date} 分析 #{body.analysis_id}】\n"
        new_text = (
            existing + "\n\n---\n\n" + prefix + body.content
            if existing.strip()
            else prefix + body.content
        )
        conn.execute(
            "UPDATE module_entries SET text_content=?, revision=revision+1, "
            "updated_at=datetime('now','localtime') WHERE id=?",
            (new_text, entry["id"]),
        )
        flag = "saved_to_review" if body.module_id == 9 else "saved_to_advice"
        conn.execute(f"UPDATE analyses SET {flag}=1 WHERE id=?", (body.analysis_id,))
    return {
        "message": "已保存",
        "record_date": record_date,
        "revision": entry["revision"] + 1,
    }


class ReviewContentUpdate(BaseModel):
    review_content: str


@router.put("/{analysis_id}/review")
def update_review_content(analysis_id: int, body: ReviewContentUpdate):
    with get_db() as conn:
        row = conn.execute("SELECT id FROM analyses WHERE id=?", (analysis_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="分析记录不存在")
        conn.execute(
            "UPDATE analyses SET review_content=? WHERE id=?",
            (body.review_content, analysis_id),
        )
    return {"message": "复盘内容已保存"}
