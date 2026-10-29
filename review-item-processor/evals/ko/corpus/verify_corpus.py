#!/usr/bin/env python3
"""
Verify the Korean evaluation fixtures (corpus D1–D5) against their manifests.

Checks, for every document referenced by the suites:
  - the file exists (external D2/D3 files: hint to run fetch_external.sh)
  - PDFs open with both pypdf and pdfium; PNGs open with Pillow
  - sha256 and page count match the manifest entry
  - scan variants (IMGPDF) have no text layer
  - PNG pages stay within the Bedrock Converse image limits (3.75 MB, 8000 px)

Exit status 1 when any check fails, so the script can gate a run.

Usage (from review-item-processor/):
    uv run --extra evals python evals/ko/corpus/verify_corpus.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent                 # evals/ko/corpus
KO_DIR = HERE.parent
REPO_ROOT = KO_DIR.parent.parent.parent

SUITES = [
    # (suite, manifest, required)
    (KO_DIR / "examples" / "korean_examples_suite.json", KO_DIR / "examples" / "fixtures_manifest.json", True),
    (KO_DIR / "examples" / "korean_examples_image_suite.json", KO_DIR / "examples" / "image_fixtures_manifest.json", False),
    (HERE / "corpus_suite.json", HERE / "corpus_manifest.json", True),
]
MAX_IMAGE_BYTES = 3_750_000
MAX_IMAGE_SIDE = 8000


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pdf_info(path: Path) -> tuple[int, int]:
    """(pages, text chars) via pypdf; also opens the file with pdfium to prove it renders."""
    from pypdf import PdfReader
    import pypdfium2 as pdfium

    reader = PdfReader(str(path))
    chars = sum(len(p.extract_text() or "") for p in reader.pages)
    doc = pdfium.PdfDocument(str(path))
    try:
        if len(doc) != len(reader.pages):
            raise ValueError(f"pypdf/pdfium page count differ ({len(reader.pages)} vs {len(doc)})")
    finally:
        doc.close()
    return len(reader.pages), chars


def _png_info(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as im:
        im.verify()
    with Image.open(path) as im:
        return im.size


def main() -> int:
    problems: list[str] = []
    checked = 0
    referenced: dict[Path, dict] = {}   # file -> {variant, cases}

    suites_checked = 0
    for suite_path, manifest_path, required in SUITES:
        if not suite_path.exists():
            if required:
                problems.append(f"suite missing: {suite_path.relative_to(REPO_ROOT)} (run its generate script)")
            else:
                print(f"note: {suite_path.relative_to(REPO_ROOT)} not generated (generate_suite.py --with-image-variants); skipped")
            continue
        suites_checked += 1
        cases = json.loads(suite_path.read_text(encoding="utf-8"))
        manifest = {REPO_ROOT / m["path"]: m for m in json.loads(manifest_path.read_text(encoding="utf-8"))} if manifest_path.exists() else {}
        if not manifest:
            problems.append(f"manifest missing or empty: {manifest_path.relative_to(REPO_ROOT)}")

        for case in cases:
            base = (suite_path.parent / case["input"].get("fixtures_dir", "")).resolve()
            for doc in case["input"]["document_paths"]:
                entry = referenced.setdefault(base / doc, {"variant": case["metadata"].get("variant", "pdf"), "cases": 0,
                                                            "manifest": manifest.get(base / doc), "suite": suite_path.name})
                entry["cases"] += 1

    for path, info in sorted(referenced.items()):
        rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
        checked += 1
        if not path.exists():
            hint = " -> bash evals/ko/corpus/fetch_external.sh" if "external" in path.parts else \
                   " -> evals/ko/corpus/rasterize_pdf.py --png" if "image" in path.parts else \
                   " -> evals/ko/corpus/d5_mixed_document.py" if "d5" in path.parts else ""
            problems.append(f"missing: {rel} ({info['cases']} cases){hint}")
            continue
        m = info["manifest"]
        if m is None:
            problems.append(f"not in manifest: {rel} (regenerate the suite)")
        else:
            actual = _sha256(path)
            if actual != m["sha256"]:
                problems.append(f"sha256 mismatch: {rel} (manifest {m['sha256'][:12]}, file {actual[:12]})")
        try:
            if path.suffix.lower() == ".pdf":
                pages, chars = _pdf_info(path)
                if m and m.get("pages") not in (None, pages):
                    problems.append(f"page count {pages} != manifest {m['pages']}: {rel}")
                if info["variant"] == "imgpdf" and chars > 0:
                    problems.append(f"scan variant has a text layer ({chars} chars): {rel}")
                if info["variant"] == "pdf" and chars == 0:
                    problems.append(f"text PDF has no extractable text: {rel}")
            elif path.suffix.lower() == ".png":
                w, h = _png_info(path)
                if path.stat().st_size > MAX_IMAGE_BYTES or max(w, h) > MAX_IMAGE_SIDE:
                    problems.append(f"PNG exceeds Bedrock image limits ({path.stat().st_size} bytes, {w}x{h}): {rel}")
            else:
                problems.append(f"unsupported fixture type: {rel}")
        except Exception as exc:  # noqa: BLE001 - report every unreadable file
            problems.append(f"cannot open {rel}: {exc}")

    print(f"checked {checked} fixtures referenced by {suites_checked} suite(s)")
    if problems:
        print(f"{len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("all fixtures present, readable, manifest sha256/pages match, scan variants have no text layer")
    return 0


if __name__ == "__main__":
    sys.exit(main())
