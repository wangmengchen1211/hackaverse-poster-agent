#!/usr/bin/env python3
"""使用 PRD 文件测试报纸生成"""
import json
import os
import asyncio
from pathlib import Path

from app.main import app
from app.config import get_settings
from app.models import ProjectBrief
from app.orchestrator import run_pipeline
from app.llm_client import LLMClient


async def test_prd_newspaper():
    """使用原点日报机 PRD 测试报纸生成"""
    
    print("=== 原点日报机报纸生成测试 ===\n")
    
    # 1. 读取 PRD 文件内容
    prd_path = Path("d:\\AI\\Qoder task\\.qoder\\原点日报宇宙\\PRD.txt")
    if not prd_path.exists():
        print("[ERROR] 找不到 PRD 文件")
        return
    
    with open(prd_path, 'r', encoding='utf-8') as f:
        prd_content = f.read()
    
    print(f"[INFO] PRD 文件大小: {len(prd_content)} 字符")
    
    # 2. 创建项目简报
    project_brief = ProjectBrief(
        project_name="原点日报机",
        prd_text=prd_content,
        team_name="AI创意团队",
        event_name="抖音原点社区黑客松",
        user_ref="test_user_origin_universe"
    )
    
    print("[INFO] 项目简报创建成功:")
    print(f"  - 项目名称: {project_brief.project_name}")
    print(f"  - 团队名称: {project_brief.team_name}")
    print(f"  - 活动名称: {project_brief.event_name}")
    
    # 3. 设置测试参数
    style_key = "daily"  # 使用经典日报风格
    image_count = 0  # 暂不使用图片，先测试纯文字生成
    layout_mode = "random"  # 随机选择排版
    
    print(f"\n[INFO] 测试参数:")
    print(f"  - 风格: {style_key}")
    print(f"  - 图片数量: {image_count}")
    print(f"  - 排版模式: {layout_mode}")
    
    # 4. 初始化 LLM 客户端
    settings = get_settings()
    llm_client = LLMClient(settings)
    
    # 5. 运行生成管道
    print(f"\n[INFO] 开始生成报纸...")
    print("=" * 50)
    
    try:
        result = await run_pipeline(
            prd=project_brief,
            style_key=style_key,
            project_name=project_brief.project_name,
            team_name=project_brief.team_name,
            event_name=project_brief.event_name,
            image_count=image_count,
            layout_mode=layout_mode,
            user_ref="test_user_origin_universe",
            client=llm_client
        )
        
        print("=" * 50)
        print(f"\n[SUCCESS] 报纸生成成功!")
        
        # 6. 输出生成结果
        print(f"\n=== 生成结果 ===")
        print(f"标题: {result.response.title}")
        print(f"副标题: {result.response.subtitle}")
        print(f"风格: {result.response.style_key}")
        print(f"排版: {result.response.layout_used}")
        print(f"状态: {result.response.status}")
        
        print(f"\n=== 报纸内容 ===")
        print(result.response.poster_copy)
        
        print(f"\n=== 项目信息 ===")
        project_info = result.response.project_info
        print(f"项目类型: {project_info.get('project_type', 'N/A')}")
        print(f"关键词: {project_info.get('keywords', 'N/A')}")
        print(f"亮点: {project_info.get('highlights', 'N/A')}")
        
        # 7. 保存生成的报纸内容到文件
        output_file = Path(__file__).parent / "outputs" / "origin_universe_daily_newspaper.md"
        output_file.parent.mkdir(exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"""# 原点日报 - 生成测试

## 项目信息
- **项目名称**: {project_brief.project_name}
- **团队名称**: {project_brief.team_name}
- **活动名称**: {project_brief.event_name}
- **生成时间**: {result.response.created_at}
- **风格**: {result.response.style_key}
- **排版**: {result.response.layout_used}

## 报纸内容

### 标题
{result.response.title}

### 副标题
{result.response.subtitle}

### 正文
{result.response.poster_copy}

### 项目信息
{json.dumps(project_info, ensure_ascii=False, indent=2)}

""")
        
        print(f"\n[INFO] 生成的报纸已保存到: {output_file}")
        
        # 8. 检查是否有图片生成
        if result.image_bytes:
            image_path = Path(__file__).parent / "outputs" / "origin_universe_daily_poster.png"
            with open(image_path, 'wb') as f:
                f.write(result.image_bytes)
            print(f"[INFO] 报纸图片已保存到: {image_path}")
        else:
            print("[INFO] 本次测试未生成图片（无图片输入）")
        
        return result
        
    except Exception as e:
        print(f"\n[ERROR] 生成过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    # 运行异步测试
    result = asyncio.run(test_prd_newspaper())
    
    if result:
        print("\n[SUCCESS] 测试完成！报纸生成成功。")
    else:
        print("\n[FAIL] 测试失败。")