#!/usr/bin/env python
"""测试脚本：只运行文案生成步骤（copywrite），跳过图片生成。

验证修改后的文案是否：
1. 栏目名摆脱了"项目简介"等直述句
2. 正文从说明书式陈述变成故事化叙述

用法: python test_copywrite.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import os

# 确保可以 import app.* 和 prompts.*
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def make_test_brief():
    """构造一个有足够细节的测试 ProjectBrief。"""
    from app.models import ProjectBrief
    return ProjectBrief(
        project_name="有点惦记",
        team_name="念念小队",
        target_user="远在他乡的子女与家中的长辈",
        core_problem="子女太忙，没时间打电话，长辈感到孤独，双方沟通越来越少",
        core_solution="AI 小助理念念，帮子女把惦记变成每日问候，自动拨打电话陪长辈聊天",
        main_value="让爱不再迟到，让惦记每天都有回音",
        features=[
            "AI 自动拨打电话，用温柔的声音陪长辈聊天",
            "把长辈的近况整理成记忆卡片推送给子女",
            "子女只需花30秒录制一句话，念念就能变成长辈的一整天陪伴",
        ],
        event_name="AI Hackathon 2026",
        fun_points=[
            "念念会记得长辈上次提到的每一件小事，下次主动提起",
            "有个奶奶管念念叫'电子孙女'",
            "最难的不是AI说话，是让AI知道什么时候该闭嘴听长辈讲",
        ],
        visual_direction="温暖、家庭感、有点复古",
    )


def print_separator(style_name: str):
    print("\n" + "=" * 70)
    print(f"  风格: {style_name}")
    print("=" * 70)


def print_copy(copy):
    """格式化打印文案，重点标注栏目名和正文。"""
    print(f"\n[报纸名] {copy.poster_name}")
    print(f"[期号]   {copy.issue_label}")
    print(f"[日期]   {copy.date}")
    print(f"\n[主标题] {copy.headline}")
    print(f"[副标题] {copy.subheadline}")
    print(f"\n[标签] {', '.join(copy.tags)}")

    print(f"\n[栏目] 共 {len(copy.columns)} 栏:")
    print("-" * 50)
    for i, col in enumerate(copy.columns, 1):
        body_len = len(col.body)
        print(f"\n  栏目 {i}: [{col.title}]")
        print(f"  正文 ({body_len}字): {col.body}")
        print("-" * 50)

    print(f"\n[彩蛋] {copy.easter_egg}")
    print(f"[主编点评] {copy.editor_comment}")
    print(f"[分享语] {copy.share_line}")

    if copy.used_facts:
        print(f"\n[Fact Lock] 使用的事实:")
        for f in copy.used_facts:
            print(f"   - {f}")
    if copy.creative_angles:
        print(f"\n[创意角度]")
        for a in copy.creative_angles:
            print(f"   - {a}")


async def run_test():
    from app.steps.copywrite import generate_copy
    from app.styles import list_styles

    brief = make_test_brief()
    all_styles = list_styles()
    style_map = {s.key: s for s in all_styles}

    # 测试 3 个差异最大的风格
    test_keys = ["daily", "entertainment", "magic"]

    print("=" * 70)
    print("  文案生成测试（修改后）- 3 种风格对比")
    print("  项目: 有点惦记（AI陪聊小助理念念）")
    print("=" * 70)

    for key in test_keys:
        if key not in style_map:
            print(f"\n[警告] 风格 {key} 不存在，跳过")
            continue

        s = style_map[key]
        print_separator(s.name)

        try:
            copy = await generate_copy(brief, key, mode="participant")
            print_copy(copy)
        except Exception as e:
            print(f"\n[失败] 生成失败: {e}")

    print("\n" + "=" * 70)
    print("  测试完成！请检查上方输出：")
    print("  1. 栏目名是否摆脱了'项目简介'等直述句？")
    print("  2. 正文是否从说明书式变成了故事化叙述？")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_test())
