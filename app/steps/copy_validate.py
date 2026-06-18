"""Step4：文案校验（Copy Validate）。

独立的质量门禁步骤，在 copywrite 之后、layout select 之前执行。

检查项：
1. schema 合法性（必填字段、栏目数量）
2. 字数校验（各层级字数约束）
3. 空泛词/黑话校验
4. Fact Lock 校验（选手模式：used_facts 不超出 ProjectBrief）
"""
from __future__ import annotations

import logging

from ..models import PosterCopy, ProjectBrief, ValidationResult

logger = logging.getLogger(__name__)

# 空泛词/黑话黑名单
BUZZWORD_BLACKLIST = {
    "赋能", "抓手", "闭环", "打通", "沉淀", "复用", "联动",
    "矩阵", "赛道", "痛点", "护城河", "降维打击", "组合拳",
    "方法论", "生态化反", "心智占领",
}

# 字数约束（最大值）
WORD_LIMITS = {
    "poster_name": 10,
    "headline": 25,
    "subheadline": 35,
    "easter_egg": 20,
    "editor_comment": 20,
    "share_line": 20,
}

# 栏目字数约束
COLUMN_TITLE_MAX = 10
COLUMN_BODY_MIN = 30
COLUMN_BODY_MAX = 100


def validate_copy(
    copy: PosterCopy,
    *,
    brief: ProjectBrief | None = None,
    mode: str = "participant",
) -> ValidationResult:
    """校验 PosterCopy 文案质量。

    Args:
        copy: 待校验的文案
        brief: 项目摘要（选手模式用于 Fact Lock 校验）
        mode: participant=选手模式, audience=观众模式

    Returns:
        ValidationResult: 校验结果
    """
    issues: list[str] = []

    # 1. 必填字段检查
    if not copy.headline.strip():
        issues.append("主标题为空")
    if not copy.subheadline.strip():
        issues.append("副标题为空")
    if not copy.poster_name.strip():
        issues.append("报纸名为空")

    # 2. 栏目数量检查
    if len(copy.columns) != 3:
        issues.append(f"栏目数量不等于 3（当前 {len(copy.columns)} 个）")
    else:
        # 3. 栏目内容检查
        for i, col in enumerate(copy.columns):
            if not col.title.strip():
                issues.append(f"栏目{i + 1}标题为空")
            elif len(col.title) > COLUMN_TITLE_MAX:
                issues.append(f"栏目{i + 1}标题超 {COLUMN_TITLE_MAX} 字（{len(col.title)} 字）")
            if not col.body.strip():
                issues.append(f"栏目{i + 1}正文为空")
            elif len(col.body) > COLUMN_BODY_MAX:
                issues.append(f"栏目{i + 1}正文超 {COLUMN_BODY_MAX} 字（{len(col.body)} 字）")

    # 4. 顶层字段字数检查
    for field, limit in WORD_LIMITS.items():
        val = getattr(copy, field, "")
        if val and len(val) > limit:
            issues.append(f"{field} 超 {limit} 字（{len(val)} 字）")

    # 5. 空泛词检查
    all_text = " ".join([
        copy.headline, copy.subheadline,
        " ".join(c.title + " " + c.body for c in copy.columns),
        copy.easter_egg, copy.editor_comment, copy.share_line,
    ])
    found_buzzwords = [w for w in BUZZWORD_BLACKLIST if w in all_text]
    if found_buzzwords:
        issues.append(f"发现空泛词/黑话: {', '.join(found_buzzwords)}")

    # 6. Fact Lock 校验（仅选手模式）
    if mode == "participant" and brief:
        fact_issues = _check_fact_lock(copy, brief)
        issues.extend(fact_issues)

    passed = len(issues) == 0
    retry = "" if passed else "修正上述文案问题后重新生成"
    logger.info("Copy Validate: passed=%s issues=%d (%s)", passed, len(issues), "; ".join(issues) if issues else "OK")
    return ValidationResult(passed=passed, issues=issues, retry_suggestion=retry)


def _check_fact_lock(copy: PosterCopy, brief: ProjectBrief) -> list[str]:
    """Fact Lock 校验：检查 used_facts 是否能在 ProjectBrief 中找到来源。

    简化实现：检查 used_facts 中的关键词是否出现在 brief 的字段值中。
    """
    issues: list[str] = []

    # 构建 brief 全文（用于关键词匹配）
    brief_text = " ".join([
        brief.project_name, brief.team_name, brief.target_user,
        brief.core_problem, brief.core_solution, brief.main_value,
        " ".join(brief.features), " ".join(brief.fun_points),
        brief.event_name, brief.visual_direction,
    ]).lower()

    for fact in copy.used_facts:
        # 提取 fact 中的关键名词（简化：取 >2 字的片段）
        # 如果 fact 中的任何 3+ 字片段在 brief 中找不到，标记为可疑
        fact_lower = fact.lower()
        # 简单检查：fact 中的核心词是否在 brief 中出现
        # 取 fact 中长度 >= 3 的连续中文字符片段
        import re
        segments = re.findall(r"[\u4e00-\u9fff]{3,}", fact_lower)
        if not segments:
            continue
        # 至少有一个片段能在 brief 中找到
        found_any = any(seg in brief_text for seg in segments)
        if not found_any:
            issues.append(f"Fact Lock: used_fact 在 ProjectBrief 中找不到来源: '{fact[:30]}'")

    return issues
