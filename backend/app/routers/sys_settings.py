"""系统设置 API"""
from fastapi import APIRouter
from ..database import get_db
from ..schemas import SettingsUpdate, SettingsOut

router = APIRouter()

SETTING_KEYS = ["ai_api_url", "ai_api_key", "ai_model", "backup_location", "font_size"]


def _mask_api_key(key: str) -> str:
    """对API密钥进行脱敏：显示前2位和后4位，中间用****代替；太短则全部掩码"""
    if not key:
        return ""
    if len(key) <= 6:
        return "****"
    return key[:2] + "****" + key[-4:]


@router.get("", response_model=SettingsOut)
def get_settings():
    """获取系统设置"""
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT key, value FROM settings WHERE key IN ({','.join(['?']*len(SETTING_KEYS))})",
            SETTING_KEYS
        ).fetchall()
        cfg = {r["key"]: r["value"] for r in rows}
    api_key = cfg.get("ai_api_key", "") or ""
    return SettingsOut(
        ai_api_url=cfg.get("ai_api_url", ""),
        has_api_key=bool(api_key.strip()),
        masked_api_key=_mask_api_key(api_key),
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
            if val is None:
                continue
            # ai_api_key 为空字符串时不更新（保留原值），只有非空时才更新
            if key == "ai_api_key" and val == "":
                continue
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) "
                "VALUES (?, ?, datetime('now','localtime')) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "updated_at=excluded.updated_at",
                (key, val),
            )
    return {"message": "设置已保存"}
