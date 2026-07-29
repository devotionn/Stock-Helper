"""图片处理服务"""
import hashlib
import uuid
import shutil
from pathlib import Path
from io import BytesIO
from PIL import Image
from fastapi import UploadFile, HTTPException
from ..config import settings


def _two_level_prefix(sha256: str) -> str:
    """生成两级前缀目录，如 ab/cd"""
    return f"{sha256[:2]}/{sha256[2:4]}"


def _validate_image(data: bytes) -> tuple[Image.Image, str, str]:
    """验证图片真实格式，返回 (PIL Image, format, mime_type)"""
    try:
        img = Image.open(BytesIO(data))
        img.verify()
        img = Image.open(BytesIO(data))  # verify后需要重新打开
    except Exception:
        raise HTTPException(status_code=400, detail="文件不是有效的图片")

    fmt = (img.format or "").lower()
    if fmt not in settings.allowed_image_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式: {fmt}，仅支持 {', '.join(settings.allowed_image_types)}",
        )

    mime_map = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
                "gif": "image/gif", "bmp": "image/bmp"}
    return img, fmt, mime_map.get(fmt, "application/octet-stream")


def _make_thumbnail(img: Image.Image) -> bytes:
    """生成缩略图"""
    thumb = img.copy()
    thumb.thumbnail((settings.thumbnail_size, settings.thumbnail_size), Image.LANCZOS)
    if thumb.mode in ("RGBA", "P"):
        thumb = thumb.convert("RGB")
    buf = BytesIO()
    thumb.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


async def save_uploaded_image(upload_file: UploadFile) -> dict:
    """完整处理上传图片：验证、存储、生成缩略图，返回图片信息"""
    data = await upload_file.read()
    if len(data) > settings.max_image_size:
        raise HTTPException(status_code=413, detail=f"图片大小超过限制（最大 {settings.max_image_size // 1024 // 1024}MB）")

    img, fmt, mime_type = _validate_image(data)
    width, height = img.size

    if width > settings.max_image_dimension or height > settings.max_image_dimension:
        raise HTTPException(status_code=400, detail=f"图片尺寸过大（最大 {settings.max_image_dimension}px）")

    if width * height > settings.max_total_pixels:
        raise HTTPException(status_code=400, detail="图片总像素超过限制")

    sha256 = hashlib.sha256(data).hexdigest()
    ext = "jpg" if fmt == "jpeg" else fmt
    prefix = _two_level_prefix(sha256)
    filename = f"{sha256}.{ext}"
    rel_path = f"{prefix}/{filename}"
    abs_path = settings.assets_dir / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)

    # 如果已存在相同文件，直接复用；否则先写临时文件再原子rename
    if not abs_path.exists():
        tmp_path = abs_path.with_suffix(abs_path.suffix + ".tmp")
        tmp_path.write_bytes(data)
        tmp_path.replace(abs_path)  # 原子rename

    # 生成缩略图
    thumb_data = _make_thumbnail(img)
    thumb_rel = f"{prefix}/{sha256}_thumb.jpg"
    thumb_abs = settings.assets_dir / thumb_rel
    if not thumb_abs.exists():
        thumb_tmp = thumb_abs.with_suffix(".tmp")
        thumb_tmp.write_bytes(thumb_data)
        thumb_tmp.replace(thumb_abs)

    return {
        "sha256": sha256,
        "original_filename": upload_file.filename,
        "relative_path": rel_path,
        "thumbnail_path": thumb_rel,
        "file_size": len(data),
        "width": width,
        "height": height,
        "mime_type": mime_type,
        "format": fmt,
    }


def get_asset_path(relative_path: str) -> Path:
    """获取图片绝对路径"""
    return settings.assets_dir / relative_path


def safe_delete_asset(relative_path: str, thumbnail_path: str = None):
    """删除图片物理文件"""
    for p in [relative_path, thumbnail_path]:
        if p:
            f = settings.assets_dir / p
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass
