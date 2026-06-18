"""Skill 2：排版选择。

模式：
- random：从 A/B/C 三模板随机选（或用风格默认排版）
- generate：调 DeepSeek，以三模板为示例，生成一个"保持报纸结构但布局微调"的新排版指令

读取 prompts/layout_blocks.md 的三段模板作为基础。
"""
from __future__ import annotations

import logging
import random
import re
from pathlib import Path

from ..llm_client import LLMClient
from ..styles import StyleDefinition

logger = logging.getLogger(__name__)

_LAYOUT_FILE = Path(__file__).resolve().parent.parent.parent / "prompts" / "layout_blocks.md"

# 娱乐风格的专属排版（附件中娱乐风有独立排版描述，非 A/B/C）
ENTERTAINMENT_LAYOUT_KEY = "entertainment"


def _load_layout_blocks() -> dict[str, str]:
    """解析 layout_blocks.md，返回 {A: text, B: text, C: text}。"""
    if not _LAYOUT_FILE.exists():
        logger.warning("排版模板文件不存在: %s", _LAYOUT_FILE)
        return {}
    text = _LAYOUT_FILE.read_text(encoding="utf-8")
    blocks: dict[str, str] = {}
    # 按 "## 模式 X：" 分段
    pattern = re.compile(r"##\s*模式\s*([ABC])[^：]*：[^\n]*\n(.*?)(?=\n##\s*模式\s*[ABC]|\Z)", re.DOTALL)
    for m in pattern.finditer(text):
        key = m.group(1)
        body = m.group(2).strip()
        blocks[key] = body
    return blocks


_LAYOUT_BLOCKS = _load_layout_blocks()


def get_layout_block(mode: str) -> str:
    """取指定模式的排版模板原文。"""
    return _LAYOUT_BLOCKS.get(mode, "")


async def select_layout(
    style: StyleDefinition,
    mode: str = "fixed",
    *,
    seed: int | None = None,
    client: LLMClient | None = None,
) -> tuple[str, str]:
    """选择/生成排版。

    返回 (layout_key, layout_prompt)。
    layout_key: "A"/"B"/"C"/"entertainment"/"generate"

    mode:
    - fixed（默认）: 使用风格默认排版，同输入 100% 可复现
    - random: 从 A/B/C 随机选（需提供 seed 保证可复现）
    - generate: 调 DeepSeek 生成新排版
    """
    # 娱乐风格有专属排版，优先用
    if style.key == "entertainment" and style.default_layout == ENTERTAINMENT_LAYOUT_KEY:
        return ENTERTAINMENT_LAYOUT_KEY, _entertainment_layout_prompt()

    if mode == "generate":
        layout_key, layout_prompt = await _generate_layout_variant(style, client)
        return layout_key, layout_prompt

    if mode == "random":
        # random 模式：需 seed 保证可复现
        if seed is not None:
            rng = random.Random(seed)
        else:
            rng = random.Random()
        candidates = ["A", "B", "C"]
        chosen = rng.choice(candidates)
        block = get_layout_block(chosen)
        if not block:
            chosen = style.default_layout if style.default_layout in _LAYOUT_BLOCKS else "A"
            block = get_layout_block(chosen)
        logger.info("排版选择(random, seed=%s): %s", seed, chosen)
        return chosen, block

    # fixed（默认）: 使用风格默认排版
    chosen = style.default_layout if style.default_layout in _LAYOUT_BLOCKS else "A"
    block = get_layout_block(chosen)
    logger.info("排版选择(fixed): %s", chosen)
    return chosen, block


def _entertainment_layout_prompt() -> str:
    """娱乐专属排版（取自附件娱乐头条段落）。"""
    return (
        "报纸排版模式：顶部爆款头条 + 大图 + 三栏短新闻结构。\n\n"
        "请严格按照娱乐头条报纸版式排版：\n"
        "1. 顶部 10% 为娱乐报刊头区，横向铺满整页，放置报纸名、期数、日期，可加入价格、独家、特别报道等小元素。\n"
        "2. 刊头下方 20% 为超大头条标题区，主标题横跨整页，字号最大，形成强烈冲击力。\n"
        "3. 主标题下方放置副标题和爆点短句，可使用粗线框或醒目标注。\n"
        "4. 页面中部放置一张大头条新闻图片，宽度约 70%-85%，有图注、边框和娱乐新闻贴纸角标。\n"
        "5. 大图旁边或右侧放置栏目一作为头条侧栏，标题醒目，正文短而清晰。\n"
        "6. 页面下半部分分成三块新闻区：栏目一延展、栏目二、栏目三，采用报纸分栏或娱乐小报短栏结构。\n"
        "7. 三个栏目不能只是简单并列卡片，要有主次关系：主图最大，头条最醒目，栏目围绕头条展开。\n"
        "8. 底部横向信息条放置标签、彩蛋、主编点评和分享语。\n"
        "9. 可加入《独家》《爆料》《今日热榜》《现场直击》等视觉装饰，但不要改变用户提供的正式文字内容。\n"
        "10. 图片、贴纸、角标不能遮挡正文，正文必须完整可读。"
    )


async def _generate_layout_variant(style: StyleDefinition, client: LLMClient | None = None) -> tuple[str, str]:
    """调 DeepSeek 生成一个新的排版指令变体（保持报纸结构、布局微调）。"""
    c = client or LLMClient()
    examples = "\n\n".join(
        f"=== 示例排版 {k} ===\n{v}" for k, v in _LAYOUT_BLOCKS.items()
    )
    system = (
        "你是报纸排版设计师。请基于三个示例排版，生成一个新的排版指令。"
        "要求：保持真实报纸结构（刊头、主标题、新闻配图、三栏正文、底部信息），"
        "但在区域比例、位置、图位上做合理微调，让它既有报纸感又有新意。"
        "只输出排版指令文本，不要解释，不要输出 JSON。"
    )
    user = (
        f"当前风格：{style.name}（{style.intro}）\n\n"
        f"三个示例排版：\n{examples}\n\n"
        f"请生成一个新的排版指令（保持竖版 3:4，1080x1440）。"
    )
    try:
        # 用 chat_json 会要求 JSON，这里改用普通 chat；为复用客户端，走原始请求
        data = await c.chat_json(system, user, temperature=0.9, max_tokens=800)
        # 模型可能仍返回 JSON，尝试提取 text 字段
        variant = data.get("layout") or data.get("text") or data.get("content") or ""
        if not variant:
            # 把整个 dict 转成文本兜底
            import json
            variant = json.dumps(data, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("生成排版变体失败，退回随机模板: %s", exc)
        fallback = random.choice(["A", "B", "C"])
        return fallback, get_layout_block(fallback)
    logger.info("排版选择(generate): 新变体")
    return "generate", variant
