#!/usr/bin/env python3
"""
Generate the PDF documents (and the KB_01 statute text file) for the Korean
examples under examples/ko/.

Usage (from .claude/skills/add-example):
    uv run --no-project --with "reportlab>=4" --with "fonttools>=4.40" \
        python scripts/create_korean_example_pdfs.py [--font /path/to/NotoSansKR[wght].ttf] [--only 001,002]

Fonts
-----
Korean text needs a font with Hangul glyphs, and the reportlab CID fonts used by
the Japanese examples have none.  This script embeds Noto Sans KR (SIL Open Font
License 1.1).  The variable font (~10 MB) is NOT committed to the repository; it
is downloaded from a pinned google/fonts commit into ~/.cache/rapid-ko-fonts/,
verified by sha256, and two static instances (Regular 400 / Bold 700) are built
with fontTools so that reportlab can embed them.  Pass --font to use a local
copy instead (offline machines).

Content lives in scripts/korean_examples/ (one module per use case); statute
text in scripts/korean_examples/law_texts.py is reproduced verbatim from
law.go.kr and must not be edited by hand.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from urllib.request import urlopen
from xml.sax.saxutils import escape

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
except ImportError:  # pragma: no cover
    print('reportlab is required: uv run --no-project --with "reportlab>=4" --with "fonttools>=4.40" python scripts/create_korean_example_pdfs.py')
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from korean_examples import USE_CASES  # noqa: E402
from korean_examples import uc001_privacy  # noqa: E402
from korean_examples import law_texts  # noqa: E402

PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent.parent
EXAMPLES_KO = PROJECT_ROOT / "examples" / "ko"

# google/fonts commit "Noto Sans KR hotfix2 (#5532)", 2022-12-09
FONT_COMMIT = "4efc2774c63917927efe769ca845def6bd6debae"
FONT_URL = f"https://raw.githubusercontent.com/google/fonts/{FONT_COMMIT}/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf"
FONT_SHA256 = "194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252"
OFL_URL = f"https://raw.githubusercontent.com/google/fonts/{FONT_COMMIT}/ofl/notosanskr/OFL.txt"
OFL_SHA256 = "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9"
FONT_CACHE = Path.home() / ".cache" / "rapid-ko-fonts"

FONT_REGULAR = "NotoSansKR"
FONT_BOLD = "NotoSansKR-Bold"


# ----------------------------------------------------------------------------- fonts
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path, sha256: str) -> Path:
    if dest.exists() and _sha256(dest) == sha256:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {url}")
    with urlopen(url, timeout=60) as resp:
        data = resp.read()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise SystemExit(f"sha256 mismatch for {url}; refusing to use the file")
    dest.write_bytes(data)
    return dest


def _static_instance(variable_ttf: Path, weight: int, dest: Path) -> Path:
    """Build a static instance (wght=weight) of the variable font with fontTools."""
    if dest.exists():
        return dest
    try:
        from fontTools.ttLib import TTFont as FTFont
        from fontTools.varLib import instancer
    except ImportError:  # pragma: no cover
        raise SystemExit('fonttools is required: add --with "fonttools>=4.40" to the uv run command')
    font = FTFont(str(variable_ttf))
    static = instancer.instantiateVariableFont(font, {"wght": weight}, inplace=False)
    dest.parent.mkdir(parents=True, exist_ok=True)
    static.save(str(dest))
    return dest


def register_fonts(local_variable_font: Path | None) -> None:
    if local_variable_font is not None:
        variable = local_variable_font
        if not variable.exists():
            raise SystemExit(f"font not found: {variable}")
    else:
        variable = _download(FONT_URL, FONT_CACHE / "NotoSansKR[wght].ttf", FONT_SHA256)
        _download(OFL_URL, FONT_CACHE / "OFL.txt", OFL_SHA256)
    regular = _static_instance(variable, 400, FONT_CACHE / "NotoSansKR-Regular.static.ttf")
    bold = _static_instance(variable, 700, FONT_CACHE / "NotoSansKR-Bold.static.ttf")
    pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(regular)))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold)))
    pdfmetrics.registerFontFamily(FONT_REGULAR, normal=FONT_REGULAR, bold=FONT_BOLD, italic=FONT_REGULAR, boldItalic=FONT_BOLD)


# ----------------------------------------------------------------------------- styles
def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName=FONT_REGULAR, fontSize=9.5, leading=14.5, wordWrap="CJK")
    return {
        "title": ParagraphStyle("title", parent=base, fontName=FONT_BOLD, fontSize=18, leading=24, alignment=TA_CENTER, spaceAfter=4),
        "subtitle": ParagraphStyle("subtitle", parent=base, fontSize=9, leading=13, alignment=TA_CENTER, textColor=colors.HexColor("#4B5563"), spaceAfter=14),
        "h2": ParagraphStyle("h2", parent=base, fontName=FONT_BOLD, fontSize=12.5, leading=17, textColor=colors.HexColor("#1E3A8A"), spaceBefore=12, spaceAfter=5),
        "h3": ParagraphStyle("h3", parent=base, fontName=FONT_BOLD, fontSize=10.5, leading=15, spaceBefore=8, spaceAfter=3),
        "p": ParagraphStyle("p", parent=base, spaceAfter=5),
        "bullet": ParagraphStyle("bullet", parent=base, leftIndent=12, bulletIndent=2, spaceAfter=2),
        "law": ParagraphStyle("law", parent=base, fontSize=8.6, leading=12.6, textColor=colors.HexColor("#1F2937")),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8.2, leading=11.4),
        "cell_head": ParagraphStyle("cell_head", parent=base, fontName=FONT_BOLD, fontSize=8.2, leading=11.4, alignment=TA_CENTER),
        "footer": ParagraphStyle("footer", parent=base, fontSize=7.2, leading=9.5, textColor=colors.HexColor("#6B7280")),
    }


def _law_blocks(text: str, style: ParagraphStyle) -> list:
    """Render a verbatim statute block, one box per article so long statutes can split across pages.

    Line breaks and leading indentation are preserved.
    """
    import re

    articles: list[list[str]] = []
    for raw in text.split("\n"):
        if re.match(r"^제\d+조", raw) or not articles:
            articles.append([])
        articles[-1].append(raw)

    flowables = []
    for lines in articles:
        rendered = []
        for raw in lines:
            stripped = raw.lstrip(" ")
            indent = len(raw) - len(stripped)
            rendered.append("&nbsp;" * indent + escape(stripped))
        para = Paragraph("<br/>".join(rendered), style)
        box = Table([[para]], colWidths=["100%"])
        box.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#9CA3AF")),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F9FAFB")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        flowables.append(box)
        flowables.append(Spacer(1, 3))
    return flowables


def _table(spec: dict, st: dict, avail_width: float) -> Table:
    header = spec["header"]
    rows = spec["rows"]
    widths = spec.get("widths") or [1 / len(header)] * len(header)
    size = spec.get("font_size")
    cell = st["cell"] if size is None else ParagraphStyle("cell_s", parent=st["cell"], fontSize=size, leading=size * 1.35)
    head = st["cell_head"] if size is None else ParagraphStyle("head_s", parent=st["cell_head"], fontSize=size, leading=size * 1.35)
    data = [[Paragraph(escape(str(h)), head) for h in header]]
    for r in rows:
        data.append([Paragraph(escape(str(c)).replace("\n", "<br/>"), cell) for c in r])
    t = Table(data, colWidths=[w * avail_width for w in widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9CA3AF")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DBEAFE")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def build_pdf(doc: dict, out_path: Path) -> None:
    st = _styles()
    margin = 18 * mm
    pdf = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=margin, rightMargin=margin, topMargin=20 * mm, bottomMargin=20 * mm,
        title=doc["title"], author="RAPID example (fictional document)", lang="ko",
        invariant=True,  # deterministic bytes: no creation timestamp / random document ID
    )
    avail = A4[0] - 2 * margin
    story = [Paragraph(escape(doc["title"]), st["title"]), Paragraph(escape(doc["subtitle"]), st["subtitle"])]
    for block in doc["blocks"]:
        kind = block[0]
        if kind == "h2":
            story.append(Paragraph(escape(block[1]), st["h2"]))
        elif kind == "h3":
            story.append(Paragraph(escape(block[1]), st["h3"]))
        elif kind == "p":
            story.append(Paragraph(escape(block[1]), st["p"]))
        elif kind == "bullets":
            for item in block[1]:
                story.append(Paragraph(escape(item), st["bullet"], bulletText="•"))
            story.append(Spacer(1, 3))
        elif kind == "law":
            story.extend(_law_blocks(block[1], st["law"]))
            story.append(Spacer(1, 3))
        elif kind == "table":
            story.append(_table(block[1], st, avail))
            story.append(Spacer(1, 6))
        elif kind == "spacer":
            story.append(Spacer(1, block[1]))
        elif kind == "pagebreak":
            story.append(PageBreak())
        else:
            raise ValueError(f"unknown block type: {kind}")

    header_label = doc["header_label"]
    footer_text = doc["footer"]

    def decorate(canvas, _doc):
        canvas.saveState()
        canvas.setFont(FONT_REGULAR, 7.5)
        canvas.setFillColor(colors.HexColor("#6B7280"))
        canvas.drawString(margin, A4[1] - 12 * mm, header_label)
        canvas.drawRightString(A4[0] - margin, A4[1] - 12 * mm, f"{canvas.getPageNumber()}")
        canvas.setStrokeColor(colors.HexColor("#D1D5DB"))
        canvas.line(margin, A4[1] - 13.5 * mm, A4[0] - margin, A4[1] - 13.5 * mm)
        footer = Paragraph(escape(footer_text), st["footer"])
        w, h = footer.wrap(avail, 20 * mm)
        footer.drawOn(canvas, margin, 7 * mm)
        canvas.restoreState()

    pdf.build(story, onFirstPage=decorate, onLaterPages=decorate)


def write_kb01(out_dir: Path) -> Path:
    path = out_dir / uc001_privacy.KB01_FILENAME
    body = "\n\n".join([uc001_privacy.KB01_HEADER, "「개인정보 보호법」", law_texts.PIPA_ART_30, "「개인정보 보호법 시행령」", law_texts.PIPA_DECREE_ART_31])
    path.write_text(body + "\n", encoding="utf-8")
    return path


# ----------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--font", type=Path, default=None, help="local NotoSansKR[wght].ttf (skips the download)")
    ap.add_argument("--only", default="", help="comma separated use case numbers, e.g. 001,003")
    ap.add_argument("--out", type=Path, default=EXAMPLES_KO, help=f"examples/ko directory (default: {EXAMPLES_KO})")
    args = ap.parse_args()

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    register_fonts(args.font)

    generated: list[Path] = []
    for uc in USE_CASES:
        number = uc.USE_CASE_DIR.split("_")[2]
        if only and number not in only:
            continue
        out_dir = args.out / uc.USE_CASE_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        for doc in (uc.CHECKLIST, uc.REVIEW):
            path = out_dir / doc["filename"]
            build_pdf(doc, path)
            generated.append(path)
        if uc is uc001_privacy:
            kb_dir = out_dir / "knowledge_base_sources"
            kb_dir.mkdir(exist_ok=True)
            generated.append(write_kb01(kb_dir))

    for p in generated:
        print(f"  ✓ {p.relative_to(PROJECT_ROOT) if p.is_relative_to(PROJECT_ROOT) else p}  ({p.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
