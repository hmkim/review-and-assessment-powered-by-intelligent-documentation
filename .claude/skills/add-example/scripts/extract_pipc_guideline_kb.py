#!/usr/bin/env python3
"""
Extract Knowledge Base text files for the Korean example
`examples/ko/use_case_001_privacy_policy_review` from the PIPC guideline PDF.

Source document (not included in this repository, ~11 MB):
  개인정보보호위원회, 「개인정보 처리방침 작성지침」 (2026.4. 개정), 185 pages
  https://www.pipc.go.kr  >  정책·법령  >  안내서·지침 (게시물 번호 12018)

Why text excerpts instead of the PDF itself:
  * The guideline is a work of the Korean government (Copyright Act art. 24-2)
    whose colophon asks for attribution when quoting; each generated file
    therefore starts with a source notice.
  * RAPID sends review/checklist documents to Amazon Bedrock page by page with a
    4.5 MB per-file limit, so the full 185-page PDF is not a practical input.
  * Only Part II (basic rules) and Part III (how to write each item) are needed
    to ground review results such as "작성지침 Ⅲ-5에 따르면 ...".

Usage:
  cd .claude/skills/add-example
  uv run --with pypdf python scripts/extract_pipc_guideline_kb.py <guideline.pdf> [output_dir]

The default output_dir is examples/ko/use_case_001_privacy_policy_review/knowledge_base_sources.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    print("pypdf is required: uv run --with pypdf python scripts/extract_pipc_guideline_kb.py ...")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent.parent
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "examples/ko/use_case_001_privacy_policy_review/knowledge_base_sources"
)

SOURCE_TITLE = "개인정보보호위원회, 「개인정보 처리방침 작성지침」 (2026.4. 개정)"
SOURCE_URL = "https://www.pipc.go.kr (정책·법령 > 안내서·지침, 게시물 번호 12018)"

# Printed page number = PDF page index - 1 (PDF p10 is printed p8).
PRINT_OFFSET = 2

# (file name, first printed page, last printed page, description of the range)
SECTIONS = [
    (
        "KB_02_작성지침_PartII_작성기본사항.txt",
        12,
        18,
        "Part Ⅱ. 개인정보 처리방침 작성 기본사항 (1 기본 원칙, 2 기재 사항, 3 구성, 4 공개)",
    ),
    (
        "KB_03_작성지침_PartIII_01-08_처리목적_항목_보유기간_파기_제3자제공.txt",
        20,
        41,
        "Part Ⅲ. 작성 방법 1~8 (제목 및 서문, 처리 목적, 처리 항목, 14세 미만 아동, "
        "처리 및 보유 기간, 파기 절차 및 방법, 제3자 제공, 추가적인 이용·제공 판단 기준)",
    ),
    (
        "KB_04_작성지침_PartIII_09-15_위탁_국외이전_안전성확보_자동수집장치.txt",
        42,
        64,
        "Part Ⅲ. 작성 방법 9~15 (위탁, 국외 수집·이전, 안전성 확보조치, 민감정보 공개 가능성, "
        "가명정보, 자동 수집 장치, 제3자 행태정보 수집)",
    ),
    (
        "KB_05_작성지침_PartIII_16-24_권리행사_보호책임자_구제방법_변경.txt",
        65,
        85,
        "Part Ⅲ. 작성 방법 16~24 (정보주체 권리·의무 및 행사방법, 자동화된 결정, 보호책임자, "
        "국내대리인, 권익침해 구제방법, 영상정보처리기기, 자율적 사항, 처리방침 변경)",
    ),
]

HEADER_PATTERNS = [
    re.compile(r"^\s*\d+\s+개인정보 처리방침 작성지침\s*$"),  # even-page running head
    re.compile(r"^\s*Part\s+[ⅡⅢ]\.\s.*\d+\s*$"),  # odd-page running head
]
PUA_CHARS = re.compile(r"[\ue000-\uf8ff]")  # bullet glyphs mapped into the Private Use Area


def clean_page(text: str) -> str:
    lines = []
    for raw in text.splitlines():
        if any(p.match(raw) for p in HEADER_PATTERNS):
            continue
        line = PUA_CHARS.sub("•", raw).rstrip()
        lines.append(line)
    # collapse runs of blank lines
    out: list[str] = []
    for line in lines:
        if not line.strip() and out and not out[-1].strip():
            continue
        out.append(line)
    return "\n".join(out).strip()


def notice(range_desc: str, first: int, last: int) -> str:
    return (
        f"※ 출처: {SOURCE_TITLE}\n"
        f"   발췌 범위: {range_desc}, 인쇄면 {first}~{last}쪽\n"
        f"   원문: {SOURCE_URL}\n"
        "   본 파일은 RAPID 예제의 Knowledge Base 데이터 소스로 쓰기 위해 원문 PDF에서 본문 텍스트만\n"
        "   발췌한 것입니다. 표·그림의 배치와 줄바꿈은 원문과 다를 수 있으므로 정확한 내용은 원문을\n"
        "   확인하시기 바랍니다. 가공·인용 시 출처를 밝혀 주시기 바랍니다.\n"
        "   [p.N] 표시는 원문의 인쇄면 쪽수입니다.\n"
    )


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    pdf_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(str(pdf_path))
    if len(reader.pages) != 185:
        print(f"warning: expected the 185-page 2026.4 guideline, got {len(reader.pages)} pages")

    for filename, first, last, desc in SECTIONS:
        chunks = [notice(desc, first, last)]
        for printed in range(first, last + 1):
            page = reader.pages[printed + PRINT_OFFSET - 1]
            body = clean_page(page.extract_text() or "")
            if body:
                chunks.append(f"\n[p.{printed}]\n{body}")
        text = "\n".join(chunks).rstrip() + "\n"
        target = out_dir / filename
        target.write_text(text, encoding="utf-8")
        print(f"wrote {target.relative_to(PROJECT_ROOT) if target.is_relative_to(PROJECT_ROOT) else target}"
              f"  ({len(text):,} chars, p.{first}-{last})")


if __name__ == "__main__":
    main()
