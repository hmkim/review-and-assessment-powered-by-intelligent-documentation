#!/usr/bin/env python3
"""
Generate corpus_suite.json: review cases over the harder Korean documents (corpus D2/D3/D5).

  D2  「사업장 위험성평가에 관한 지침」 고시 전문 PDF (law.go.kr attachment, 18 pages) whose text
      layer has lost most spaces ("이고시는「...」"). Measures whether citations still match the
      document and whether explanations stay readable Korean.
  D3  law.go.kr PDF renderings of the notice's HWP forms (별표·별지). The realistic input path
      for Korean public-sector documents; structural "does the form have X" checks.
  D5  Generated Korean/English mixed IT operations & DR plan (d5_mixed_document.py): RTO/RPO,
      SLO percentages, ≤/≥, ①②③, 「법령」, product names. Tokenisation and citation boundaries.

D2/D3 files are not committed (see external_sources.json; run fetch_external.sh). D5 is
generated into fixtures/d5/. The D4 scan variants of the example documents are produced by
../examples/generate_suite.py --with-image-variants, not here.

Ground truth for D2/D3 is written in this file next to each case; the D5 truth lives in
d5_mixed_document.ITEMS so document and cases cannot drift apart.

Usage (from review-item-processor/):
    uv run --extra evals python evals/ko/corpus/generate_corpus_suite.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent                 # evals/ko/corpus
REPO_ROOT = HERE.parent.parent.parent.parent
EXTERNAL = HERE / "external"
LANGUAGE_NAME = "Korean"

sys.path.insert(0, str(HERE))
import d5_mixed_document as d5  # noqa: E402

D2_FILE = "D2_위험성평가지침_고시_전문.pdf"
D2_SOURCE = "law.go.kr 고용노동부고시 제2024-76호 전문 (flSeq 146415417)"

# (kind, check_name, check_description, note) — note is the clause the truth rests on.
D2_CASES = [
    ("pass", "위험성평가 실시 시기 구분",
     "위험성평가의 실시 시기가 최초평가, 수시평가, 정기평가(또는 상시평가)로 구분되어 규정되어 있는가.",
     "제15조 (최초·수시·정기/상시)"),
    ("pass", "정기 재검토 주기",
     "실시한 위험성평가 결과의 적정성을 1년마다 정기적으로 재검토하도록 규정하고 있는가.",
     "제15조제3항 '1년마다 정기적으로 재검토'"),
    ("pass", "근로자 참여 조항",
     "위험성평가를 실시할 때 해당 작업에 종사하는 근로자를 참여시켜야 하는 경우가 규정되어 있는가.",
     "제6조(근로자 참여)"),
    ("fail", "인정 유효기간 5년 여부",
     "위험성평가 인정사업장의 인정 유효기간이 인정 결정일부터 5년으로 규정되어 있는가.",
     "제19조제4항은 3년 → fail"),
    ("fail", "벌칙 규정 포함 여부",
     "이 고시에 위반 시 과태료 등 벌칙(제재) 조항이 포함되어 있는가.",
     "고시에 벌칙·과태료 조항 없음 → fail"),
    ("insufficient", "최신 개정본 여부",
     "이 문서가 현재 시행 중인 「사업장 위험성평가에 관한 지침」의 최신 개정본인지, 이후 개정 고시가 있는지 확인한다.",
     "문서 밖 정보 필요 → 근거 부족"),
]

# D3: (form id, filename, [(kind, check_name, check_description, note), ...])
D3_FORMS = [
    ("byl0000", "D3_별표_인정심사_항목_및_기준.pdf", [
        ("pass", "영역별 가중치 명시",
         "종합점수 산정 기준에 심사 영역별 가중치(사업주의 관심도, 위험성평가 실행 수준, 구성원의 참여 및 이해 수준, 재해발생)가 백분율로 명시되어 있는가.",
         "2쪽 종합점수 산정 기준 10%/60%/25%/5%"),
        ("pass", "수시평가 미실시 감점",
         "감점 기준에 산업재해 발생 후 수시 위험성평가를 실시하지 않은 경우의 감점 점수가 규정되어 있는가.",
         "2쪽 감점 기준 △5점"),
        ("fail", "외부 전문기관 컨설팅 이력 항목",
         "심사항목에 외부 전문기관의 컨설팅 이수 이력에 대한 배점 항목이 포함되어 있는가.",
         "심사항목 표에 없음 → fail"),
    ]),
    ("byl0001", "D3_별지1_인정신청서.pdf", [
        ("pass", "위험성평가 담당자 기재란",
         "신청서에 위험성평가 담당자의 성명, 휴대전화번호, 전자우편 주소를 기재하는 란이 있는가.",
         "1쪽 신청인 란"),
        ("pass", "개인정보 보유·이용기간 명시",
         "개인정보 수집·이용 및 제3자 제공 동의서에 항목별 보유·이용기간이 명시되어 있는가.",
         "2쪽 동의서 '다음연도부터 3년', '1년'"),
        ("fail", "최근 3년 산업재해 건수 기재란",
         "신청서에 최근 3년간 산업재해 발생 건수를 기재하는 란이 있는가.",
         "해당 란 없음 → fail"),
    ]),
    ("byl0004", "D3_별지4_컨설팅지원신청서.pdf", [
        ("pass", "처리기간 명시",
         "신청서 상단에 접수 후 처리기간이 명시되어 있는가.",
         "'처리기간 1개월 10일'"),
        ("fail", "컨설팅 희망 분야 선택란",
         "신청서에 컨설팅을 희망하는 분야(공정·설비·작업 등)를 선택하거나 기재하는 란이 있는가.",
         "해당 란 없음 → fail"),
    ]),
    ("byl0003", "D3_별지3_교육신청서.pdf", [
        ("insufficient", "최신 서식 여부",
         "이 교육 신청서 양식이 한국산업안전보건공단 홈페이지에 게시된 현재 사용 중인 최신 양식과 동일한지 확인한다.",
         "문서 밖 정보 필요 → 근거 부족"),
    ]),
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
    except Exception:  # pragma: no cover
        return None


def _expected(kind: str) -> dict:
    if kind == "insufficient":
        return {"result": "fail", "insufficient_evidence": True}
    return {"result": kind}


def _case(name: str, document: str, fixtures_rel: str, check_name: str, description: str, meta: dict) -> dict:
    return {
        "name": name,
        "input": {
            "document_paths": [document],
            "fixtures_dir": fixtures_rel,
            "check_name": check_name,
            "check_description": description,
            "language_name": LANGUAGE_NAME,
        },
        "expected_output": _expected(meta["kind"]),
        "metadata": meta,
    }


def build_cases() -> tuple[list[dict], list[dict], list[str]]:
    cases: list[dict] = []
    manifest: list[dict] = []
    missing: list[str] = []

    def record(path: Path, corpus: str) -> None:
        if path.exists():
            manifest.append({"corpus": corpus, "path": str(path.relative_to(REPO_ROOT)), "sha256": _sha256(path),
                             "size_bytes": path.stat().st_size, "pages": _page_count(path)})
        else:
            missing.append(str(path.relative_to(REPO_ROOT)))

    # D2
    record(EXTERNAL / D2_FILE, "D2")
    counters: dict[str, int] = {}
    for kind, name, desc, note in D2_CASES:
        counters[kind] = counters.get(kind, 0) + 1
        meta = {"corpus": "D2", "kind": kind, "tags": ["manufacturing", "law-text"], "variant": "pdf",
                "source": D2_SOURCE, "truth_note": note}
        cases.append(_case(f"KO-D2-PDF-{kind}-{counters[kind]:02d}", D2_FILE, "external", name, desc, meta))

    # D3
    for form_id, filename, items in D3_FORMS:
        record(EXTERNAL / filename, "D3")
        counters = {}
        for kind, name, desc, note in items:
            counters[kind] = counters.get(kind, 0) + 1
            meta = {"corpus": "D3", "kind": kind, "tags": ["manufacturing", "public-form"], "variant": "pdf",
                    "form": form_id, "source": "law.go.kr 별지/별표 PDF (HWP 서식 변환본)", "truth_note": note}
            cases.append(_case(f"KO-D3-{form_id}-{kind}-{counters[kind]:02d}", filename, "external", name, desc, meta))

    # D5
    d5_path = d5.OUT_DIR / d5.FILENAME
    record(d5_path, "D5")
    for item_no, name, desc, kind, defect in d5.ITEMS:
        meta = {"corpus": "D5", "kind": kind, "tags": d5.TAGS, "variant": "pdf", "item": item_no}
        if defect:
            meta["defect"] = defect
            meta["defect_text"] = d5.DEFECTS[defect - 1]
        cases.append(_case(f"KO-D5-PDF-{kind}-item{item_no.zfill(2)}", d5.FILENAME, "fixtures/d5", name, desc, meta))
    for idx, (name, desc) in enumerate(d5.INSUFFICIENT, start=1):
        meta = {"corpus": "D5", "kind": "insufficient", "tags": d5.TAGS, "variant": "pdf"}
        cases.append(_case(f"KO-D5-PDF-insufficient-{idx}", d5.FILENAME, "fixtures/d5", name, desc, meta))

    return cases, manifest, missing


def main() -> None:
    cases, manifest, missing = build_cases()
    out = HERE / "corpus_suite.json"
    out.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (HERE / "corpus_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    by_corpus: dict[str, dict[str, int]] = {}
    for c in cases:
        m = c["metadata"]
        by_corpus.setdefault(m["corpus"], {}).setdefault(m["kind"], 0)
        by_corpus[m["corpus"]][m["kind"]] += 1
    print(f"wrote {len(cases)} cases -> {out.relative_to(REPO_ROOT)}  {by_corpus}")
    print(f"manifest: {len(manifest)} files present")
    if missing:
        print("missing fixtures (cases still generated; run fetch_external.sh / d5_mixed_document.py):")
        for m in missing:
            print(f"  - {m}")


if __name__ == "__main__":
    main()
