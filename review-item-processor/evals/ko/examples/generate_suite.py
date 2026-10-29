#!/usr/bin/env python3
"""
Generate the Korean evaluation suite (korean_examples_suite.json) from the
example content modules under .claude/skills/add-example/scripts/korean_examples/.

Why generate instead of hand-writing the suite
----------------------------------------------
The review targets in examples/ko were written with deliberate defects, and both
the checklist items and the defect list live in those content modules. Deriving
the cases from them keeps a single source of truth: a change to a checklist item
or a defect is reflected here on the next run instead of drifting.

Each case = one checklist item (check_name / check_description taken verbatim
from the checklist PDF content) reviewed against the use case's review target:

  kind "fail"         the item exercises a planted defect -> expected result "fail"
  kind "pass"         the item is satisfied by the document -> expected "pass"
  kind "insufficient" the item needs information that is not in the document
                      -> expected "fail" with insufficient_evidence: true
                      (prompt protocol: confidence <= 0.49, empty extractedText)

Items whose ground truth is debatable are listed in AMBIGUOUS and skipped.

Documents are referenced in place (per-case `fixtures_dir` relative to this
file -> ../../../../examples/ko/<use case>/); nothing is copied. A manifest with
sha256 / size / page count of every referenced PDF is written next to the suite.

Usage (from review-item-processor/):
    uv run python evals/ko/examples/generate_suite.py            # suite + manifest
    uv run python evals/ko/examples/generate_suite.py --with-image-variants
        # also adds IMAGE cases for every "fail" case when the rasterised PDFs exist
        # in evals/ko/examples/fixtures/image/<use case>/<file>.pdf (see M4-b)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent                 # evals/ko/examples
EVALS_DIR = HERE.parent.parent                          # evals/
REPO_ROOT = EVALS_DIR.parent.parent                     # repository root
CONTENT_DIR = REPO_ROOT / ".claude" / "skills" / "add-example" / "scripts"
EXAMPLES_KO = REPO_ROOT / "examples" / "ko"
LANGUAGE_NAME = "Korean"   # what the backend sends for ko (backend/src/utils/language.ts)

sys.path.insert(0, str(CONTENT_DIR))
from korean_examples import uc001_privacy, uc002_building, uc003_risk  # noqa: E402

# --------------------------------------------------------------------------- ground truth
# Checklist item number -> planted defect index (1-based, see each module's DEFECTS /
# examples/ko/README.md). Items not listed here and not AMBIGUOUS/INSUFFICIENT are "pass".
FAIL_ITEMS = {
    "001": {"5": 1, "6": 2, "16": 3, "18": 4, "7": 5, "10": 6},
    "002": {"5": 1, "4": 1, "3": 2, "8": 3},     # item 4 (제외 면적 확인) is the same defect as item 5 seen from the input side
    "003": {"5": 1, "3": 2, "10": 3, "12": 4, "11": 5},
}

# Items that the fictional documents genuinely satisfy -> expected "pass".
PASS_ITEMS = {
    "001": ["1", "2", "3", "4", "9", "11", "14", "20", "24"],
    "002": ["1", "2", "6", "7", "9"],
    "003": ["1", "2", "4", "6", "7", "8", "13", "14"],
}

# Items whose verdict is debatable on the fictional document; excluded on purpose.
AMBIGUOUS = {
    "001": {"8": "추가적 이용·제공 판단 기준 — 문서가 해당 처리를 하지 않음(해당 시 항목)",
            "12": "민감정보 공개 가능성 — 해당 처리 없음", "13": "가명정보 — 해당 처리 없음",
            "15": "제3자 행태정보 — 해당 처리 없음(권장 항목)", "17": "자동화된 결정 — 해당 처리 없음",
            "19": "국내대리인 — 국외 사업자 아님", "21": "고정형 영상기기 — 해당 없음", "22": "이동형 영상기기 — 해당 없음",
            "23": "자율 보호조치 — 권장 항목"},
    "002": {},
    "003": {"9": "위험성 결정: 허용 가능 여부 열이 없어 '기록되었는가'의 판정이 갈림 (결함 2와 겹침)"},
}

# Checks that need information the document cannot contain -> insufficient evidence.
INSUFFICIENT_CASES = {
    "001": [("홈페이지 게재 여부", "이 개인정보 처리방침이 개인정보처리자의 인터넷 홈페이지에 지속적으로 게재되어 있는가(시행령 제31조제2항). 게재 위치와 최종 게재일을 확인한다.")],
    "002": [("설계도서와의 면적 일치", "설계개요서의 대지면적·건축면적·층별 바닥면적이 배치도 및 각 층 평면도의 면적 산출표와 일치하는가.")],
    "003": [("작업환경측정 결과서 확인", "프레스 구역 소음 측정값(92 dB(A))이 2025년 작업환경측정 결과서 원본의 측정 지점·측정값과 일치하는가.")],
}

USE_CASES = [
    ("001", uc001_privacy, uc001_privacy._ITEMS, ["corporate-governance"]),
    ("002", uc002_building, uc002_building._RECHECK_ITEMS, ["real-estate"]),
    ("003", uc003_risk, uc003_risk._ITEMS, ["manufacturing"]),
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _page_count(path: Path) -> int | None:
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(path)).pages)
    except Exception:  # pragma: no cover - pypdf optional at generation time
        return None


def build_cases(with_image_variants: bool) -> tuple[list[dict], list[dict]]:
    cases: list[dict] = []
    manifest: list[dict] = []
    seen_files: set[Path] = set()

    for number, module, items, tags in USE_CASES:
        uc_dir = EXAMPLES_KO / module.USE_CASE_DIR
        review_pdf = uc_dir / module.REVIEW_FILENAME
        if not review_pdf.exists():
            raise SystemExit(f"review target not found: {review_pdf} (run create_korean_example_pdfs.py first)")
        fixtures_rel = Path("..") / ".." / ".." / ".." / "examples" / "ko" / module.USE_CASE_DIR  # relative to this file
        if review_pdf not in seen_files:
            seen_files.add(review_pdf)
            manifest.append({
                "use_case": number,
                "path": str(review_pdf.relative_to(REPO_ROOT)),
                "sha256": _sha256(review_pdf),
                "size_bytes": review_pdf.stat().st_size,
                "pages": _page_count(review_pdf),
            })

        by_number = {str(item[0]): item for item in items}
        defect_items = FAIL_ITEMS[number]
        pass_items = PASS_ITEMS[number]
        for item_no in list(defect_items) + pass_items:
            if item_no not in by_number:
                raise SystemExit(f"UC{number}: checklist item {item_no} not found in content module")
        for item_no in AMBIGUOUS[number]:
            assert item_no not in defect_items and item_no not in pass_items, f"UC{number} item {item_no} both ambiguous and used"

        def make_case(item_no: str, kind: str, expected: dict, extra_meta: dict | None = None,
                      document: str = module.REVIEW_FILENAME, fixtures: Path = fixtures_rel, variant: str = "pdf") -> dict:
            _, name, criteria, basis = by_number[item_no]
            meta = {"use_case": number, "item": item_no, "kind": kind, "basis": basis, "tags": tags, "variant": variant}
            if extra_meta:
                meta.update(extra_meta)
            return {
                "name": f"KO-UC{number}-{variant.upper()}-{kind}-item{item_no.zfill(2)}",
                "input": {
                    "document_paths": [document],
                    "fixtures_dir": str(fixtures),
                    "check_name": name,
                    "check_description": criteria,
                    "language_name": LANGUAGE_NAME,
                },
                "expected_output": expected,
                "metadata": meta,
            }

        for item_no, defect_idx in defect_items.items():
            defect_text = module.DEFECTS[defect_idx - 1]
            cases.append(make_case(item_no, "fail", {"result": "fail"}, {"defect": defect_idx, "defect_text": defect_text}))
        for item_no in pass_items:
            cases.append(make_case(item_no, "pass", {"result": "pass"}))

        for idx, (name, criteria) in enumerate(INSUFFICIENT_CASES[number], start=1):
            cases.append({
                "name": f"KO-UC{number}-PDF-insufficient-{idx}",
                "input": {
                    "document_paths": [module.REVIEW_FILENAME],
                    "fixtures_dir": str(fixtures_rel),
                    "check_name": name,
                    "check_description": criteria,
                    "language_name": LANGUAGE_NAME,
                },
                "expected_output": {"result": "fail", "insufficient_evidence": True},
                "metadata": {"use_case": number, "kind": "insufficient", "tags": tags, "variant": "pdf"},
            })

        if with_image_variants:
            image_dir = HERE / "fixtures" / "image" / module.USE_CASE_DIR
            image_pdf = image_dir / module.REVIEW_FILENAME
            if image_pdf.exists():
                image_rel = Path("fixtures") / "image" / module.USE_CASE_DIR
                for item_no, defect_idx in defect_items.items():
                    cases.append(make_case(item_no, "fail", {"result": "fail"},
                                           {"defect": defect_idx}, fixtures=image_rel, variant="image"))
                manifest.append({
                    "use_case": number, "path": str(image_pdf.relative_to(REPO_ROOT)),
                    "sha256": _sha256(image_pdf), "size_bytes": image_pdf.stat().st_size,
                    "pages": _page_count(image_pdf), "variant": "image",
                })
            else:
                print(f"  (no image variant for UC{number}: {image_pdf} missing, skipped)")

    return cases, manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--with-image-variants", action="store_true", help="add IMAGE cases when rasterised PDFs exist under fixtures/image/")
    ap.add_argument("--out", type=Path, default=HERE / "korean_examples_suite.json")
    args = ap.parse_args()

    cases, manifest = build_cases(args.with_image_variants)
    args.out.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = args.out.with_name("fixtures_manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    kinds = {}
    for c in cases:
        kinds[c["metadata"]["kind"]] = kinds.get(c["metadata"]["kind"], 0) + 1
    print(f"wrote {len(cases)} cases -> {args.out.relative_to(REPO_ROOT)}  {kinds}")
    print(f"wrote manifest ({len(manifest)} files) -> {manifest_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
