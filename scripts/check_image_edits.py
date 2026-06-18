#!/usr/bin/env python3
"""测试 llmgateway 是否支持 /images/edits 端点（图生图）。"""
import os, sys, time, base64, io
from pathlib import Path

try:
    import httpx
except ImportError:
    print("[FATAL] 缺少 httpx"); sys.exit(2)

# 加载 .env.local
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent / ".env.local"
    if not env_path.exists():
        env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[INFO] 已加载 {env_path}")
except ImportError:
    print("[WARN] 缺少 python-dotenv")

API_KEY = os.getenv("IMAGE_API_KEY", "").strip()
BASE_URL = os.getenv("IMAGE_BASE_URL", "https://www.llmgateway.cn").strip().rstrip("/")
MODEL = os.getenv("IMAGE_MODEL", "gpt-image-2").strip()

if not API_KEY:
    print("[FAIL] IMAGE_API_KEY 为空"); sys.exit(1)

# 用 Pillow 生成一张 100x100 的测试图
try:
    from PIL import Image
    img = Image.new("RGB", (256, 256), color=(100, 149, 237))  # 矢车菊蓝
    img_bytes_io = io.BytesIO()
    img.save(img_bytes_io, format="PNG")
    test_image_bytes = img_bytes_io.getvalue()
    print(f"[INFO] 生成测试图: {len(test_image_bytes)} bytes")
except ImportError:
    print("[FATAL] 缺少 Pillow: pip install Pillow"); sys.exit(2)

# 候选端点
ENDPOINTS = [
    f"{BASE_URL}/v1/images/edits",
    f"{BASE_URL}/images/edits",
]

PROMPT = "在这张蓝色图片中央画一只白色的猫，保持原图的蓝色背景"

def try_edits(url):
    print(f"\n[TRY] POST {url}")
    headers = {"Authorization": f"Bearer {API_KEY}"}
    files = {"image": ("test.png", test_image_bytes, "image/png")}
    data = {"model": MODEL, "prompt": PROMPT, "n": "1", "size": "1024x1024"}
    
    t0 = time.time()
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, headers=headers, files=files, data=data)
    except Exception as exc:
        elapsed = int((time.time() - t0) * 1000)
        print(f"  -> ERROR ({elapsed}ms): {exc}")
        return False
    
    elapsed = int((time.time() - t0) * 1000)
    print(f"  -> HTTP {resp.status_code}  ({elapsed}ms)")
    
    if resp.status_code != 200:
        print(f"  -> body: {resp.text[:500]}")
        return False
    
    try:
        body = resp.json()
        items = body.get("data", [])
        if items and items[0].get("b64_json"):
            b64_len = len(items[0]["b64_json"])
            print(f"  -> OK! data[0].b64_json length={b64_len} (~{b64_len//1024}KB)")
            # 保存测试结果
            out_path = Path(__file__).resolve().parent.parent / "outputs" / "test_edits_result.png"
            out_path.parent.mkdir(exist_ok=True)
            out_path.write_bytes(base64.b64decode(items[0]["b64_json"]))
            print(f"  -> 已保存到 {out_path}")
            return True
        elif items and items[0].get("url"):
            print(f"  -> OK! data[0].url = {items[0]['url'][:100]}")
            return True
        else:
            print(f"  -> 响应结构异常: {str(body)[:300]}")
            return False
    except Exception as exc:
        print(f"  -> JSON 解析失败: {exc}")
        print(f"  -> body: {resp.text[:300]}")
        return False

print(f"=== 测试 /images/edits 端点支持情况 ===")
print(f"[INFO] base_url = {BASE_URL}")
print(f"[INFO] model    = {MODEL}")
print(f"[INFO] prompt   = {PROMPT}")

success = False
for url in ENDPOINTS:
    if try_edits(url):
        success = True
        break

print(f"\n=== 结论 ===")
if success:
    print(f"[OK] llmgateway 支持 /images/edits！用户照片可直接传给 gpt-image-2。")
else:
    print(f"[FAIL] llmgateway 不支持 /images/edits。")
    print(f"       需要换方案：视觉理解照片内容 → 文字描述写进 prompt → 纯文生图。")
