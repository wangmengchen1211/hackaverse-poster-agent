"""DeepSeek API 连通性自检脚本（Task 0）。

用法（在项目根目录 poster-agent/ 下）：
    1. 先配置 .env（参考 .env.example）
    2. pip install httpx python-dotenv
    3. python scripts/check_deepseek.py

输出：HTTP 状态、响应片段、耗时、是否 JSON 模式可用。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("[FATAL] 缺少 httpx，请运行: pip install httpx", file=sys.stderr)
    sys.exit(2)

try:
    from dotenv import load_dotenv
    _HAS_DOTENV = True
except ImportError:
    _HAS_DOTENV = False
    print("[WARN] 缺少 python-dotenv，将直接读系统环境变量。建议: pip install python-dotenv")


def load_env() -> None:
    """从项目根 .env 或 .env.local 加载（若 dotenv 可用）。"""
    if not _HAS_DOTENV:
        return
    # scripts/ 的上一级即项目根
    root = Path(__file__).resolve().parent.parent
    
    # 优先尝试 .env.local
    env_path = root / ".env.local"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[INFO] 已加载 {env_path}")
        return
    
    # 回退到 .env
    env_path = root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[INFO] 已加载 {env_path}")
    else:
        print(f"[WARN] 未找到 {env_path}，将使用系统环境变量")


def main() -> int:
    load_env()

    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()

    if not api_key:
        print("[FAIL] DEEPSEEK_API_KEY 为空，请先在 .env 中配置。", file=sys.stderr)
        return 1

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个测试助手，只输出 JSON。"},
            {"role": "user", "content": '请输出一个 JSON：{"ok": true, "msg": "deepseek 连通"}'},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "max_tokens": 100,
    }

    print(f"[INFO] POST {url}")
    print(f"[INFO] model={model}")
    t0 = time.time()
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, headers=headers, json=payload)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] 请求异常: {exc}", file=sys.stderr)
        return 1
    latency_ms = int((time.time() - t0) * 1000)

    print(f"[INFO] HTTP {resp.status_code}  耗时 {latency_ms} ms")

    if resp.status_code != 200:
        print(f"[FAIL] 非 200 响应体:\n{resp.text[:500]}", file=sys.stderr)
        return 1

    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 响应不是合法 JSON: {exc}\n{resp.text[:500]}", file=sys.stderr)
        return 1

    content = ""
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        print(f"[WARN] 响应结构异常，缺少 choices[0].message.content:\n{json.dumps(data, ensure_ascii=False)[:500]}")

    json_mode_ok = False
    try:
        parsed = json.loads(content)
        json_mode_ok = isinstance(parsed, dict)
    except Exception:  # noqa: BLE001
        pass

    print("\n========== 结果 ==========")
    print(f"HTTP 状态        : {resp.status_code}")
    print(f"耗时             : {latency_ms} ms")
    print(f"JSON 模式可用    : {'是' if json_mode_ok else '否'}")
    print(f"返回内容片段     : {content[:200]}")
    print("==========================")

    if json_mode_ok:
        print("[OK] DeepSeek 连通正常，可用于 Step1/2。")
        return 0
    print("[WARN] 连通但 JSON 模式不可用，Step1/2 需做容错解析。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
