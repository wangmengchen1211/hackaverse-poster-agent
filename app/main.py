"""poster-agent FastAPI 入口。

本地：uvicorn app.main:app --reload --port 8766
"""
from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse

from .config import get_settings
from .db import DBError, PosterDB
from .models import GenerateResponse, PosterListItem
from .orchestrator import run_pipeline
from .storage import PosterStorage, StorageError
from .styles import list_styles, style_to_public_dict

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = FastAPI(title="Poster Director Agent", version="0.1.0")

settings = get_settings()

# ── 静态测试页面 ──
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def index():
    """返回 Web 测试页面。"""
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>static/index.html not found</h1>"


@app.get("/outputs/{filename}")
async def serve_output(filename: str):
    """返回本地生成的海报图片。"""
    safe_name = Path(filename).name  # 防路径穿越
    img_path = STATIC_DIR.parent / "outputs" / safe_name
    if img_path.exists():
        return FileResponse(img_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="图片不存在")


@app.get("/api/health")
async def health() -> dict:
    """健康检查 + 配置就绪状态（不泄露任何 key）。"""
    return {
        "status": "ok",
        "service": "poster-agent",
        "env": settings.env,
        "deepseek_ready": settings.deepseek_ready,
        "image_ready": settings.image_ready,
        "supabase_ready": settings.supabase_ready,
        "image_model": settings.image_model,
    }


@app.get("/api/styles")
async def get_styles() -> dict:
    """返回 6 种风格元数据（供前端选择器展示）。"""
    return {
        "styles": [style_to_public_dict(s) for s in list_styles()],
        "count": len(list_styles()),
    }


