"""Skill 1：图片适配。

输入：用户上传的图片数量（0-3）+ 所选风格
输出：图片处理 prompt 片段（主图转化规则 + 多图分散布局策略）

核心原则（来自《image prompt template》+ 用户要求）：
- 用户图片必须按风格转化，不能原样贴图
- 多图分散到不同分栏/角标，不堆在一处
- 图片只作新闻配图，不可铺满背景，不可压正文
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..styles import StyleDefinition

logger = logging.getLogger(__name__)


@dataclass
class ImageDirective:
    """图片适配 skill 的输出，供 prompt_build 拼装。"""
    has_images: bool
    image_count: int
    placement_rules: str       # 图片放置规则段（拼入 prompt）
    transform_rules: str       # 风格化转化规则段（拼入 prompt）


def adapt_images(image_count: int, style: StyleDefinition) -> ImageDirective:
    """根据图片数量 + 风格，输出图片处理 prompt 片段。

    image_count: 0-3（接口层已限制上限）
    """
    n = max(0, min(3, image_count))
    has_img = n > 0

    if not has_img:
        return ImageDirective(
            has_images=False,
            image_count=0,
            placement_rules="本次无用户上传图片。主新闻图片请根据项目主题自行生成符合风格的新闻配图。",
            transform_rules="",
        )

    placement = _placement_strategy(n)
    transform = _transform_strategy(style)

    # 明确告知模型收到了用户照片
    image_note = (
        f"重要提示：本次通过 /images/edits 收到了用户上传的 {n} 张照片。\n"
        "模型必须将这些照片的内容融入到报纸版面中，不要忽略输入图片。\n"
        "照片中的人物、场景或物品应作为报纸的新闻配图素材被保留和转化。"
    )

    return ImageDirective(
        has_images=True,
        image_count=n,
        placement_rules=image_note + "\n\n" + placement,
        transform_rules=transform,
    )


def _placement_strategy(n: int) -> str:
    """按图片数量输出放置策略（来自用户要求：多图分散到小分栏）。"""
    if n == 1:
        return (
            "图片放置规则（1 张用户图）：\n"
            "1. 该用户图作为主新闻图片，放在页面中上部主图区域（左侧或中心，取决于排版模式）。\n"
            "2. 主图必须有边框、留白或细线边框，像真实报纸新闻配图。\n"
            "3. 主图宽度不超过页面 55%，不可铺满背景。\n"
            "4. 主图不能压住正文，正文不能漂浮在图片上。\n"
            "5. 主图可配图注。"
        )
    if n == 2:
        return (
            "图片放置规则（2 张用户图）：\n"
            "1. 第 1 张作为主新闻图片，放在页面中上部主图区域（宽度约 50-55%）。\n"
            "2. 第 2 张作为分栏配图或角标图，放在栏目一/栏目二的侧边或边角（宽度约 20-30%）。\n"
            "3. 两张图都不可铺满背景，都不可压正文。\n"
            "4. 两张图之间要有留白或细线分隔，不要拼贴成卡片。\n"
            "5. 主图比次图更大、更显眼，形成主次关系。"
        )
    # n == 3
    return (
        "图片放置规则（3 张用户图）：\n"
        "1. 第 1 张作为主新闻图片，放在页面中上部主图区域（宽度约 50-55%）。\n"
        "2. 第 2 张作为栏目配图，放在栏目一或栏目二的侧边（宽度约 20-25%）。\n"
        "3. 第 3 张作为边角图注或底部小配图，放在栏目三附近或底部信息区角落（宽度约 15-20%）。\n"
        "4. 三张图分散在不同区域，不可堆在一处，不可拼贴成卡片墙。\n"
        "5. 主图最大、次图中等、角标图最小，形成清晰的视觉层级。\n"
        "6. 所有图都不可铺满背景，都不可压正文。"
    )


def _transform_strategy(style: StyleDefinition) -> str:
    """按风格输出转化规则（取自各风格的 image_transform_rule，并强化"不原样贴图"）。"""
    return (
        f"图片风格转化规则（{style.name}）：\n"
        f"{style.image_transform_rule}\n\n"
        "重要：用户上传的图片必须先按上述风格转化为当前报纸风格下的视觉元素，"
        "再放入版面，严禁原样贴图，严禁保留与报纸风格冲突的写实/现代感。"
    )
