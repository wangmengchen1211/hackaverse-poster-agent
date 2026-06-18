"""后处理层：Pillow 贴图 + 校正。

职责：
- 二维码程序化贴入右下角预留区域（含白底安全框 + 可扫描校验）
- 后续可扩展：文字清晰度修正、色彩校正等
"""
from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# 最大重试次数（QR 扫描失败时逐步增大尺寸/边距）
MAX_QR_RETRIES = 3


def overlay_qr_code(
    poster_bytes: bytes,
    qr_path: str,
    *,
    margin_pct: float = 0.03,
    size_pct: float = 0.10,
    padding: int = 10,
) -> bytes:
    """在海报右下角贴入二维码（含白底安全框）。

    流程：
    1. 创建白色底板（QR 尺寸 + 2 * padding）
    2. 将 QR alpha 合成到白底中央
    3. 将整体（白底 + QR）贴入海报右下角
    4. 验证二维码可扫描性，失败则自适应重试

    Args:
        poster_bytes: 海报图片的 PNG 字节
        qr_path: 二维码图片文件路径
        margin_pct: 距离右下角的边距比例（默认 3%）
        size_pct: 二维码宽度占页面宽度的比例（默认 10%）
        padding: 白底安全框的内边距像素（默认 10px）

    Returns:
        合成后的 PNG 字节
    """
    try:
        poster = Image.open(BytesIO(poster_bytes)).convert("RGBA")
        qr = Image.open(qr_path).convert("RGBA")
    except Exception as exc:
        logger.error("打开图片或二维码失败: %s", exc)
        return poster_bytes

    pw, ph = poster.size

    # 自适应重试：逐步增大 QR 尺寸和白底边距
    current_size_pct = size_pct
    current_padding = padding
    result_bytes = poster_bytes

    for attempt in range(MAX_QR_RETRIES):
        qr_target = int(pw * current_size_pct)
        qr_resized = qr.resize((qr_target, qr_target), Image.LANCZOS)

        # 创建白底安全框
        plate_size = qr_target + 2 * current_padding
        plate = Image.new("RGBA", (plate_size, plate_size), (255, 255, 255, 255))

        # 将 QR 贴到白底中央
        plate.paste(qr_resized, (current_padding, current_padding), qr_resized)

        # 复制海报（避免多次 paste 污染原图）
        poster_copy = poster.copy()

        # 右下角定位
        margin_x = int(pw * margin_pct)
        margin_y = int(ph * margin_pct)
        x = pw - plate_size - margin_x
        y = ph - plate_size - margin_y

        # 贴入（使用 alpha 合成）
        poster_copy.paste(plate, (x, y), plate)

        # 输出 PNG
        buf = BytesIO()
        poster_copy.save(buf, format="PNG", optimize=True)
        result_bytes = buf.getvalue()

        logger.info(
            "二维码贴入(attempt=%d): poster=%dx%d qr=%dx%d plate=%dx%d padding=%d pos=(%d,%d)",
            attempt + 1, pw, ph, qr_target, qr_target, plate_size, plate_size,
            current_padding, x, y,
        )

        # 可扫描校验
        if _verify_qr_scannable(result_bytes):
            logger.info("✅ 二维码可扫描校验通过 (attempt=%d)", attempt + 1)
            return result_bytes
        else:
            logger.warning("⚠️ 二维码不可扫描 (attempt=%d)，增大尺寸/边距重试", attempt + 1)
            # 逐步增大：size +2%，padding +6px
            current_size_pct += 0.02
            current_padding += 6

    logger.error("❌ 二维码 %d 次重试后仍不可扫描，返回最后一次合成图", MAX_QR_RETRIES)
    return result_bytes


def _verify_qr_scannable(poster_bytes: bytes) -> bool:
    """验证海报中的二维码是否可被扫描。

    优先使用 pyzbar，未安装则跳过校验（返回 True）。
    """
    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
    except ImportError:
        logger.debug("pyzbar 未安装，跳过二维码可扫描校验")
        return True

    try:
        img = Image.open(BytesIO(poster_bytes))
        decoded = pyzbar_decode(img)
        if decoded:
            logger.debug("pyzbar 解码成功: %s", decoded[0].data[:100])
            return True
        return False
    except Exception as exc:
        logger.warning("pyzbar 解码异常: %s", exc)
        return False


def apply_post_processing(
    poster_bytes: bytes,
    *,
    qr_path: str | None = None,
) -> bytes:
    """统一后处理入口。

    当前功能：二维码贴图（含白底安全框 + 可扫描校验）。
    后续可扩展：文字锐化、色彩校正等。
    """
    result = poster_bytes

    if qr_path and Path(qr_path).exists():
        result = overlay_qr_code(result, qr_path)

    return result