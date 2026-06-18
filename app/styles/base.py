"""风格定义的数据基类。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StyleDefinition:
    """单个风格的完整 prompt 模块。

    字段内容直接对应附件《6 styles prompt tem》的各风格段落，
    以及《image prompt template》的图片转化规则。
    """

    key: str                        # daily / cyber / entertainment / character3d / comic / magic
    name: str                       # 中文名
    default_layout: str             # A / B / C（该风格的默认排版模板）
    visual_prompt: str              # 整体视觉要求段
    text_style_rules: str           # 文字样式要求段
    negative_prompt: str            # 负面约束段
    image_transform_rule: str       # 该风格下用户照片的转化规则（image_adapter skill 用）
    reference_image: str            # references/ 下文件名
    intro: str = ""                 # 一句话风格描述（给前端展示）
    copywriting_tone: str = ""      # 文案语调描述（供 Step2 文案生成使用）
