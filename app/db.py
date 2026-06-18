"""Supabase Postgres 接入层（posters 表 CRUD）。

使用 service_role key（绕过 RLS），负责写；前端用 anon key 读。
"""
from __future__ import annotations

import logging
from typing import Any

from .config import get_settings

logger = logging.getLogger(__name__)


class DBError(RuntimeError):
    pass


class PosterDB:
    """posters 表的薄封装。"""

    def __init__(self, settings=None) -> None:
        self.s = settings or get_settings()
        self._client = None

    @property
    def client(self):
        if not self.s.supabase_ready:
            raise DBError("SUPABASE_URL / SUPABASE_SERVICE_KEY 未配置")
        if self._client is None:
            # 延迟导入，避免未装 supabase 时 import 失败
            from supabase import create_client, Client

            self._client = create_client(self.s.supabase_url, self.s.supabase_service_key)
        return self._client

    def save_poster(self, record: dict[str, Any]) -> dict[str, Any]:
        """插入一条 poster 记录，返回含 id 的完整记录。"""
        try:
            resp = self.client.table("posters").insert(record).execute()
        except Exception as exc:  # noqa: BLE001
            logger.exception("save_poster 插入失败")
            raise DBError(f"save_poster 失败: {exc}") from exc
        if not resp.data:
            raise DBError(f"save_poster 无返回数据: {resp!r}")
        return resp.data[0]

    def list_posters(
        self,
        *,
        user_ref: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """查询海报列表（默认按时间倒序）。"""
        try:
            q = self.client.table("posters").select("*").order("created_at", desc=True)
            if user_ref:
                q = q.eq("user_ref", user_ref)
            resp = q.limit(limit).offset(offset).execute()
        except Exception as exc:  # noqa: BLE001
            logger.exception("list_posters 查询失败")
            raise DBError(f"list_posters 失败: {exc}") from exc
        return resp.data or []

    def get_poster(self, poster_id: str) -> dict[str, Any] | None:
        """查询单条海报。"""
        try:
            resp = (
                self.client.table("posters")
                .select("*")
                .eq("id", poster_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("get_poster 查询失败")
            raise DBError(f"get_poster 失败: {exc}") from exc
        return resp.data[0] if resp.data else None
