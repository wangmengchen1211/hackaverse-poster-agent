"""Step1-6 编排器：串联解析 → 文案 → prompt 组装 → 生图 → 校验 → 后处理 → 持久化/重试。"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

from .llm_client import LLMClient, ImageResult
from .models import (
    GenerateResponse,
    GenerationMeta,
    ImagePlan,
    PosterCopy,
    ProjectBrief,
    ValidationResult,
)
from .skills.image_adapter import adapt_images
from .skills.layout_selector import select_layout
from .steps.copywrite import generate_copy
from .steps.copy_validate import validate_copy
from .steps.image_gen import generate_image
from .steps.overlay import apply_post_processing
from .steps.parse import parse_project
from .steps.prompt_build import build_image_plan
from .steps.validate import validate_poster
from .styles import get_style

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2  # 含首次，最多重试 1 次


@dataclass
class OrchestratorResult:
    response: GenerateResponse
    image_bytes: bytes | None = None
    image_storage_path: str | None = None


async def run_pipeline(
    *,
    prd: str,
    style_key: str,
    project_name: str = "",
    team_name: str = "",
    event_name: str = "",
    image_count: int = 0,
    user_image_paths: list[str] | None = None,
    qr_code_path: str | None = None,
    layout_mode: str = "fixed",
    user_ref: str = "",
    mode: str = "participant",
    user_name: str = "",
    impression: str = "",
    client: LLMClient | None = None,
) -> OrchestratorResult:
    """完整工作流：解析 → 文案 → prompt → 生图 → 后处理(二维码) → 校验 → 持久化。

    mode: participant=选手模式, audience=观众模式
    user_name: 观众姓名/昵称（audience 模式使用）
    impression: 观众感受/印象（audience 模式使用）
    image_count: 用户上传图片数量（0-3），用于图片适配 skill
    qr_code_path: 用户上传的二维码图片路径（可选），程序化贴入右下角
    返回 OrchestratorResult（含 GenerateResponse + 原始图片字节，供接口层上传 Storage）。
    """
    c = client or LLMClient()
    style = get_style(style_key)
    total_t0 = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    meta = GenerationMeta(image_model=c.s.image_model, attempts=1)

    logger.info("=== Pipeline 开始 [request_id=%s] style=%s mode=%s ===", request_id, style_key, mode)

    # ── Step1 + Step2（文本，一次计时）──
    text_t0 = time.time()
    if mode == "audience":
        # 观众模式：跳过 parse，直接生成观众文案
        logger.info("Audience mode: 跳过 Step1 parse，直接生成观众文案")
        brief = ProjectBrief(
            project_name=user_name or "观众",
            event_name=event_name,
        )
    else:
        # 选手模式：正常 parse
        brief = await parse_project(
            prd, project_name=project_name, team_name=team_name, event_name=event_name, client=c
        )
    copy: PosterCopy = await generate_copy(
        brief, style_key, mode=mode, user_name=user_name, event_name=event_name,
        impression=impression, client=c
    )
    meta.text_latency_ms = int((time.time() - text_t0) * 1000)

    # ── Step2.5：文案校验（Copy Validate）──
    copy_validation = validate_copy(copy, brief=brief if mode != "audience" else None, mode=mode)
    if not copy_validation.passed:
        logger.warning("Copy Validate 未通过 [request_id=%s]: %s", request_id, copy_validation.issues)
        # 文案校验未通过：记录问题但继续流程（不阻断，因为图片仍可用）
        # 如果问题严重可以在后续版本中改为阻断
    else:
        logger.info("Copy Validate 通过 [request_id=%s]", request_id)

    # ── Step3：skill + prompt 组装（含中文文字强化规则）──
    image_directive = adapt_images(image_count, style)
    layout_key, layout_prompt = await select_layout(style, layout_mode, client=c)
    plan: ImagePlan = build_image_plan(
        style, copy, layout_key, layout_prompt, image_directive,
        has_qr_code=bool(qr_code_path),
        mode=mode,
    )

    # ── Step4（生图）+ Step5（校验）+ 重试 ──
    last_result: ImageResult | None = None
    last_validation: ValidationResult = ValidationResult()
    attempts = 0
    while attempts < MAX_ATTEMPTS:
        attempts += 1
        meta.attempts = attempts
        img_t0 = time.time()
        try:
            last_result = await generate_image(
                plan,
                user_image_paths=user_image_paths,
                client=c,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Step4 生图失败 (attempt %s)", attempts)
            last_validation = ValidationResult(
                passed=False, issues=[f"生图异常: {exc}"], retry_suggestion="重试或检查 API"
            )
            meta.image_latency_ms = int((time.time() - img_t0) * 1000)
            if attempts < MAX_ATTEMPTS:
                continue
            # 生图彻底失败 → 返回失败响应（文案仍落库）
            meta.validation = last_validation
            meta.total_latency_ms = int((time.time() - total_t0) * 1000)
            return _build_failed_response(
                copy, style_key, layout_key, meta, error=str(exc),
                error_code="IMAGE_GENERATION_FAILED", request_id=request_id,
            )

        meta.image_latency_ms = int((time.time() - img_t0) * 1000)

        # ── Step5.5：后处理（二维码贴图等）──
        if last_result and last_result.image_bytes:
            try:
                last_result = ImageResult(
                    image_bytes=apply_post_processing(
                        last_result.image_bytes,
                        qr_path=qr_code_path,
                    ),
                    value_kind=last_result.value_kind,
                    raw=last_result.raw,
                )
                logger.info("Step5.5 后处理完成（二维码贴图）")
            except Exception as exc:  # noqa: BLE001
                logger.warning("后处理失败（不影响主流程）: %s", exc)

        last_validation = validate_poster(last_result)
        meta.validation = last_validation
        if last_validation.passed or attempts >= MAX_ATTEMPTS:
            break
        # 未通过且有重试机会：把 issues 拼进 prompt 重试
        logger.info("校验未通过，重试: %s", last_validation.issues)
        plan.final_prompt += (
            f"\n\n[重试修复要求]\n上一版问题：{'；'.join(last_validation.issues)}\n"
            f"{last_validation.retry_suggestion}"
        )

    meta.total_latency_ms = int((time.time() - total_t0) * 1000)
    status = "success" if (last_result and last_validation.passed) else "failed"

    resp = GenerateResponse(
        status=status,
        poster_copy=copy,
        style=style_key,
        layout_used=layout_key,
        generation_meta=meta,
        error=None if status == "success" else "；".join(last_validation.issues),
        error_code=None if status == "success" else "IMAGE_GENERATION_FAILED",
        request_id=request_id,
    )
    return OrchestratorResult(
        response=resp,
        image_bytes=last_result.image_bytes if last_result else None,
    )


def _build_failed_response(
    copy: PosterCopy,
    style_key: str,
    layout_key: str,
    meta: GenerationMeta,
    *,
    error: str,
    error_code: str = "IMAGE_GENERATION_FAILED",
    request_id: str = "",
) -> OrchestratorResult:
    resp = GenerateResponse(
        status="failed",
        poster_copy=copy,
        style=style_key,
        layout_used=layout_key,
        generation_meta=meta,
        error=error,
        error_code=error_code,
        request_id=request_id,
    )
    return OrchestratorResult(response=resp, image_bytes=None)
