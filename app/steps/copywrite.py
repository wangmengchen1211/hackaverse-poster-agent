"""Step2：文案生成（DeepSeek → PosterCopy，每栏目 body 50-80 字）。

支持两种模式：
- participant: 选手模式，基于 PRD 生成项目文案
- audience: 观众模式，基于现场体验生成观众专属文案
"""
from __future__ import annotations

import logging
from datetime import datetime

from ..llm_client import LLMClient
from ..models import ProjectBrief, PosterCopy, Column
from ..styles import get_style, StyleDefinition
from prompts.system_prompts import COPYWRITE_SYSTEM, AUDIENCE_COPYWRITE_SYSTEM, GLOBAL_COPY_CONSTRAINTS

logger = logging.getLogger(__name__)

MAX_BODY_CHARS = 80
MIN_BODY_CHARS = 50


async def generate_copy(brief: ProjectBrief, style_key: str, *,
                        mode: str = "participant",
                        user_name: str = "",
                        event_name: str = "",
                        impression: str = "",
                        client: LLMClient | None = None) -> PosterCopy:
    """根据项目摘要 + 风格，生成海报文案。
    
    mode: participant=选手模式, audience=观众模式
    user_name: 观众姓名/昵称（audience 模式使用）
    event_name: 活动名称（audience 模式使用）
    impression: 观众感受/印象（audience 模式使用）
    """
    c = client or LLMClient()
    style = get_style(style_key)

    if mode == "audience":
        # 观众模式：使用 AUDIENCE_COPYWRITE_SYSTEM
        user_msg = (
            f"请为黑客松观众生成一套专属头版报纸文案。\n\n"
            f"{GLOBAL_COPY_CONSTRAINTS}\n\n"
            f"海报风格：{style.name}\n"
            f"风格说明：{style.intro}\n\n"
            f"文案语调要求（严格遵守）：\n{style.copywriting_tone}\n\n"
            f"观众信息：\n"
            f"- 姓名/昵称：{user_name or '匿名观众'}\n"
            f"- 活动名称：{event_name or '黑客松现场'}\n"
            f"- 现场感受/印象：{impression or '见证了一群开发者创造未来的过程'}\n\n"
            f"严格约束：每个栏目 body 必须 {MIN_BODY_CHARS}-{MAX_BODY_CHARS} 个中文字符，突出【我在现场】的见证感。"
        )
        system_prompt = AUDIENCE_COPYWRITE_SYSTEM
    else:
        # 选手模式：使用 COPYWRITE_SYSTEM
        user_msg = (
            f"请根据以下 project_brief 和海报风格，生成一套结构化海报文案。\n\n"
            f"{GLOBAL_COPY_CONSTRAINTS}\n\n"
            f"海报风格：{style.name}\n"
            f"风格说明：{style.intro}\n\n"
            f"文案语调要求（严格遵守）：\n{style.copywriting_tone}\n\n"
            f"project_brief（JSON）：\n{brief.model_dump_json(indent=2, ensure_ascii=False)}\n\n"
            f"严格约束：每个栏目 body 必须 {MIN_BODY_CHARS}-{MAX_BODY_CHARS} 个中文字符，短小精悍但有亮点。"
        )
        system_prompt = COPYWRITE_SYSTEM

    data = await c.chat_json(system_prompt, user_msg, temperature=0.8, max_tokens=2500)

    # 后处理：对超长 body 做截断兜底，对过短 body 做补齐
    columns = data.get("columns") or []
    fixed_columns: list[dict] = []
    for col in columns[:3]:
        body = str(col.get("body", ""))
        if len(body) > MAX_BODY_CHARS:
            logger.warning("栏目 body 超 %s 字（%s），截断兜底", MAX_BODY_CHARS, len(body))
            body = body[:MAX_BODY_CHARS]
        elif len(body) < MIN_BODY_CHARS:
            logger.warning("栏目 body 不足 %s 字（%s），需要补齐", MIN_BODY_CHARS, len(body))
        fixed_columns.append({"title": col.get("title", ""), "body": body})

    # 补齐到 3 栏
    while len(fixed_columns) < 3:
        fixed_columns.append({"title": f"栏目{len(fixed_columns) + 1}", "body": ""})

    data["columns"] = fixed_columns

    # 日期强制使用实时日期（不让 LLM 自由发挥）
    today = datetime.now()
    data["date"] = today.strftime("%Y年%m月%d日")

    copy = PosterCopy.model_validate(data)
    logger.info("Step2 文案完成 (mode=%s): headline=%s, date=%s, 栏目数=%d", mode, copy.headline[:30], copy.date, len(copy.columns))
    return copy
