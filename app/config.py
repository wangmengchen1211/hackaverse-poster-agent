"""poster-agent 全局配置。

通过 pydantic-settings 从 .env 读取，所有字段均无硬编码值。
宪法 §7：本文件不读取/不写入 .env 本身，仅声明 KEY 名。
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", ".env.local"],
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── 文本 LLM（DeepSeek）──
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")
    deepseek_model: str = Field(default="deepseek-chat", alias="DEEPSEEK_MODEL")

    # ── 生图（gpt-image-2 via llmgateway 中转）──
    image_api_key: str = Field(default="", alias="IMAGE_API_KEY")
    image_base_url: str = Field(default="https://www.llmgateway.cn", alias="IMAGE_BASE_URL")
    image_model: str = Field(default="gpt-image-2", alias="IMAGE_MODEL")
    # Task 0 实测后由用户/部署补全；默认尝试 /v1/images/generations
    image_path: str = Field(default="/v1/images/generations", alias="IMAGE_PATH")

    # ── Supabase ──
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_service_key: str = Field(default="", alias="SUPABASE_SERVICE_KEY")
    supabase_anon_key: str = Field(default="", alias="SUPABASE_ANON_KEY")
    supabase_bucket: str = Field(default="posters", alias="SUPABASE_BUCKET")

    # ── 图片编辑失败策略 ──
    # strict: 生产高保真模式，失败就报错（IMAGE_REFERENCE_LOST）
    # degrade_without_user_image: 不使用用户照片，生成通用配图（需告知用户）
    # ask_retry: 返回错误，提示用户换图或重试
    image_edit_fail_policy: str = Field(
        default="strict", alias="IMAGE_EDIT_FAIL_POLICY"
    )

    # ── 图片安全限制 ──
    image_max_size_mb: int = Field(default=10, alias="IMAGE_MAX_SIZE_MB")
    image_max_dimension: int = Field(default=4096, alias="IMAGE_MAX_DIMENSION")
    image_allowed_mimes: str = Field(
        default="image/png,image/jpeg,image/webp", alias="IMAGE_ALLOWED_MIMES"
    )

    # ── 服务 ──
    port: int = Field(default=8766, alias="PORT")
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        alias="CORS_ORIGINS",
    )
    env: str = Field(default="local", alias="ENV")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def deepseek_ready(self) -> bool:
        return bool(self.deepseek_api_key)

    @property
    def image_ready(self) -> bool:
        return bool(self.image_api_key)

    @property
    def image_allowed_mime_list(self) -> list[str]:
        return [m.strip() for m in self.image_allowed_mimes.split(",") if m.strip()]

    @property
    def supabase_ready(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
