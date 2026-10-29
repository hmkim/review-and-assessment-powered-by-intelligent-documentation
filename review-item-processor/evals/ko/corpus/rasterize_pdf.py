#!/usr/bin/env python3
"""
Rasterise PDFs into scan-like fixtures (corpus D4).

Two outputs per input PDF:
  <out>/<name>.pdf          image-only PDF: every page is a JPEG scan, no text layer.
                            The agent still routes it through the PDF path (routing is by
                            file extension), so this measures Bedrock's handling of a
                            scanned PDF: judgement, language and whether citations exist.
  <out>/<stem>_p01.png ...  one PNG per page (--png). Image files route through the
                            agent's IMAGE path (image model, no citations), which is how
                            scanned pages arrive when users upload photos/scans directly.

Rendering uses pypdfium2 (bundled pdfium, no system packages). Output is deterministic
for a given pdfium/Pillow version; regenerate the manifest if those change.

Usage (from review-item-processor/):
    uv run --extra evals python evals/ko/corpus/rasterize_pdf.py \
        --out evals/ko/examples/fixtures/image/<use case dir> --png <input.pdf> [...]
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path

MAX_IMAGE_BYTES = 3_750_000   # Bedrock Converse per-image limit (3.75 MB)
MAX_IMAGE_SIDE = 8000         # Bedrock Converse max image dimension (px)


def _render_pages(pdf_path: Path, dpi: int, grayscale: bool):
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        for page in doc:
            bitmap = page.render(scale=dpi / 72, grayscale=grayscale)
            image = bitmap.to_pil()
            yield image.convert("L" if grayscale else "RGB")
            page.close()
    finally:
        doc.close()


def _fit_png(image, max_bytes: int = MAX_IMAGE_BYTES) -> bytes:
    """PNG-encode, downscaling in 10% steps until the file fits the Bedrock image limit."""
    scale = 1.0
    while True:
        img = image if scale == 1.0 else image.resize(
            (max(1, int(image.width * scale)), max(1, int(image.height * scale))))
        if max(img.size) > MAX_IMAGE_SIDE:
            scale *= 0.9
            continue
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        if buf.tell() <= max_bytes or scale < 0.3:
            return buf.getvalue()
        scale *= 0.9


def rasterize(pdf_path: Path, out_dir: Path, dpi: int = 300, jpeg_quality: int = 80,
              grayscale: bool = False, png: bool = False) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = list(_render_pages(pdf_path, dpi, grayscale))
    if not pages:
        raise SystemExit(f"no pages rendered from {pdf_path}")

    # Image-only PDF: Pillow's PDF writer stores each page as a DCT (JPEG) stream — no text.
    pdf_out = out_dir / pdf_path.name
    first, rest = pages[0], pages[1:]
    first.save(str(pdf_out), format="PDF", save_all=True, append_images=rest,
               resolution=dpi, quality=jpeg_quality)

    written = {"pdf": pdf_out, "pages": len(pages), "pngs": []}
    if png:
        for i, image in enumerate(pages, start=1):
            png_out = out_dir / f"{pdf_path.stem}_p{i:02d}.png"
            png_out.write_bytes(_fit_png(image))
            written["pngs"].append(png_out)
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", type=Path, help="text-layer PDFs to rasterise")
    ap.add_argument("--out", type=Path, required=True, help="output directory")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--jpeg-quality", type=int, default=80, help="JPEG quality for the image-only PDF")
    ap.add_argument("--grayscale", action="store_true", help="render in grayscale (smaller files)")
    ap.add_argument("--png", action="store_true", help="also write one PNG per page (image-path fixtures)")
    args = ap.parse_args()

    for pdf in args.inputs:
        if not pdf.exists():
            raise SystemExit(f"input not found: {pdf}")
        result = rasterize(pdf, args.out, args.dpi, args.jpeg_quality, args.grayscale, args.png)
        size_kb = result["pdf"].stat().st_size // 1024
        print(f"{pdf.name}: {result['pages']} pages -> {result['pdf']} ({size_kb} KB)"
              + (f", {len(result['pngs'])} PNGs" if result["pngs"] else ""))


if __name__ == "__main__":
    main()
