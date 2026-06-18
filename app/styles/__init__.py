"""风格注册表。

启动时校验所有 reference_image 文件存在（缺失则记录警告，不阻塞启动）。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from .base import StyleDefinition
from .definitions import ALL_STYLES, MEDIA_PREAMBLE

logger = logging.getLogger(__name__)

# references/ 目录：项目根/references/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_REFERENCES_DIR = _PROJECT_ROOT / "references"

STYLE_REGISTRY: dict[str, StyleDefinition] = {s.key: s for s in ALL_STYLES}


def get_style(key: str) -> StyleDefinition:
    """按 key 取风格，不存在抛 KeyError。"""
    if key not in STYLE_REGISTRY:
        raise KeyError(f"未知风格 key: {key}，可选: {list(STYLE_REGISTRY.keys())}")
    return STYLE_REGISTRY[key]


def list_styles() -> list[StyleDefinition]:
    """全部风格（有序）。"""
    return list(ALL_STYLES)


def style_to_public_dict(s: StyleDefinition) -> dict:
    """供 GET /api/styles 返回的精简 dict（不含完整 prompt，避免暴露太多内部）。"""
    return {
        "key": s.key,
        "name": s.name,
        "intro": s.intro,
        "default_layout": s.default_layout,
        "has_reference": reference_exists(s),
    }


def reference_exists(s: StyleDefinition) -> bool:
    return (_REFERENCES_DIR / s.reference_image).exists()


def reference_path(s: StyleDefinition) -> str:
    """返回参考图绝对路径（供 llm_client 传给生图）。"""
    return str(_REFERENCES_DIR / s.reference_image)


def _validate_references() -> None:
    missing = [s.reference_image for s in ALL_STYLES if not reference_exists(s)]
    if missing:
        logger.warning("缺少参考图: %s（在 %s）", missing, _REFERENCES_DIR)
    else:
        logger.info("6 风格参考图全部就绪（%s）", _REFERENCES_DIR)


# 模块加载时校验一次
_validate_references()
