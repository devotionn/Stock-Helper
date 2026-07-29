"""系统设置 API"""
from fastapi import APIRouter
from ..database import get_db
from ..schemas import SettingsUpdate, SettingsOut

router = APIRouter()

SETTING_KEYS = ["ai_api_url", "ai_api_key", "ai_model", "backup_location", "font_size"]


@router.get("", response_model=SettingsOut)
def get_settings():
    """获取系统设置"""
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT key, value FROM settings WHERE key IN ({','.join(['?']*len(SETTING_KEYS))})",
            SETTING_KEYS
        ).fetchall()
        cfg = {r["key"]: r["value"] for r in rows}
    return SettingsOut(
        ai_api_url=cfg.get("ai_api_url", ""),
        ai_api_key=cfg.get("ai_api_key", ""),
        ai_model=cfg.get("ai_model", ""),
        backup_location=cfg.get("backup_location", ""),
        font_size=cfg.get("font_size", "18"),
    )


@router.put("")
def update_settings(body: SettingsUpdate):
    """更新系统设置"""
    with get_db() as conn:
        for key in SETTING_KEYS:
            val = getattr(body, key, None)
            if val is not None:
                conn.execute(
                    "INSERT INTO settings (key, value, updated_at) "
                    "VALUES (?, ?, datetime('now','localtime')) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                    "updated_at=excluded.updated_at",
                    (key, val),
                )
    return {"message": "设置已保存"}
