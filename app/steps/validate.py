"""Step5：结果校验。

MVP：基础校验（图片非空 + 尺寸比例≈3:4）。
可选 vision 校验（默认关，由 options.vision_check 开关）列为 v2。
"""
from __future__ import annotations

import io
import logging

from ..llm_client import ImageResult
from ..models import ValidationResult

logger = logging.getLogger(__name__)


def validate_poster(result: ImageResult) -> ValidationResult:
    """基础校验：图片非空 + 解码成功 + 比例接近 3:4。"""
    issues: list[str] = []

    if not result.image_bytes:
        issues.append("生图返回空数据")
        return ValidationResult(passed=False, issues=issues, retry_suggestion="重新生成，检查 API 配置")

    # 用 Pillow 校验解码 + 比例
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(result.image_bytes))
        w, h = img.size
        ratio = h / w if w else 0
        # 3:4 → h/w = 1.333；容忍 ±20%
        if not (1.06 <= ratio <= 1.60):
            issues.append(f"图片比例偏离 3:4（{w}x{h}, h/w={ratio:.2f}）")
        if w < 512 or h < 512:
            issues.append(f"图片分辨率过低（{w}x{h}）")
    except ImportError:
        logger.debug("Pillow 未安装，跳过解码校验")
    except Exception as exc:  # noqa: BLE001
        issues.append(f"图片解码失败: {exc}")
        return ValidationResult(passed=False, issues=issues, retry_suggestion="重新生成")

    passed = len(issues) == 0
    retry = "" if passed else "按上述问题重试，保持风格与文案不变，强化排版与文字可读性"
    logger.info("Step5 校验: passed=%s issues=%d", passed, len(issues))
    return ValidationResult(passed=passed, issues=issues, retry_suggestion=retry)
