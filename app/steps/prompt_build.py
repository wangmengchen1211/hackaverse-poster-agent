"""Step3：单次生图 prompt 组装（含中文文字强化规则）。

融合：媒介定义 + 风格块 + 版式块(skill) + 内容槽位(copy) + 图片处理 + 中文文字强化6规则 + 二维码预留 + 负面约束
"""
from __future__ import annotations

import logging

from ..models import PosterCopy, ImagePlan
from ..skills.image_adapter import ImageDirective
from ..styles import StyleDefinition, reference_path
from ..styles.definitions import MEDIA_PREAMBLE

logger = logging.getLogger(__name__)


def build_image_plan(
    style: StyleDefinition,
    copy: PosterCopy,
    layout_key: str,
    layout_prompt: str,
    image_directive: ImageDirective,
    *,
    has_qr_code: bool = False,
    size: str = "1024x1536",
    mode: str = "participant",
) -> ImagePlan:
    """拼装单次生图 prompt（含中文文字强化）+ 选定参考图。
    
    mode: participant=选手模式, audience=观众模式
    """

    # ── 内容槽位段（用双引号精确标注文字）──
    col1, col2, col3 = (copy.columns + [None, None, None])[:3]
    content_block = _render_content_slots(copy, col1, col2, col3)

    sections: list[str] = []

    # 1. 媒介定义
    sections.append(f"[媒介定义]\n{MEDIA_PREAMBLE}")

    # 2. 视觉风格 + 风格专属文字规则
    sections.append(
        f"[风格]\n报纸风格：{style.name}\n整体视觉要求：\n{style.visual_prompt}\n\n"
        f"风格专属文字规则：\n{style.text_style_rules}"
    )

    # 3. 版式
    sections.append(
        f"[版式]\n报纸排版模式：{layout_key}\n请严格按照真实报纸结构排版："
        "刊头、主标题、副标题、主视觉图片、三栏正文、底部信息区。\n\n"
        f"{layout_prompt}"
    )

    # 4. 内容槽位（精确标注文字）
    if mode == "audience":
        sections.append(
            f"[内容槽位 - 观众专属报纸]\n"
            "说明：这是一张黑客松观众的专属头版报纸，突出【我在现场】的见证感。\n"
            "以下内容中，用中文双引号包裹的部分是必须精确渲染在报纸上的文字。\n"
            "请在版面中清晰呈现这些文字，不要改写、不要遗漏、不要错别字。\n\n"
            f"{content_block}"
        )
    else:
        sections.append(
            f"[内容槽位 - 用双引号精确标注需要渲染的文字]\n"
            "说明：以下内容中，用中文双引号包裹的部分是必须精确渲染在报纸上的文字。\n"
            "请在版面中清晰呈现这些文字，不要改写、不要遗漏、不要错别字。\n\n"
            f"{content_block}"
        )

    # 5. 图片处理
    if image_directive.has_images:
        sections.append(
            f"[用户照片处理]\n{image_directive.placement_rules}\n\n"
            f"{image_directive.transform_rules}"
        )
    else:
        sections.append(
            "[配图]\n没有用户上传照片，请根据项目主题自行生成符合风格的新闻配图。\n"
            "主新闻图片放在页面中上部，宽度约 50-55%，像真实报纸新闻配图。"
        )

    # 6. 中文文字强化规则（6条）— 使用模块级常量，避免重复构建
    sections.append(_CHINESE_TEXT_RULES)

    # 7. 二维码预留
    qr_block = _build_qr_block(has_qr_code)
    sections.append(f"[二维码区域]\n{qr_block}")

    # 8. 负面约束
    sections.append(f"[负面约束]\n{style.negative_prompt}")

    final_prompt = "\n\n".join(sections)

    ref_path = reference_path(style)
    plan = ImagePlan(
        style_key=style.key,
        style_name=style.name,
        layout_mode=layout_key,
        final_prompt=final_prompt,
        negative_prompt=style.negative_prompt,
        reference_image=ref_path,
        size=size,
        image_directives={
            "has_images": image_directive.has_images,
            "image_count": image_directive.image_count,
        },
        has_qr_code=has_qr_code,
        has_user_images=image_directive.has_images,
    )
    logger.info(
        "Step3 prompt 组装完成: style=%s layout=%s len=%d qr=%s",
        style.key, layout_key, len(final_prompt), has_qr_code,
    )
    return plan


