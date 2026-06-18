"""Supabase Storage 接入层（海报图上传 + 公共 URL）。"""
from __future__ import annotations

import io
import logging
import time
import uuid

from .config import get_settings

logger = logging.getLogger(__name__)


class StorageError(RuntimeError):
    pass


class PosterStorage:
    """posters bucket 上传/取 URL。"""

    def __init__(self, settings=None) -> None:
        self.s = settings or get_settings()
        self._client = None

    @property
    def client(self):
        if not self.s.supabase_ready:
            raise StorageError("SUPABASE_URL / SUPABASE_SERVICE_KEY 未配置")
        if self._client is None:
            from supabase import create_client

            self._client = create_client(self.s.supabase_url, self.s.supabase_service_key)
        return self._client

    def upload_poster_image(self, image_bytes: bytes, *, ext: str = "png") -> tuple[str, str]:
        """上传海报图到 posters bucket。

        返回 (public_url, storage_path)。
        storage_path 形如 "2026/06/uuid.png"，用于落库 image_storage_path。
        """
        # 分日期+uuid 存储，避免冲突
        ym = time.strftime("%Y/%m", time.gmtime())
        filename = f"{uuid.uuid4().hex}.{ext.lstrip('.')}"
        storage_path = f"{ym}/{filename}"

        bucket = self.client.storage.from_(self.s.supabase_bucket)
        try:
            # supabase-py upload 接受 file-like 对象
            buf = io.BytesIO(image_bytes)
            bucket.upload(
                file=buf,
                path=storage_path,
                file_options={"content-type": f"image/{ext.lstrip('.')}", "upsert": "false"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("upload_poster_image 上传失败")
            raise StorageError(f"上传失败: {exc}") from exc

        try:
            public_url = bucket.get_public_url(storage_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("get_public_url 失败")
            raise StorageError(f"get_public_url 失败: {exc}") from exc

        return public_url, storage_path
