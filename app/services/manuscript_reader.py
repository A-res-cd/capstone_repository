"""Bounded, private page rendering; no original PDF bytes reach the reader."""
from datetime import datetime, timezone
from contextlib import closing
from functools import lru_cache
from io import BytesIO
from math import isfinite
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import pypdfium2 as pdfium

from app.utils.pdf_rendering import pdfium_lock


MAX_PAGE_DIMENSION = 1800


def _file_version(path):
    file = Path(path).resolve()
    stat = file.stat()
    return str(file), stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=128)
def _page_count(path, modified, size):
    with pdfium_lock, pdfium.PdfDocument(path) as document:
        count = len(document)
        if not count:
            raise ValueError("Manuscript has no pages.")
        return count


def page_count(path):
    return _page_count(*_file_version(path))


@lru_cache(maxsize=24)
def _render_page(path, modified, size, page_number):
    # Cache only a bounded number of base images in server memory. File version
    # keys invalidate cached pages when a manuscript is replaced.
    with pdfium_lock, pdfium.PdfDocument(path) as document:
        if page_number < 1 or page_number > len(document):
            raise IndexError("Page not found.")
        with closing(document[page_number - 1]) as page:
            width, height = page.get_size()
            if not all(isfinite(value) and value > 0 for value in (width, height)):
                raise ValueError("Invalid page dimensions.")
            with closing(page.render(scale=MAX_PAGE_DIMENSION / max(width, height))) as bitmap:
                with bitmap.to_pil() as rendered:
                    image = rendered.convert("RGB")
    try:
        with BytesIO() as output:
            image.save(output, format="JPEG", quality=88)
            return output.getvalue()
    finally:
        image.close()


def page_image(path, page_number, user_id, capstone_id, output_format="JPEG"):
    """Return a watermarked image, optionally wrapped in a fresh one-page PDF."""
    base = _render_page(*_file_version(path), page_number)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d UTC")
    label = f"CAPRE | User {user_id} | Manuscript {capstone_id} | {stamp}"
    with Image.open(BytesIO(base)) as source:
        image = source.convert("RGB")
    try:
        font = ImageFont.load_default(size=max(12, min(image.size) // 55))
        with Image.new("RGBA", image.size, (0, 0, 0, 0)) as overlay:
            draw = ImageDraw.Draw(overlay)
            text_width = draw.textlength(label, font=font)
            for fraction in (.15, .4, .65, .9):
                draw.text((max(8, (image.width - text_width) / 2), image.height * fraction),
                          label, font=font, fill=(65, 75, 100, 65))
            image.paste(overlay, (0, 0), overlay)
        with BytesIO() as output:
            # The PDF contains only these watermarked pixels: no original text,
            # attachments, metadata, scripts, or other manuscript pages.
            image.save(output, format=output_format, quality=88, resolution=144)
            return output.getvalue()
    finally:
        image.close()
