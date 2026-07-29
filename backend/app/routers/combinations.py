"""常用组合管理 API"""
import json
from fastapi import APIRouter, HTTPException
from ..database import get_db
from ..schemas import CombinationCreate, CombinationOut

router = APIRouter()


@router.get("", response_model=list[CombinationOut])
def list_combinations():
    """获取所有常用组合"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM combinations ORDER BY updated_at DESC"
        ).fetchall()
        return [CombinationOut(
            id=r["id"], name=r["name"],
            module_ids=json.loads(r["module_ids"]),
            created_at=r["created_at"], updated_at=r["updated_at"],
        ) for r in rows]


@router.post("", response_model=CombinationOut)
def create_combination(body: CombinationCreate):
    """创建常用组合"""
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO combinations (name, module_ids) VALUES (?, ?)",
            (body.name, json.dumps(body.module_ids)),
        )
        cid = cur.lastrowid
        row = conn.execute(
            "SELECT * FROM combinations WHERE id=?", (cid,)
        ).fetchone()
        return CombinationOut(
            id=row["id"], name=row["name"],
            module_ids=json.loads(row["module_ids"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )


@router.put("/{combination_id}", response_model=CombinationOut)
def update_combination(combination_id: int, body: CombinationCreate):
    """更新常用组合"""
    with get_db() as conn:
        conn.execute(
            "UPDATE combinations SET name=?, module_ids=?, "
            "updated_at=datetime('now','localtime') WHERE id=?",
            (body.name, json.dumps(body.module_ids), combination_id),
        )
        row = conn.execute(
            "SELECT * FROM combinations WHERE id=?", (combination_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="组合不存在")
        return CombinationOut(
            id=row["id"], name=row["name"],
            module_ids=json.loads(row["module_ids"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )


@router.delete("/{combination_id}")
def delete_combination(combination_id: int):
    """删除常用组合"""
    with get_db() as conn:
        conn.execute("DELETE FROM combinations WHERE id=?", (combination_id,))
    return {"message": "已删除"}
