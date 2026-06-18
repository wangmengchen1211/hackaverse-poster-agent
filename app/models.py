"""poster-agent 数据模型。

对应 PRD（附件）中的结构：
- ProjectBrief  ← Step1 输出
- PosterCopy    ← Step2 输出（每栏目 body ≤200 字）
- ImagePlan     ← Step3 输出（final_prompt + 参考图）
- ValidationResult ← Step5 输出
- GenerateResponse / PosterRecord ← 接口/DB
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Step1：项目摘要 ──
class ProjectBrief(BaseModel):
    project_name: str = ""
    team_name: str = ""
    target_user: str = ""
    core_problem: str = ""
    core_solution: str = ""
    main_value: str = ""
    features: list[str] = Field(default_factory=list)
    event_name: str = ""
    fun_points: list[str] = Field(default_factory=list)
    visual_direction: str = ""


# ── Step2：海报文案 ──
class Column(BaseModel):
    title: str
    body: str = Field(..., description="正文，≤200 中文字符")


class PosterCopy(BaseModel):
    poster_name: str = ""
    issue_label: str = ""
    date: str = ""
    headline: str = ""
    subheadline: str = ""
    tags: list[str] = Field(default_factory=list)
    columns: list[Column] = Field(default_factory=list, min_length=3, max_length=3)
    easter_egg: str = ""
    editor_comment: str = ""
    share_line: str = ""
    # Fact Lock 字段（选手模式由 LLM 输出，便于调试和校验）
    used_facts: list[str] = Field(
        default_factory=list,
        description="文案中使用的来自 ProjectBrief 的事实点",
    )
    creative_angles: list[str] = Field(
        default_factory=list,
        description="文案中使用的创意角度/比喻，便于调试",
    )


# ── Step3：生图计划 ──
class ImagePlan(BaseModel):
    style_key: str
    style_name: str
    layout_mode: str = Field(..., description="A / B / C / generate-xxx")
    final_prompt: str
    negative_prompt: str = ""
    reference_image: str | None = None  # references/ 下相对路径
    size: str = "1024x1536"
    image_directives: dict[str, Any] = Field(
        default_factory=dict,
        description="skill 输出的图片布局/转化指令（main_image_prompt 等）",
    )
    has_qr_code: bool = False         # 用户是否上传了二维码
    has_user_images: bool = False     # 用户是否上传了照片


# ── Step5：校验 ──
class ValidationResult(BaseModel):
    passed: bool = True
    issues: list[str] = Field(default_factory=list)
    retry_suggestion: str = ""


# ── 接口响应 ──
class GenerationMeta(BaseModel):
    image_model: str = ""
    attempts: int = 1
    text_latency_ms: int = 0
    image_latency_ms: int = 0
    total_latency_ms: int = 0
    validation: ValidationResult = Field(default_factory=ValidationResult)


class GenerateResponse(BaseModel):
    status: str = "success"  # success / failed
    poster_id: str | None = None
    image_url: str = ""
    poster_copy: PosterCopy
    style: str
    layout_used: str
    generation_meta: GenerationMeta = Field(default_factory=GenerationMeta)
    error: str | None = None
    error_code: str | None = None
    request_id: str = ""


# ── 历史列表项（精简）──
class PosterListItem(BaseModel):
    id: str
    created_at: str
    project_name: str | None = None
    style: str
    image_url: str
    headline: str = ""

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PosterListItem":
        copy = row.get("poster_copy") or {}
        return cls(
            id=str(row.get("id", "")),
            created_at=str(row.get("created_at", "")),
            project_name=row.get("project_name"),
            style=row.get("style", ""),
            image_url=row.get("image_url", ""),
            headline=(copy.get("headline") if isinstance(copy, dict) else "") or "",
        )
