"""组合分析 API"""
import json
import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks
from ..database import get_db
from ..config import MODULES
from ..schemas import AnalysisCreate, AnalysisOut, SaveToModuleRequest
from ..services.ai import call_ai

router = APIRouter()
MODULE_MAP = {m["id"]: m for m in MODULES}


def _collect_module_snapshot(conn, module_id: int) -> dict:
    """收集模块当前内容作为快照"""
    draft = conn.execute(
        "SELECT * FROM module_drafts WHERE module_id=?", (module_id,)
    ).fetchone()
    if not draft:
        return {"module_id": module_id, "text_content": "", "assets": []}

    images = conn.execute(
        "SELECT a.relative_path FROM draft_assets da "
        "JOIN assets a ON da.asset_id=a.id "
        "WHERE da.module_id=? ORDER BY da.order_index", (module_id,)
    ).fetchall()
    from ..config import settings
    asset_paths = [str(settings.assets_dir / r["relative_path"]) for r in images]
    return {
        "module_id": module_id,
        "text_content": draft["text_content"],
        "assets": asset_paths,
    }


@router.post("", response_model=AnalysisOut)
async def create_analysis(body: AnalysisCreate):
    """创建并启动分析"""
    if not body.module_ids:
        raise HTTPException(status_code=400, detail="请至少选择一个模块")

    module_ids = body.module_ids
    with get_db() as conn:
        # 创建分析记录
        cur = conn.execute(
            "INSERT INTO analyses (combination, combination_name, analysis_request, status) "
            "VALUES (?, ?, ?, 'running')",
            (json.dumps(module_ids), body.combination_name, body.analysis_request),
        )
        analysis_id = cur.lastrowid
        conn.execute(
            "UPDATE analyses SET started_at=datetime('now','localtime') WHERE id=?",
            (analysis_id,),
        )

        # 收集模块快照
        snapshots = []
        for idx, mid in enumerate(module_ids):
            snap = _collect_module_snapshot(conn, mid)
            snap["order_index"] = idx
            snap["module_name"] = MODULE_MAP.get(mid, {}).get("name", f"模块{mid}")
            # 保存快照到数据库
            conn.execute(
                "INSERT INTO analysis_snapshots (analysis_id, module_id, order_index, module_name, text_content) "
                "VALUES (?,?,?,?,?)",
                (analysis_id, mid, idx, snap["module_name"], snap["text_content"]),
            )
            # 保存图片快照
            images = conn.execute(
                "SELECT a.id, a.relative_path, a.thumbnail_path FROM draft_assets da "
                "JOIN assets a ON da.asset_id=a.id "
                "WHERE da.module_id=? ORDER BY da.order_index", (mid,)
            ).fetchall()
            for img in images:
                conn.execute(
                    "INSERT INTO analysis_assets (analysis_id, module_id, order_index, asset_id, relative_path, thumbnail_path) "
                    "VALUES (?,?,?,?,?,?)",
                    (analysis_id, mid, idx, img["id"], img["relative_path"], img["thumbnail_path"]),
                )
            snapshots.append(snap)

    # 调用AI（异步）
    result = await call_ai(snapshots, body.analysis_request)

    with get_db() as conn:
        if result["error"]:
            conn.execute(
                "UPDATE analyses SET status='failed', error_message=?, "
                "raw_result=?, completed_at=datetime('now','localtime') WHERE id=?",
                (result["error"], result["raw_result"], analysis_id),
            )
        else:
            conn.execute(
                "UPDATE analyses SET status='completed', result_json=?, "
                "raw_result=?, completed_at=datetime('now','localtime') WHERE id=?",
                (result["result_json"], result["raw_result"], analysis_id),
            )

    return get_analysis_by_id_impl(analysis_id)


def get_analysis_by_id_impl(analysis_id: int) -> AnalysisOut:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM analyses WHERE id=?", (analysis_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="分析记录不存在")
        return AnalysisOut(
            id=row["id"],
            combination=json.loads(row["combination"]),
            combination_name=row["combination_name"] or "",
            analysis_request=row["analysis_request"] or "",
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
    """获取分析结果"""
    return get_analysis_by_id_impl(analysis_id)


@router.get("/{analysis_id}/detail")
def get_analysis_detail(analysis_id: int):
    """获取分析完整详情（含模块快照和图片）"""
    with get_db() as conn:
        analysis = conn.execute(
            "SELECT * FROM analyses WHERE id=?", (analysis_id,)
        ).fetchone()
        if not analysis:
            raise HTTPException(status_code=404, detail="分析记录不存在")

        snapshots = conn.execute(
            "SELECT * FROM analysis_snapshots WHERE analysis_id=? ORDER BY order_index",
            (analysis_id,)
        ).fetchall()

        snap_list = []
        for snap in snapshots:
            images = conn.execute(
                "SELECT relative_path, thumbnail_path FROM analysis_assets "
                "WHERE analysis_id=? AND module_id=? ORDER BY order_index",
                (analysis_id, snap["module_id"])
            ).fetchall()
            snap_list.append({
                "module_id": snap["module_id"],
                "order_index": snap["order_index"],
                "module_name": snap["module_name"],
                "text_content": snap["text_content"],
                "images": [{"relative_path": r["relative_path"],
                           "thumbnail_path": r["thumbnail_path"]} for r in images],
            })

        notes = conn.execute(
            "SELECT * FROM analysis_notes WHERE analysis_id=? ORDER BY created_at DESC",
            (analysis_id,)
        ).fetchall()

        return {
            "analysis": {
                "id": analysis["id"],
                "combination": json.loads(analysis["combination"]),
                "combination_name": analysis["combination_name"] or "",
                "analysis_request": analysis["analysis_request"] or "",
                "status": analysis["status"],
                "result_json": analysis["result_json"],
                "raw_result": analysis["raw_result"],
                "error_message": analysis["error_message"],
                "created_at": analysis["created_at"],
                "started_at": analysis["started_at"],
                "completed_at": analysis["completed_at"],
            },
            "snapshots": snap_list,
            "notes": [{"id": r["id"], "note": r["note"], "created_at": r["created_at"]}
                      for r in notes],
        }


@router.post("/save-to-module")
def save_to_module(body: SaveToModuleRequest):
    """将分析结果保存到9号(AI复盘)或11号(操作建议)模块"""
    if body.module_id not in (9, 11):
        raise HTTPException(status_code=400, detail="只能保存到9号(AI复盘)或11号(操作建议)模块")

    with get_db() as conn:
        # 获取当前草稿内容，追加新内容
        draft = conn.execute(
            "SELECT * FROM module_drafts WHERE module_id=?", (body.module_id,)
        ).fetchone()
        if not draft:
            raise HTTPException(status_code=404, detail="模块不存在")

        # 追加内容（带分隔线）
        existing = draft["text_content"]
        if existing and existing.strip():
            new_text = existing + "\n\n---\n\n" + f"【来自分析 #{body.analysis_id}】\n" + body.content
        else:
            new_text = f"【来自分析 #{body.analysis_id}】\n" + body.content

        conn.execute(
            "UPDATE module_drafts SET text_content=?, revision=revision+1, "
            "updated_at=datetime('now','localtime') WHERE module_id=?",
            (new_text, body.module_id),
        )

    return {"message": "已保存", "revision": draft["revision"] + 1}