@app.post("/api/generate-poster")
async def generate_poster(
    prd: str = Form("", description="项目 PRD / 描述（选手模式必填，观众模式可省略）"),
    style: str = Form(..., description="daily/cyber/entertainment/character3d/comic/magic"),
    project_name: str = Form(""),
    team_name: str = Form(""),
    event_name: str = Form(""),
    layout_mode: str = Form("fixed", description="fixed / random(需seed) / generate"),
    user_ref: str = Form(""),
    options: str = Form("", description='可选 JSON，如 {"event_name":"..."}'),
    images: list[UploadFile] = File(default=[]),
    qr_code: UploadFile | None = File(default=None, description="可选二维码图片，程序化贴入右下角"),
    mode: str = Form("participant", description="participant=选手模式, audience=观众模式"),
    user_name: str = Form("", description="观众姓名/昵称（audience 模式使用）"),
    impression: str = Form("", description="观众感受/印象（audience 模式使用）"),
) -> dict:
    """主接口：PRD + 照片 + 风格 → 生成报纸海报。

    流程：Step1 解析 → Step2 文案 → Step3 prompt → Step4 生图 → Step5 校验 → Step6 持久化。
    mode=audience 时，跳过 Step1，直接生成观众专属文案。
    """
    # 校验：选手模式必须有 PRD
    if mode != "audience" and not prd:
        raise HTTPException(status_code=400, detail="选手模式必须提供项目描述或 PRD")
    # 限制图片 0-3 张
    image_files = [img for img in images if img.filename]
    if len(image_files) > 3:
        raise HTTPException(status_code=400, detail="最多上传 3 张图片")

    # 合并 options JSON 里的 event_name 等字段
    extra: dict[str, Any] = {}
    if options:
        try:
            extra = json.loads(options)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="options 不是合法 JSON")
    eff_event = event_name or extra.get("event_name", "")

    # 保存用户上传图片为临时文件，供 /images/edits 使用
    # 含安全校验：MIME、大小、Pillow 解码、去 EXIF、UUID 文件名
    image_count = len(image_files)
    user_image_paths: list[str] = []
    if image_files:
        uploads_dir = STATIC_DIR.parent / "uploads"
        uploads_dir.mkdir(exist_ok=True)
        for img in image_files:
            raw = await img.read()
            # 1. 大小校验
            if len(raw) > settings.image_max_size_mb * 1024 * 1024:
                raise HTTPException(
                    status_code=400,
                    detail=f"图片 {img.filename} 超过 {settings.image_max_size_mb}MB 限制",
                )
            # 2. MIME 校验
            mime = img.content_type or ""
            if mime not in settings.image_allowed_mime_list:
                raise HTTPException(
                    status_code=400,
                    detail=f"不支持的图片格式 {mime}，仅允许 {', '.join(settings.image_allowed_mime_list)}",
                )
            # 3. Pillow 解码 + 去 EXIF + 尺寸校验
            try:
                from PIL import Image as PILImage
                pil_img = PILImage.open(BytesIO(raw))
                # 去 EXIF（GPS/设备信息）
                data = list(pil_img.getdata())
                pil_img_no_exif = PILImage.new(pil_img.mode, pil_img.size)
                pil_img_no_exif.putdata(data)
                # 尺寸校验
                w, h = pil_img_no_exif.size
                if max(w, h) > settings.image_max_dimension:
                    ratio = settings.image_max_dimension / max(w, h)
                    new_size = (int(w * ratio), int(h * ratio))
                    pil_img_no_exif = pil_img_no_exif.resize(new_size, PILImage.LANCZOS)
                    logger.info("图片缩放: %dx%d → %dx%d", w, h, *new_size)
            except Exception as exc:
                raise HTTPException(
                    status_code=400, detail=f"图片解码失败: {exc}"
                ) from exc
            # 4. UUID 文件名（防路径穿越和重名）
            ext_map = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
            ext = ext_map.get(mime, "png")
            fname = f"{uuid.uuid4().hex}.{ext}"
            fpath = uploads_dir / fname
            # 保存去 EXIF 后的图片
            save_buf = BytesIO()
            pil_img_no_exif.save(save_buf, format="PNG")
            fpath.write_bytes(save_buf.getvalue())
            user_image_paths.append(str(fpath))
            logger.info("保存用户图片(安全校验通过): %s", fpath)

    # 保存二维码图片（UUID 文件名）
    qr_code_path: str | None = None
    if qr_code and qr_code.filename:
        uploads_dir = STATIC_DIR.parent / "uploads"
        uploads_dir.mkdir(exist_ok=True)
        qr_ext = Path(qr_code.filename).suffix.lstrip(".") or "png"
        qr_fname = f"qr_{uuid.uuid4().hex}.{qr_ext}"
        qr_fpath = uploads_dir / qr_fname
        qr_fpath.write_bytes(await qr_code.read())
        qr_code_path = str(qr_fpath)
        logger.info("保存二维码图片: %s", qr_fpath)

    # 跑工作流
    try:
        orch = await run_pipeline(
            prd=prd,
            style_key=style,
            project_name=project_name,
            team_name=team_name,
            event_name=eff_event,
            image_count=image_count,
            user_image_paths=user_image_paths or None,
            qr_code_path=qr_code_path,
            layout_mode=layout_mode,
            user_ref=user_ref,
            mode=mode,
            user_name=user_name,
            impression=impression,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("工作流执行失败")
        raise HTTPException(status_code=500, detail=f"生成失败: {exc}") from exc

    resp = orch.response

    # Step6：持久化（图入 Storage，记录入 DB）
    image_url = ""
    storage_path = None
    poster_id = None
    local_filename = None

    if orch.image_bytes:
        # 先存一份到本地 outputs（无论 Supabase 是否可用都有保底）
        try:
            outputs_dir = STATIC_DIR.parent / "outputs"
            outputs_dir.mkdir(exist_ok=True)
            local_filename = f"poster_{int(time.time())}.png"
            local_path = outputs_dir / local_filename
            local_path.write_bytes(orch.image_bytes)
            logger.info("图片已存本地: %s", local_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("本地保存图片失败: %s", exc)

        # 尝试上传到 Supabase Storage
        try:
            storage = PosterStorage()
            image_url, storage_path = storage.upload_poster_image(orch.image_bytes)
        except StorageError as exc:
            logger.error("图片上传 Storage 失败，回退本地/base64: %s", exc)
            # Supabase 不可用 → 回退：本地 URL + base64 data URI
            if local_filename:
                image_url = f"/outputs/{local_filename}"
            else:
                # 最终兜底：base64 直接塞进 response
                b64 = base64.b64encode(orch.image_bytes).decode("ascii")
                image_url = f"data:image/png;base64,{b64}"

    # 落库（即使生图/上传失败，文案也落库以便排查）
    record = {
        "user_ref": user_ref or None,
        "project_name": project_name or None,
        "team_name": team_name or None,
        "style": style,
        "layout_used": resp.layout_used,
        "poster_copy": resp.poster_copy.model_dump(),
        "image_url": image_url,
        "image_storage_path": storage_path,
        "generation_meta": resp.generation_meta.model_dump(),
        "status": resp.status if image_url else "failed",
    }
    try:
        db = PosterDB()
        saved = db.save_poster(record)
        poster_id = saved.get("id")
    except DBError as exc:
        logger.error("落库失败（不影响返回图片）: %s", exc)

    resp.poster_id = poster_id
    resp.image_url = image_url
    return resp.model_dump()


@app.get("/api/posters")
async def list_posters(
    user_ref: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """查询海报历史列表（前端共享 DB，也可直接用 supabase-js 查 posters 表）。"""
    try:
        db = PosterDB()
        rows = db.list_posters(user_ref=user_ref, limit=limit, offset=offset)
    except DBError as exc:
        raise HTTPException(status_code=503, detail=f"数据库不可用: {exc}") from exc
    return {
        "items": [PosterListItem.from_row(r).model_dump() for r in rows],
        "count": len(rows),
    }


@app.get("/api/posters/{poster_id}")
async def get_poster(poster_id: str) -> dict:
    """查询单张海报详情。"""
    try:
        db = PosterDB()
        row = db.get_poster(poster_id)
    except DBError as exc:
        raise HTTPException(status_code=503, detail=f"数据库不可用: {exc}") from exc
    if not row:
        raise HTTPException(status_code=404, detail="海报不存在")
    return row


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=True)
