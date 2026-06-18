"""gpt-image-2（llmgateway 中转）生图连通性自检脚本（Task 0）。

用法（在项目根目录 poster-agent/ 下）：
    1. 先配置 .env（参考 .env.example）
    2. pip install httpx python-dotenv
    3. python scripts/check_image_api.py

本脚本会自动探测：
  - base_url 完整路径（尝试 /v1/images/generations 与 /images/generations）
  - 响应格式（data[0].b64_json vs data[0].url）
  - 单次生图耗时（关键：>60s 则 Vercel 部署需异步）

输出一份结论，便于 Task 3 直接据此实现 llm_client.generate_image。
"""
from __future__ import annotations

import base64
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


def load_env() -> None:
    if not _HAS_DOTENV:
        return
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


PROMPT = "一只可爱的橘猫，简笔画风格，纯色背景"  # 最小化生图耗时


def try_endpoint(client: httpx.Client, url: str, headers: dict, payload: dict) -> dict:
    """单次尝试，返回结果摘要。"""
    result: dict = {"url": url, "payload_keys": list(payload.keys()), "ok": False, "status": None,
                    "latency_ms": None, "data_path": None, "value_kind": None, "sample": None, "error": None}
    t0 = time.time()
    try:
        resp = client.post(url, headers=headers, json=payload, timeout=120.0)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"请求异常: {exc}"
        result["latency_ms"] = int((time.time() - t0) * 1000)
        return result
    result["latency_ms"] = int((time.time() - t0) * 1000)
    result["status"] = resp.status_code
    if resp.status_code != 200:
        result["error"] = resp.text[:400]
        return result
    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"非 JSON 响应: {exc} | body={resp.text[:200]}"
        return result
    # 探测 data[0] 取值方式
    items = data.get("data") if isinstance(data, dict) else None
    if isinstance(items, list) and items:
        first = items[0]
        if isinstance(first, dict):
            if first.get("b64_json"):
                result["ok"] = True
                result["data_path"] = "data[0].b64_json"
                result["value_kind"] = "b64"
                # 估算字节数（不保存）
                try:
                    result["sample"] = f"b64 length={len(first['b64_json'])} (~{len(first['b64_json']) * 3 // 4 // 1024} KB)"
                except Exception:  # noqa: BLE001
                    result["sample"] = "b64 (长度计算失败)"
                return result
            if first.get("url"):
                result["ok"] = True
                result["data_path"] = "data[0].url"
                result["value_kind"] = "url"
                result["sample"] = str(first["url"])[:200]
                return result
            if first.get("revised_prompt") is not None and not (first.get("b64_json") or first.get("url")):
                result["error"] = "data[0] 仅含 revised_prompt，无图片字段"
                return result
        result["error"] = f"data[0] 结构异常: {json.dumps(first, ensure_ascii=False)[:200]}"
        return result
    # 非标准结构
    result["error"] = f"响应无 data 数组，顶层 keys={list(data.keys()) if isinstance(data, dict) else type(data).__name__}"
    return result


def main() -> int:
    load_env()

    api_key = os.getenv("IMAGE_API_KEY", "").strip()
    base_url = os.getenv("IMAGE_BASE_URL", "https://www.llmgateway.cn").strip().rstrip("/")
    model = os.getenv("IMAGE_MODEL", "gpt-image-2").strip()

    if not api_key:
        print("[FAIL] IMAGE_API_KEY 为空，请先在 .env 中配置。", file=sys.stderr)
        return 1

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 候选端点路径
    candidates = []
    for path in ["/v1/images/generations", "/images/generations"]:
        full = base_url + path
        if full not in [c[0] for c in candidates]:
            candidates.append((full, path))

    # 基础 payload（DALL·E 风格）
    base_payload = {
        "model": model,
        "prompt": PROMPT,
        "n": 1,
    }
    # 候选 size / response_format 组合
    size_candidates = ["1024x1024", "1024x1536"]  # 先小图省时，再试竖图
    # response_format 仅文生图有意义；gpt-image-1 系通常忽略它，但某些中转需要
    response_format_candidates = [None, "b64_json", "url"]

    print(f"[INFO] base_url = {base_url}")
    print(f"[INFO] model    = {model}")
    print(f"[INFO] 测试 prompt: {PROMPT}\n")

    results: list[dict] = []
    success: dict | None = None

    with httpx.Client() as client:
        for url, _path in candidates:
            if success:
                break
            for size in size_candidates:
                if success:
                    break
                for rf in response_format_candidates:
                    payload = dict(base_payload)
                    payload["size"] = size
                    if rf:
                        payload["response_format"] = rf
                    print(f"[TRY] {url}  size={size}  response_format={rf}")
                    r = try_endpoint(client, url, headers, payload)
                    results.append(r)
                    if r["ok"]:
                        print(f"  -> OK ({r['latency_ms']} ms, {r['data_path']}, {r['sample']})\n")
                        success = r
                        break
                    else:
                        msg = r["error"] or f"status={r['status']}"
                        print(f"  -> 失败 ({r['latency_ms']} ms): {msg[:160]}\n")
                        # 401/403 等鉴权错误不必继续换参数
                        if r["status"] in (401, 403):
                            print("[FAIL] 鉴权失败，停止探测。", file=sys.stderr)
                            _print_summary(results, success)
                            return 1
                        # 404 端点不存在，换下一个端点
                        if r["status"] == 404:
                            break

    _print_summary(results, success)
    if not success:
        print("\n[FAIL] 所有候选组合均失败。请检查 base_url / model / 中转文档。", file=sys.stderr)
        print("[提示] 若中转使用 /v1 路径但模型名不同（如 dall-e-3 / flux），请调整 .env 的 IMAGE_MODEL 后重试。", file=sys.stderr)
        return 1
    return 0


def _print_summary(results: list[dict], success: dict | None) -> None:
    print("\n========== 探测汇总 ==========")
    print(f"尝试组合数: {len(results)}")
    for i, r in enumerate(results, 1):
        tag = "OK" if r["ok"] else "FAIL"
        print(f"  [{i}] {tag} {r['url']}  size 在 payload={('size' in r['payload_keys'])}  "
              f"status={r['status']}  {r['latency_ms']}ms")
    if success:
        print("\n========== 最终结论 ==========")
        print(f"端点 URL        : {success['url']}")
        print(f"响应取值路径    : {success['data_path']}")
        print(f"取值类型        : {success['value_kind']}")
        print(f"单次生图耗时    : {success['latency_ms']} ms")
        print(f"样本            : {success['sample']}")
        if success["latency_ms"] > 50000:
            print("[决策] 耗时 >50s，Vercel 部署建议改异步（POST 返 job_id + 轮询）。")
        elif success["latency_ms"] > 30000:
            print("[决策] 耗时 30-50s，Vercel Pro 版（60s）可同步，需配置 maxDuration。")
        else:
            print("[决策] 耗时 <30s，Vercel 可同步部署。")
    print("================================")


if __name__ == "__main__":
    sys.exit(main())
