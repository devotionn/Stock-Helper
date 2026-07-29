"""Pydantic 请求/响应模型"""
from pydantic import BaseModel
from typing import Optional


# ---- 模块 ----
class ModuleDraftUpdate(BaseModel):
    text_content: str
    revision: int


class ModuleDraftOut(BaseModel):
    module_id: int
    module_name: str
    module_desc: str
    text_content: str
    revision: int
    updated_at: str
    image_count: int = 0
    text_summary: str = ""


class ModuleCardOut(BaseModel):
    module_id: int
    module_name: str
    module_desc: str
    has_content: bool
    text_summary: str
    image_count: int
    updated_at: str


class ModuleVersionCreate(BaseModel):
    note: str = ""


class ModuleVersionOut(BaseModel):
    id: int
    module_id: int
    text_content: str
    source: str
    note: str
    created_at: str
    image_count: int = 0


# ---- 图片 ----
class AssetOut(BaseModel):
    id: int
    sha256: str
    original_filename: Optional[str]
    relative_path: str
    thumbnail_path: Optional[str]
    file_size: int
    width: Optional[int]
    height: Optional[int]
    order_index: int = 0
    caption: str = ""


class AssetCaptionUpdate(BaseModel):
    caption: str = ""
    order_index: Optional[int] = None


# ---- 组合 ----
class CombinationCreate(BaseModel):
    name: str
    module_ids: list[int]


class CombinationOut(BaseModel):
    id: int
    name: str
    module_ids: list[int]
    created_at: str
    updated_at: str


# ---- 分析 ----
class AnalysisCreate(BaseModel):
    module_ids: list[int]
    analysis_request: str = ""
    combination_name: str = ""


class AnalysisResultItem(BaseModel):
    title: str
    content: str


class AnalysisOut(BaseModel):
    id: int
    combination: list[int]
    combination_name: str
    analysis_request: str
    status: str
    result_json: Optional[str]
    raw_result: Optional[str]
    error_message: Optional[str]
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]


class SaveToModuleRequest(BaseModel):
    analysis_id: int
    module_id: int  # 9 或 11
    content: str


# ---- 历史 ----
class HistoryQuery(BaseModel):
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    combination_name: Optional[str] = None
    stock_name: Optional[str] = None
    module_id: Optional[int] = None
    keyword: Optional[str] = None


class AnalysisNoteUpdate(BaseModel):
    note: str


# ---- 设置 ----
class SettingsUpdate(BaseModel):
    ai_api_url: Optional[str] = None
    ai_api_key: Optional[str] = None
    ai_model: Optional[str] = None
    backup_location: Optional[str] = None
    font_size: Optional[str] = None


class SettingsOut(BaseModel):
    ai_api_url: str
    has_api_key: bool
    masked_api_key: str
    ai_model: str
    backup_location: str
    font_size: str


# ---- 备份 ----
class BackupResult(BaseModel):
    success: bool
    path: str
    file_count: int
    total_size: int
    message: str
