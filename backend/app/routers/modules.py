"""模块 CRUD + 图片管理 API"""
import json
from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
from ..database import get_db
from ..config import settings, MODULES
from ..schemas import (
    ModuleDraftUpdate, ModuleDraftOut, ModuleCardOut,
    ModuleVersionCreate, ModuleVersionOut,
    AssetOut, AssetCaptionUpdate,
)
from ..services.image import save_uploaded_image, get_asset_path

router = APIRouter()

MODULE_MAP = {m["id"]: m for m in MODULES}


def _text_summary(text: str, max_len: int = 50) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    text = text.replace("\n", " ")
    return text[:max_len] + ("..." if len(text) > max_len else "")


@router.get("", response_model=list[ModuleCardOut])
def list_module_cards():
    """获取12个模块的首页卡片信息"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM module_drafts ORDER BY module_id"
        ).fetchall()
        result = []
        for row in rows:
            mid = row["module_id"]
            img_count = conn.execute(
                "SELECT COUNT(*) FROM draft_assets WHERE module_id=?", (mid,)
            ).fetchone()[0]
            m = MODULE_MAP.get(mid, {})
            result.append(ModuleCardOut(
                module_id=mid,
                module_name=m.get("name", ""),
                module_desc=m.get("desc", ""),
                has_content=bool(row["text_content"].strip()) or img_count > 0,
                text_summary=_text_summary(row["text_content"]),
                image_count=img_count,
                updated_at=row["updated_at"],
            ))
    return result


@router.get("/{module_id}", response_model=ModuleDraftOut)
def get_module_draft(module_id: int):
    """获取模块草稿内容"""
    if module_id not in MODULE_MAP:
        raise HTTPException(status_code=404, detail="模块不存在")
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM module_drafts WHERE module_id=?", (module_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="模块不存在")
        img_count = conn.execute(
            "SELECT COUNT(*) FROM draft_assets WHERE module_id=?", (module_id,)
        ).fetchone()[0]
        m = MODULE_MAP[module_id]
        return ModuleDraftOut(
            module_id=module_id,
            module_name=m["name"],
            module_desc=m["desc"],
            text_content=row["text_content"],
            revision=row["revision"],
            updated_at=row["updated_at"],
            image_count=img_count,
            text_summary=_text_summary(row["text_content"]),
        )


@router.put("/{module_id}")
def update_module_draft(module_id: int, body: ModuleDraftUpdate):
    """更新模块草稿文字（带并发覆盖保护）"""
    if module_id not in MODULE_MAP:
        raise HTTPException(status_code=404, detail="模块不存在")
    with get_db() as conn:
        row = conn.execute(
            "SELECT revision FROM module_drafts WHERE module_id=?", (module_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="模块不存在")
        if body.revision != row["revision"]:
            raise HTTPException(
                status_code=409,
                detail="内容已在另一个页面更新，请先刷新",
            )
        conn.execute(
            "UPDATE module_drafts SET text_content=?, revision=revision+1, "
            "updated_at=datetime('now', 'localtime') WHERE module_id=?",
            (body.text_content, module_id),
        )
    return {"revision": body.revision + 1, "message": "保存成功"}


# ---- 图片管理 ----

@router.get("/{module_id}/images", response_model=list[AssetOut])
def get_module_images(module_id: int):
    """获取模块的图片列表"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT a.*, da.order_index, da.caption FROM draft_assets da "
            "JOIN assets a ON da.asset_id=a.id "
            "WHERE da.module_id=? ORDER BY da.order_index", (module_id,)
        ).fetchall()
        return [AssetOut(
            id=r["id"], sha256=r["sha256"],
            original_filename=r["original_filename"],
            relative_path=r["relative_path"], thumbnail_path=r["thumbnail_path"],
            file_size=r["file_size"], width=r["width"], height=r["height"],
            order_index=r["order_index"], caption=r["caption"],
        ) for r in rows]


@router.post("/{module_id}/images", response_model=AssetOut)
async def upload_module_image(module_id: int, file: UploadFile = File(...)):
    """上传图片到模块"""
    if module_id not in MODULE_MAP:
        raise HTTPException(status_code=404, detail="模块不存在")
    info = await save_uploaded_image(file)
    with get_db() as conn:
        # 插入或复用asset
        existing = conn.execute(
            "SELECT id FROM assets WHERE sha256=?", (info["sha256"],)
        ).fetchone()
        if existing:
            asset_id = existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO assets (sha256, original_filename, relative_path, "
                "thumbnail_path, file_size, width, height, mime_type, format) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (info["sha256"], info["original_filename"], info["relative_path"],
                 info["thumbnail_path"], info["file_size"], info["width"],
                 info["height"], info["mime_type"], info["format"]),
            )
            asset_id = cur.lastrowid

        # 检查是否已存在相同(module_id, asset_id)，存在则跳过（防止重复添加）
        existing_draft = conn.execute(
            "SELECT order_index FROM draft_assets WHERE module_id=? AND asset_id=?",
            (module_id, asset_id),
        ).fetchone()
        if existing_draft:
            return AssetOut(
                id=asset_id, sha256=info["sha256"],
                original_filename=info["original_filename"],
                relative_path=info["relative_path"], thumbnail_path=info["thumbnail_path"],
                file_size=info["file_size"], width=info["width"], height=info["height"],
                order_index=existing_draft["order_index"], caption="",
            )

        # 获取当前最大order_index
        max_order = conn.execute(
            "SELECT MAX(order_index) FROM draft_assets WHERE module_id=?", (module_id,)
        ).fetchone()[0] or 0

        conn.execute(
            "INSERT INTO draft_assets (module_id, asset_id, order_index, caption) "
            "VALUES (?,?,?, '')",
            (module_id, asset_id, max_order + 1),
        )
    return AssetOut(
        id=asset_id, sha256=info["sha256"],
        original_filename=info["original_filename"],
        relative_path=info["relative_path"], thumbnail_path=info["thumbnail_path"],
        file_size=info["file_size"], width=info["width"], height=info["height"],
        order_index=max_order + 1, caption="",
    )


