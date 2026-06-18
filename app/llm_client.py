"""LLM 客户端：DeepSeek（文本）+ llmgateway（生图 gpt-image-2）。

关键经验（来自工作区 review.md / 记忆）：
- DeepSeek catch 块必须打印错误，避免静默失败
- 图像 API 必须用 /images/generations 端点，响应取 data[0].b64_json（非 choices）
- 参考图若中转支持 /images/edits 则用，否则退化把视觉描述并入 prompt
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from .config import get_settings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """LLM 调用失败。"""


@dataclass
class ImageResult:
    """生图结果。"""
    image_bytes: bytes       # 解码后的 PNG 字节
    value_kind: str          # "b64" | "url"
    raw: dict[str, Any]      # 原始响应（不含图片数据，便于日志/落库）
    edits_used: bool = False # 是否通过 /images/edits（用户照片被融入）


class LLMClient:
    """统一封装 DeepSeek chat + llmgateway 生图。"""

    def __init__(self, settings=None) -> None:
        self.s = settings or get_settings()

    # ── 文本：DeepSeek ──
    async def chat_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        """调 DeepSeek chat，要求 JSON 输出并解析为 dict。

        若模型不支持 response_format，自动回退到从 content 中抽取 JSON。
        """
        if not self.s.deepseek_ready:
            raise LLMError("DEEPSEEK_API_KEY 未配置")

        url = f"{self.s.deepseek_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.s.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.s.deepseek_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except Exception as exc:  # noqa: BLE001
            # 记忆铁律：catch 必须打印错误
            logger.exception("DeepSeek 请求异常")
            raise LLMError(f"DeepSeek 请求异常: {exc}") from exc

        if resp.status_code != 200:
            logger.error("DeepSeek 非 200: status=%s body=%s", resp.status_code, resp.text[:500])
            raise LLMError(f"DeepSeek HTTP {resp.status_code}: {resp.text[:200]}")

        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            logger.error("DeepSeek 响应结构异常: %s body=%s", exc, resp.text[:500])
            raise LLMError(f"DeepSeek 响应结构异常: {exc}") from exc

        return _extract_json(content)

    # ── 生图：llmgateway gpt-image-2 ──
    async def generate_image(
        self,
        prompt: str,
        *,
        reference_image_paths: list[str] | None = None,
        size: str = "1024x1536",  # 竖版 3:4
        timeout: float = 180.0,
    ) -> ImageResult:
        """调 gpt-image-2 生图。

        优先级：
        1. 若提供参考图且中转支持 /images/edits → 用 edits 端点传参考图
        2. 否则 → /images/generations 纯文生图

        响应统一从 data[0] 取 b64_json 或 url（Task 0 实测确认格式）。
        """
        if not self.s.image_ready:
            raise LLMError("IMAGE_API_KEY 未配置")

        # 参考图：MVP 先尝试 edits 端点；若失败则退化文生图
        edits_used = False
        if reference_image_paths:
            try:
                result = await self._image_edits(prompt, reference_image_paths, size, timeout)
                result.edits_used = True
                return result
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "=== images/edits 失败，用户照片将不会被融入海报！===\n"
                    "错误详情: %s\n"
                    "退化为纯文生图（/images/generations），用户照片将被忽略。",
                    exc,
                )

        result = await self._image_generations(prompt, size, timeout)
        result.edits_used = False
        return result

    async def _image_generations(self, prompt: str, size: str, timeout: float) -> ImageResult:
        url = f"{self.s.image_base_url.rstrip('/')}{self.s.image_path}"
        headers = {
            "Authorization": f"Bearer {self.s.image_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.s.image_model,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "response_format": "b64_json",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except Exception as exc:  # noqa: BLE001
            logger.exception("生图请求异常 generations")
            raise LLMError(f"生图请求异常: {exc}") from exc

        if resp.status_code != 200:
            logger.error("生图非 200: status=%s body=%s", resp.status_code, resp.text[:500])
            raise LLMError(f"生图 HTTP {resp.status_code}: {resp.text[:200]}")

        return _parse_image_response(resp.json())

    async def _image_edits(
        self,
        prompt: str,
        reference_paths: list[str],
        size: str,
        timeout: float,
    ) -> ImageResult:
        """尝试 /images/edits 传参考图（multipart）。

        用户上传的照片作为输入图传给 gpt-image-2 编辑。
        支持多张：第1张作为 image[]，后续图也附加。
        若 edits 失败则退化为纯文生图（由调用方 catch）。
        """
        import os

        edits_path = self.s.image_path.replace("/generations", "/edits")
        if edits_path == self.s.image_path:
            edits_path = "/v1/images/edits"
        url = f"{self.s.image_base_url.rstrip('/')}{edits_path}"
        headers = {
            "Authorization": f"Bearer {self.s.image_api_key}",
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                files = []
                opened = []
                try:
                    for i, p in enumerate(reference_paths):
                        if not os.path.exists(p):
                            raise LLMError(f"用户照片不存在: {p}")
                        f = open(p, "rb")  # noqa: SIM115
                        opened.append(f)
                        ext = os.path.splitext(p)[1].lstrip(".") or "png"
                        files.append(("image[]", (f"user_{i}.{ext}", f, f"image/{ext}")))
                    data = {
                        "model": self.s.image_model,
                        "prompt": prompt,
                        "n": "1",
                        "size": size,
                        "response_format": "b64_json",
                    }
                    logger.info(
                        "images/edits 请求: url=%s model=%s size=%s 图片数=%d",
                        url, self.s.image_model, size, len(reference_paths),
                    )
                    resp = await client.post(url, headers=headers, data=data, files=files)
                finally:
                    for f in opened:
                        f.close()
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("images/edits 请求异常: %s", exc)
            raise

        if resp.status_code != 200:
            raise LLMError(f"images/edits HTTP {resp.status_code}: {resp.text[:200]}")

        return _parse_image_response(resp.json())


def _parse_image_response(data: dict[str, Any]) -> ImageResult:
    """从生图响应取 data[0].b64_json 或 data[0].url。"""
    items = data.get("data")
    if not isinstance(items, list) or not items:
        raise LLMError(f"生图响应无 data 数组: {json.dumps(data, ensure_ascii=False)[:300]}")
    first = items[0]
    if not isinstance(first, dict):
        raise LLMError(f"data[0] 非对象: {first!r}")

    if first.get("b64_json"):
        try:
            img_bytes = base64.b64decode(first["b64_json"])
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"b64_json 解码失败: {exc}") from exc
        # raw 仅保留长度，不存图片数据
        raw = {**data, "data": [{"b64_json_length": len(first["b64_json"])}]}
        return ImageResult(image_bytes=img_bytes, value_kind="b64", raw=raw)

    if first.get("url"):
        # url 模式：再下载一次
        url = str(first["url"])
        try:
            with httpx.Client(timeout=60.0) as c:
                r = c.get(url)
                r.raise_for_status()
                img_bytes = r.content
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"下载图片 URL 失败: {exc}") from exc
        raw = {**data, "data": [{"url": url}]}
        return ImageResult(image_bytes=img_bytes, value_kind="url", raw=raw)

    raise LLMError(f"data[0] 无 b64_json 也无 url: {json.dumps(first, ensure_ascii=False)[:200]}")


def _extract_json(content: str) -> dict[str, Any]:
    """从 LLM 文本中提取 JSON dict（容错：去除 markdown 代码块、截取首尾大括号）。"""
    text = content.strip()
    # 去除 ```json ... ``` 包裹
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    # 直接解析
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        raise LLMError(f"JSON 不是对象: {type(parsed).__name__}")
    except json.JSONDecodeError:
        pass
    # 截取首个 { 到末个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    raise LLMError(f"无法从内容提取 JSON: {content[:300]}")
