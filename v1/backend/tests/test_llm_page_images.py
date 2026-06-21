"""Page-image shaping for multimodal extraction requests."""

from __future__ import annotations

import io

from PIL import Image

from app.services.pipeline.llm import (
    _MAX_LLM_IMAGE_DIMENSION,
    _fit_page_image_for_llm,
)


def _png_bytes(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color="white").save(buf, format="PNG")
    return buf.getvalue()


def test_fit_page_image_downscales_over_2000px():
    jpeg, media_type = _fit_page_image_for_llm(_png_bytes(2400, 3200))
    assert media_type == "image/jpeg"
    img = Image.open(io.BytesIO(jpeg))
    assert max(img.size) <= _MAX_LLM_IMAGE_DIMENSION


def test_fit_page_image_keeps_small_images():
    jpeg, media_type = _fit_page_image_for_llm(_png_bytes(800, 600))
    assert media_type == "image/jpeg"
    img = Image.open(io.BytesIO(jpeg))
    assert max(img.size) == 800