@router.delete("/{module_id}/images/{asset_id}")
def delete_module_image(module_id: int, asset_id: int):
    """从模块草稿中移除图片（不删除物理文件，如被历史引用则保留）"""
    with get_db() as conn:
        conn.execute(
            "DELETE FROM draft_assets WHERE module_id=? AND asset_id=?",
            (module_id, asset_id),
        )
        # 检查是否仍被其他地方引用
        refs = conn.execute(
            "SELECT COUNT(*) FROM draft_assets WHERE asset_id=? "
            "UNION ALL SELECT COUNT(*) FROM version_assets WHERE asset_id=? "
            "UNION ALL SELECT COUNT(*) FROM analysis_assets WHERE asset_id=?",
            (asset_id, asset_id, asset_id)
        ).fetchall()
        total_refs = sum(r[0] for r in refs)
        if total_refs == 0:
            # 标记为orphan
            conn.execute(
                "UPDATE assets SET is_orphan=1, orphan_since=datetime('now','localtime') "
                "WHERE id=?", (asset_id,)
            )
    return {"message": "已移除"}


@router.put("/{module_id}/images/{asset_id}")
def update_image_caption(module_id: int, asset_id: int, body: AssetCaptionUpdate):
    """更新图片说明文字或顺序"""
    with get_db() as conn:
        if body.order_index is not None:
            conn.execute(
                "UPDATE draft_assets SET caption=?, order_index=? "
                "WHERE module_id=? AND asset_id=?",
                (body.caption, body.order_index, module_id, asset_id),
            )
        else:
            conn.execute(
                "UPDATE draft_assets SET caption=? WHERE module_id=? AND asset_id=?",
                (body.caption, module_id, asset_id),
            )
    return {"message": "已更新"}


@router.put("/{module_id}/images/reorder")
def reorder_images(module_id: int, asset_ids: list[int]):
    """重新排序模块图片"""
    with get_db() as conn:
        for idx, aid in enumerate(asset_ids):
            conn.execute(
                "UPDATE draft_assets SET order_index=? WHERE module_id=? AND asset_id=?",
                (idx + 1, module_id, aid),
            )
    return {"message": "排序已更新"}


# ---- 版本管理 ----

@router.post("/{module_id}/versions", response_model=ModuleVersionOut)
def save_module_version(module_id: int, body: ModuleVersionCreate):
    """保存模块版本快照"""
    if module_id not in MODULE_MAP:
        raise HTTPException(status_code=404, detail="模块不存在")
    with get_db() as conn:
        draft = conn.execute(
            "SELECT * FROM module_drafts WHERE module_id=?", (module_id,)
        ).fetchone()
        if not draft:
            raise HTTPException(status_code=404, detail="模块不存在")
        cur = conn.execute(
            "INSERT INTO module_versions (module_id, text_content, source, note) "
            "VALUES (?, ?, 'user', ?)",
            (module_id, draft["text_content"], body.note),
        )
        version_id = cur.lastrowid
        # 复制图片关联
        images = conn.execute(
            "SELECT asset_id, order_index, caption FROM draft_assets WHERE module_id=? "
            "ORDER BY order_index", (module_id,)
        ).fetchall()
        for img in images:
            conn.execute(
                "INSERT INTO version_assets (module_version_id, asset_id, order_index, caption) "
                "VALUES (?,?,?,?)",
                (version_id, img["asset_id"], img["order_index"], img["caption"]),
            )
        # 重新查询获取真实created_at
        version_row = conn.execute(
            "SELECT created_at FROM module_versions WHERE id=?", (version_id,)
        ).fetchone()
        created_at = version_row["created_at"] if version_row else ""
        return ModuleVersionOut(
            id=version_id, module_id=module_id,
            text_content=draft["text_content"], source="user",
            note=body.note, created_at=created_at,
            image_count=len(images),
        )


@router.get("/{module_id}/versions", response_model=list[ModuleVersionOut])
def list_module_versions(module_id: int):
    """列出模块的历史版本"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT v.*, (SELECT COUNT(*) FROM version_assets WHERE module_version_id=v.id) as img_count "
            "FROM module_versions v WHERE v.module_id=? ORDER BY v.created_at DESC",
            (module_id,)
        ).fetchall()
        return [ModuleVersionOut(
            id=r["id"], module_id=r["module_id"],
            text_content=r["text_content"], source=r["source"],
            note=r["note"], created_at=r["created_at"],
            image_count=r["img_count"],
        ) for r in rows]
