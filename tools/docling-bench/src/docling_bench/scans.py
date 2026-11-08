"""テキスト層のある PDF をページ画像化して PDF に戻し、スキャン相当の PDF を作る。"""

from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium


def make_scanned_pdf(src: Path, dst: Path, *, dpi: int = 200) -> int:
    """全ページを dpi でラスタ化し、テキスト層の無い画像だけの PDF を書く。ページ数を返す。"""
    pdf = pdfium.PdfDocument(src)
    images = [page.render(scale=dpi / 72).to_pil().convert("RGB") for page in pdf]
    dst.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(dst, "PDF", resolution=dpi, save_all=True, append_images=images[1:])
    return len(images)
