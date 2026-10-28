"""Bounded local decoding. PDFium calls are serialized (it is not thread safe)."""

import math
import threading
from contextlib import closing
from io import BytesIO

import pypdfium2 as pdfium
from fastapi import HTTPException
from PIL import Image
from pypdf import PdfReader

from app.assignments import decode_image

_pdf_lock = threading.Lock()


def prepare_document(raw):
    if not raw.startswith(b"%PDF-"):
        clean = decode_image(raw)
        with Image.open(BytesIO(raw)) as im:
            suffix, mime = {
                "PNG": ("png", "image/png"),
                "JPEG": ("jpg", "image/jpeg"),
                "WEBP": ("webp", "image/webp"),
            }[im.format]
        return suffix, mime, [{"png": clean, "text": "", "type": "image"}]
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(413, "PDF 超过 20 MiB")
    try:
        reader = PdfReader(BytesIO(raw))
        if reader.is_encrypted:
            raise HTTPException(422, "暂不支持加密 PDF，请先导出未加密副本")
        if not 1 <= len(reader.pages) <= 10:
            raise HTTPException(413, "PDF 仅支持 1–10 页，请拆分后导入；未截取任何页面")
        pages = []
        with _pdf_lock, pdfium.PdfDocument(raw) as doc:
            for i in range(len(doc)):
                with closing(doc[i]) as page:
                    width, height = page.get_size()
                    if not all(math.isfinite(n) and n > 0 for n in (width, height)):
                        raise HTTPException(422, "PDF 页面尺寸无效")
                    # Render legible pages without silently downscaling huge posters.
                    scale = 2
                    if (
                        math.ceil(width * scale) * math.ceil(height * scale)
                        > 20_000_000
                    ):
                        raise HTTPException(
                            413, "PDF 单页渲染超过 20 百万像素，请缩小页面后导入"
                        )
                    with closing(page.get_textpage()) as textpage:
                        text = textpage.get_text_bounded()
                    if len(text) > 100_000:
                        raise HTTPException(
                            413, "PDF 单页文字超过 10 万字符，请拆分后导入"
                        )
                    bitmap = page.render(scale=scale)
                    try:
                        out = BytesIO()
                        bitmap.to_pil().convert("RGB").save(out, format="PNG")
                        pages.append(
                            {
                                "png": out.getvalue(),
                                "text": text,
                                "type": "text_pdf" if text.strip() else "scanned_pdf",
                            }
                        )
                    finally:
                        bitmap.close()
        return "pdf", "application/pdf", pages
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, "PDF 损坏、加密或无法读取，请导出副本后重试") from exc