# 中文文字强化6规则 — 模块级常量，只构建一次，不随输入变化。
_CHINESE_TEXT_RULES = (
    "[中文文字渲染强化规则 - 必须严格遵守]\n\n"
        
        "规则1：精确标注文字\n"
        "所有需要渲染在报纸上的中文文字，必须用双引号包裹，明确区分描述性文字和实际内容。\n"
        "例如：标题写为【某某团队发布新产品】，正文写为【该项目解决了用户的XX问题】。\n\n"
        
        "规则2：字数精简+字号放大\n"
        "- 每个栏目正文控制在 50-80 字（2-3行），少但有亮点\n"
        "- 栏目标题字号要明显大于正文（建议比例 1.5-2倍）\n"
        "- 主标题字号最大，副标题次之，栏目标题再次之，正文最小\n"
        "- 彩蛋、主编点评、分享语各不超过 15 字，用中等字号\n\n"
        
        "规则3：指定渲染字体\n"
        "- 主标题：中文黑体、微软雅黑或无衬线粗体（清晰易读）\n"
        "- 栏目标题：黑体或微软雅黑\n"
        "- 正文：宋体、微软雅黑或无衬线常规体（不要花哨字体）\n"
        "- 禁止使用手写体、艺术字、装饰字体、难以辨认的字体\n\n"
        
        "规则4：排版与位置\n"
        "- 主标题：页面顶部居中或左对齐，字号最大，字间距适当\n"
        "- 副标题：紧跟主标题下方，字号约为主标题的 60-70%\n"
        "- 三栏正文：等宽分栏，栏间有细线分隔，左对齐\n"
        "- 每栏标题与正文间距约 1 行高\n"
        "- 栏内行间距 1.2-1.5 倍字号，不要拥挤\n"
        "- 底部信息区（报纸名、期数、日期）：页面底部，小字号，居中或右对齐\n\n"
        
        "规则5：质量强化\n"
        "- 所有中文笔画必须清晰完整，无粘连、无断笔\n"
        "- 字符间距均匀，不要过密或过疏\n"
        "- 文字颜色与背景对比度充足（深色背景用白字/浅色字，浅色背景用黑字/深色字）\n"
        "- 文字不要被图片、装饰元素遮挡\n"
        "- 每个汉字必须完整渲染，不要出现缺笔、变形、镜像\n"
        "- 所有文字必须清晰锐利，禁止模糊效果（no blur, no gaussian blur）\n"
        "- 所有文字下方禁止出现下划线（no underline, no text-decoration）\n\n"
        
        "规则6：否定提示 - 排除错误形态\n"
        "严禁出现以下情况：\n"
        "- 乱码、错别字、伪中文、无意义笔画组合\n"
        "- 拼音、英文、日文假名替代中文\n"
        "- 文字重叠、文字扭曲、文字模糊不清\n"
        "- 文字带有模糊效果、高斯模糊、阴影模糊\n"
        "- 文字下方出现下划线、底线、装饰线（分隔线除外，分隔线必须在文字区域之外）\n"
        "- 生僻字、造字、异体字\n"
        "- 文字被图片覆盖或被装饰元素遮挡\n"
        "- 文字溢出边界、文字挤压变形"
)


def _build_qr_block(has_qr_code: bool) -> str:
    """构建二维码预留区域指令。"""
    if has_qr_code:
        return (
            "页面右下角必须预留一个空白区域用于放置二维码。\n"
            "预留区域位置：右下角，距底部边距约页面高度的 3%，距右边距约页面宽度的 3%。\n"
            "预留区域尺寸：宽约页面宽度的 10%，高宽相等（正方形）。\n"
            "预留区域必须是纯白或浅色空白，不要在其中生成任何内容。\n"
            "二维码将由程序后续直接贴入此区域。"
        )
    else:
        return (
            "本次无需预留二维码区域。\n"
            "底部信息区右下角可以正常排列文字内容。"
        )


def _render_content_slots(copy: PosterCopy, col1, col2, col3) -> str:
    """渲染内容槽位段（用双引号精确标注文字）。"""
    tags = " ".join([f"#{t}" for t in copy.tags]) if copy.tags else ""
    lines = [
        f'报纸名：\n"{copy.poster_name}"',
        f'期数：\n"{copy.issue_label}"',
        f'日期：\n"{copy.date}"',
        f'主标题：\n"{copy.headline}"',
        f'副标题：\n"{copy.subheadline}"',
    ]
    if col1:
        lines.append(f'栏目一标题：\n"{col1.title}"')
        lines.append(f'栏目一正文：\n"{col1.body}"')
    if col2:
        lines.append(f'栏目二标题：\n"{col2.title}"')
        lines.append(f'栏目二正文：\n"{col2.body}"')
    if col3:
        lines.append(f'栏目三标题：\n"{col3.title}"')
        lines.append(f'栏目三正文：\n"{col3.body}"')
    if tags:
        lines.append(f'标签：\n"{tags}"')
    if copy.easter_egg:
        lines.append(f'彩蛋：\n"{copy.easter_egg}"')
    if copy.editor_comment:
        lines.append(f'主编点评：\n"{copy.editor_comment}"')
    if copy.share_line:
        lines.append(f'分享语：\n"{copy.share_line}"')
    return "\n\n".join(lines)
