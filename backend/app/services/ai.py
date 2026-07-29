"""AI 供应商适配层"""
import json
import base64
import mimetypes
from pathlib import Path
from io import BytesIO
import httpx
import asyncio
from typing import Optional
from PIL import Image
from ..config import settings
from ..database import get_db
from .secret_store import get_secret_store

# 固定系统提示词
SYSTEM_PROMPT = """你是一个专业的股票分析助手。你将收到用户选择的多个模块的内容（文字和图片），按照模块排列顺序进行分析。

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
1. 不得虚构股票价格、政策、财务数据或图片中看不清的信息
2. 当图片不清楚或信息不足时，必须明确提示无法确认
3. 分析结果仅供参考，不构成投资建议
4. 每个部分的内容用中文，详细但不冗余"""


def get_ai_config() -> dict:
    """获取AI配置：API密钥从SecretStore读取，其余从数据库"""
    secret_store = get_secret_store()
    with get_db() as conn:
        row = conn.execute(
            "SELECT key, value FROM settings WHERE key IN ('ai_api_url', 'ai_model')"
        ).fetchall()
        cfg = {r["key"]: r["value"] for r in row}
    return {
        "api_url": cfg.get("ai_api_url", ""),
        "api_key": secret_store.get_secret("ai_api_key") or "",
        "model": cfg.get("ai_model", ""),
    }


def _image_to_data_uri(file_path: str) -> str:
    """将本地图片文件转为 base64 data URI，供远程AI API读取"""
    path = Path(file_path)
    if not path.exists():
        return ""
    mime, _ = mimetypes.guess_type(str(path))
    if mime is None:
        mime = "image/jpeg"
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def compress_image_for_ai(file_path: str) -> str:
    """压缩图片供AI分析：最长边压缩到设定像素，转为JPEG质量85，返回base64 data URI。
    如果图片已经较小（<500KB）则直接读取为base64不压缩。"""
    path = Path(file_path)
    if not path.exists():
        return ""

    # 如果图片已经较小（<500KB），直接读取为base64不压缩
    file_size = path.stat().st_size
    if file_size < 500 * 1024:
        return _image_to_data_uri(file_path)

    try:
        img = Image.open(str(path))
        # 最长边压缩
        max_edge = settings.ai_image_max_long_edge
        w, h = img.size
        if max(w, h) > max_edge:
            if w >= h:
                new_w = max_edge
                new_h = int(h * max_edge / w)
            else:
                new_h = max_edge
                new_w = int(w * max_edge / h)
            img = img.resize((new_w, new_h), Image.LANCZOS)
        # 转为RGB（JPEG不支持透明通道）
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=settings.ai_image_quality)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception:
        # 压缩失败则回退到直接读取
        return _image_to_data_uri(file_path)


def build_analysis_input(module_snapshots: list[dict], analysis_request: str, asset_paths: list[str]) -> list[dict]:
    """构建AI输入消息内容"""
    content = []
    image_count = 0
    max_images = settings.ai_max_images

    for snap in module_snapshots:
        # 文字始终添加（不受图片数量限制影响）
        content.append({
            "type": "text",
            "text": f"【模块{snap['order_index']+1}：{snap['module_name']}】\n{snap['text_content'] or '（无文字内容）'}"
        })
        # 添加该模块的图片（压缩后转为 base64 data URI），限制总数量
        for asset_path in snap.get("assets", []):
            if image_count >= max_images:
                break
            data_uri = compress_image_for_ai(asset_path)
            if data_uri:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": data_uri}
                })
                image_count += 1

    # 分析要求始终添加
    if analysis_request:
        content.append({
            "type": "text",
            "text": f"【本次分析要求】\n{analysis_request}"
        })

    return content


async def call_ai(module_snapshots: list[dict], analysis_request: str) -> dict:
    """调用AI API进行分析，返回 {result_json, raw_result, error}"""
    cfg = get_ai_config()
    if not cfg["api_url"] or not cfg["api_key"] or not cfg["model"]:
        return {
            "result_json": None,
            "raw_result": None,
            "error": "AI接口未配置，请在系统设置中填写API地址、密钥和模型名称",
        }

    # 收集所有图片路径
    asset_paths = []
    for snap in module_snapshots:
        for asset in snap.get("assets", []):
            asset_paths.append(asset)

    content = build_analysis_input(module_snapshots, analysis_request, asset_paths)

    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }

    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.ai_timeout) as client:
            response = await client.post(cfg["api_url"], json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        # 提取AI返回文本
        raw_text = ""
        try:
            raw_text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            return {"result_json": None, "raw_result": str(data),
                    "error": "AI返回格式异常"}

        # 尝试解析JSON
        result_json = parse_ai_result(raw_text)

        if result_json is None:
            # JSON解析失败，返回警告但保留原文
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
        return {"result_json": None, "raw_result": None,
                "error": f"AI请求超时（{settings.ai_timeout}秒）"}
    except httpx.HTTPStatusError as e:
        return {"result_json": None, "raw_result": None,
                "error": f"AI接口返回错误: {e.response.status_code} - {e.response.text[:200]}"}
    except Exception as e:
        return {"result_json": None, "raw_result": None,
                "error": f"AI调用失败: {str(e)}"}


def parse_ai_result(text: str) -> Optional[str]:
    """尝试从AI返回文本中提取JSON结果"""
    # 尝试直接解析
    try:
        result = json.loads(text)
        return json.dumps(result, ensure_ascii=False)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 块
    import re
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(1))
            return json.dumps(result, ensure_ascii=False)
        except json.JSONDecodeError:
            pass

    # 尝试提取第一个 { ... } 块
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(0))
            return json.dumps(result, ensure_ascii=False)
        except json.JSONDecodeError:
            pass

    return None
