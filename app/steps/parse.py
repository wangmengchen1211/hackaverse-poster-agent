"""Step1：信息解析（DeepSeek → ProjectBrief）。"""
from __future__ import annotations

import json
import logging

from ..llm_client import LLMClient
from ..models import ProjectBrief
from prompts.system_prompts import PARSE_SYSTEM

logger = logging.getLogger(__name__)


async def parse_project(prd: str, *, project_name: str = "", team_name: str = "",
                        event_name: str = "", client: LLMClient | None = None) -> ProjectBrief:
    """从 PRD 文本提炼项目摘要。

    输入 PRD + 可选的项目名/团队名/活动名（会拼进 user 消息作为已知信息）。
    """
    c = client or LLMClient()

    known_parts = []
    if project_name:
        known_parts.append(f"项目名称（已知）：{project_name}")
    if team_name:
        known_parts.append(f"团队名称（已知）：{team_name}")
    if event_name:
        known_parts.append(f"活动名称（已知）：{event_name}")
    known_block = "\n".join(known_parts)

    known_section = ""
    if known_block:
        known_section = f"已知信息：\n{known_block}\n\n"

    user_msg = (
        f"请根据以下项目输入提炼 project_brief：\n\n"
        f"{known_section}"
        f"项目 PRD / 描述：\n{prd}"
    )

    data = await c.chat_json(PARSE_SYSTEM, user_msg, temperature=0.3, max_tokens=1200)
    logger.info("Step1 解析完成: project_name=%s", data.get("project_name", ""))
    return ProjectBrief.model_validate(data)
