"""Vercel Python Functions 入口。

Vercel 会把 /api/* 请求路由到本文件。这里把 FastAPI app 暴露为 ASGI 应用。
本地开发仍用 uvicorn app.main:app；部署后用本文件。

注意：Vercel serverless 函数有超时限制（Hobby/Pro 60s）。
若 Task 0 实测生图 >60s，需改异步模式（POST 返 job_id + 轮询）。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让 Vercel 能找到项目根的 app 包和 prompts 包
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.main import app  # noqa: E402

# Vercel Python runtime 期望的 ASGI 入口
handler = app
