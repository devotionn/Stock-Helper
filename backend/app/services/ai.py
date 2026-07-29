"""AI 供应商适配层。"""
from __future__ import annotations

import base64
import json
import mimetypes
import re
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx
from PIL import Image

from ..config import settings
from ..database import get_db
from .secret_store import get_secret_store

SYSTEM_PROMPT = """你是一个专业的股票分析助手。你将收到同一个投研日期下、按用户指定顺序排列的多个模块内容（文字和图片）。

请严格按照以下7个部分输出分析结果，使用JSON格式：
{
  "信息汇总": "将所选模块内容归纳整理",
  "一致观点": "各模块中相互印证的看法",
  "冲突观点": "各模块中相互矛盾的看法",
  "关键判断": "基于信息得出的核心结论",
  "风险提示": "潜在风险点",
  "信息不足之处": "哪些信息缺失或不够清晰",
  "操作参考建议": "笼统的操作方向参考"
}

重要规范：
1. 必须区分投研日期、模块名称和股票名称，不得把不同日期的信息混为一谈
2. 不得虚构股票价格、政策、财务数据或图片中看不清的信息
3. 当图片不清楚或信息不足时，必须明确提示无法确认
4. 分析结果仅供参考，不构成投资建议
5. 每个部分的内容用中文，详细但不冗余"""


def get_ai_config() -> dict:
    """获取 AI 配置：API 密钥从 SecretStore 读取，其余从数据库读取。"""
    secret_store = get_secret_store()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE key IN ('ai_api_url', 'ai_model')"
        ).fetchall()
        config = {row["key"]: row["value"] for row in rows}
    return {
        "api_url": config.get("ai_api_url", ""),
        "api_key": secret_store.get_secret("ai_api_key") or "",
        "model": config.get("ai_model", ""),
    }


def _image_to_data_uri(file_path: str) -> str:
    path = Path(file_path)
    if not path.exists():
        return ""
    mime_type, _ = mimetypes.guess_type(str(path))
    mime_type = mime_type or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def compress_image_for_ai(file_path: str) -> str:
    """压缩图片供 AI 分析；原文件不变。"""
    path = Path(file_path)
    if not path.exists():
        return ""
    if path.stat().st_size < 500 * 1024:
        return _image_to_data_uri(file_path)

    try:
        with Image.open(str(path)) as source:
            image = source.copy()
        max_edge = settings.ai_image_max_long_edge
        width, height = image.size
        if max(width, height) > max_edge:
            if width >= height:
                new_size = (max_edge, int(height * max_edge / width))
            else:
                new_size = (int(width * max_edge / height), max_edge)
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=settings.ai_image_quality)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"
    except Exception:
        return _image_to_data_uri(file_path)


def build_analysis_input(
    module_snapshots: list[dict],
    analysis_request: str,
) -> list[dict]:
    """构建包含投研日期、股票标题、文字和图片的多模态输入。"""
    content: list[dict] = []
    image_count = 0
    max_images = settings.ai_max_images

    record_dates = {
        snapshot.get("record_date")
        for snapshot in module_snapshots
        if snapshot.get("record_date")
    }
    if record_dates:
        content.append(
            {
                "type": "text",
                "text": "【本次投研日期】\n" + "、".join(sorted(record_dates)),
            }
        )

    for snapshot in module_snapshots:
        module_number = int(snapshot.get("order_index", 0)) + 1
        module_name = snapshot.get("module_name") or f"模块{module_number}"
        display_title = (snapshot.get("display_title") or "").strip()
        header = f"【模块{module_number}：{module_name}】"
        if display_title:
            header += f"\n【股票名称/标的：{display_title}】"
        text = snapshot.get("text_content") or "（无文字内容）"
        content.append({"type": "text", "text": f"{header}\n{text}"})

        for asset_path in snapshot.get("assets", []):
            if image_count >= max_images:
                break
            data_uri = compress_image_for_ai(asset_path)
            if data_uri:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": data_uri},
                    }
                )
                image_count += 1

    if analysis_request:
        content.append(
            {
                "type": "text",
                "text": f"【本次分析要求】\n{analysis_request}",
            }
        )
    return content


async def call_ai(module_snapshots: list[dict], analysis_request: str) -> dict:
    """调用 AI API，返回结构化结果、原文或明确错误。"""
    config = get_ai_config()
    if not config["api_url"] or not config["api_key"] or not config["model"]:
        return {
            "result_json": None,
            "raw_result": None,
            "error": "AI接口未配置，请在系统设置中填写API地址、密钥和模型名称",
        }

    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_analysis_input(module_snapshots, analysis_request),
            },
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.ai_timeout) as client:
            response = await client.post(config["api_url"], json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        try:
            raw_text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return {
                "result_json": None,
                "raw_result": str(data),
                "error": "AI返回格式异常",
            }

        result_json = parse_ai_result(raw_text)
        if result_json is None:
            return {
                "result_json": None,
                "raw_result": raw_text,
                "error": None,
                "warning": "AI返回结果格式不完整",
            }
        return {
            "result_json": result_json,
            "raw_result": raw_text,
            "error": None,
        }
    except httpx.TimeoutException:
        return {
            "result_json": None,
            "raw_result": None,
            "error": f"AI请求超时（{settings.ai_timeout}秒）",
        }
    except httpx.HTTPStatusError as exc:
        return {
            "result_json": None,
            "raw_result": None,
            "error": (
                f"AI接口返回错误: {exc.response.status_code} - "
                f"{exc.response.text[:200]}"
            ),
        }
    except Exception as exc:
        return {
            "result_json": None,
            "raw_result": None,
            "error": f"AI调用失败: {exc}",
        }


def parse_ai_result(text: str) -> Optional[str]:
    """从 AI 返回文本中提取 JSON。"""
    try:
        return json.dumps(json.loads(text), ensure_ascii=False)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.dumps(json.loads(fenced.group(1)), ensure_ascii=False)
        except json.JSONDecodeError:
            pass

    object_match = re.search(r"\{.*\}", text, re.DOTALL)
    if object_match:
        try:
            return json.dumps(json.loads(object_match.group(0)), ensure_ascii=False)
        except json.JSONDecodeError:
            pass
    return None
