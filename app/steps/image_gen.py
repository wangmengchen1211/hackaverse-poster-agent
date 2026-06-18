"""Step4：调用 gpt-image-2 生图（单次直接生成）。

优先级：
1. 有用户上传照片 → /images/edits（把照片作为输入图传给模型编辑）
2. 无用户照片   → /images/generations（纯文生图）

注意：风格参考图（references/*.jpg）暂不传给 gpt-image-2。
"""
from __future__ import annotations

import logging
import os

from ..llm_client import LLMClient, ImageResult
from ..models import ImagePlan

logger = logging.getLogger(__name__)


async def generate_image(
    plan: ImagePlan,
    *,
    user_image_paths: list[str] | None = None,
    client: LLMClient | None = None,
) -> ImageResult:
    """按 ImagePlan 调用生图（单次直接生成）。

    user_image_paths: 用户上传照片的本地路径列表（0-3张）。
                      有值时优先走 /images/edits，把照片传给模型。
    """
    c = client or LLMClient()

    # 过滤出实际存在的用户照片路径
    valid_user_images: list[str] = []
    if user_image_paths:
        for p in user_image_paths:
            if os.path.exists(p):
                valid_user_images.append(p)
            else:
                logger.warning("用户照片不存在，跳过: %s", p)

    # 根据是否有用户照片选择端点
    if valid_user_images:
        logger.info("有 %d 张用户照片，尝试使用 /images/edits 融入海报", len(valid_user_images))
        result = await c.generate_image(
            prompt=plan.final_prompt,
            reference_image_paths=valid_user_images,
            size=plan.size,
        )
        if result.edits_used:
            logger.info("✅ 用户照片已通过 /images/edits 融入海报")
        else:
            logger.warning(
                "❌ 用户照片未能融入海报！/images/edits 失败，已退化为纯文生图。"
                "请检查 llm_client 日志中的错误详情。"
            )
    else:
        logger.info("无用户照片，使用 /images/generations 纯文生图")
        result = await c.generate_image(
            prompt=plan.final_prompt,
            reference_image_paths=None,
            size=plan.size,
        )

    logger.info("生图完成: bytes=%d", len(result.image_bytes))
    return result
