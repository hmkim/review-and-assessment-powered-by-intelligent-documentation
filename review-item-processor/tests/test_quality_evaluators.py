#!/usr/bin/env python3
"""Offline tests for the output-quality evaluators (evals/quality_evaluators.py).

No Bedrock calls: ReviewAgentOutput objects are built by hand and the citation
tests render a two-page Korean PDF with reportlab (same font setup as the
examples/ko generator is not needed — a CID font is enough for the text layer).
Run: uv run --extra evals --extra dev pytest tests/test_quality_evaluators.py
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("strands_evals", reason="evals extra not installed (uv sync --extra evals)")

from strands_evals.types.evaluation import EvaluationData  # noqa: E402

from evals.metrics import calculate_quality_metrics  # noqa: E402
from evals.quality_evaluators import (  # noqa: E402
    CitationFidelityEvaluator,
    InsufficientEvidenceEvaluator,
    JsonParseEvaluator,
    OutputLanguageEvaluator,
    ShortExplanationLengthEvaluator,
    language_code_from_name,
    normalize_for_match,
    parse_reason,
)
from evals.wrapper import ReviewAgentInput, ReviewAgentOutput, load_test_suite_from_json  # noqa: E402


def _output(**kw) -> ReviewAgentOutput:
    base = dict(result="fail", confidence=0.9, explanation="제9조에 연락처가 없습니다.",
                short_explanation="연락처 누락", tool_usage=[], review_meta={},
                extracted_text=None, page_number=None, review_type="PDF")
    base.update(kw)
    return ReviewAgentOutput(**base)


def _case(output: ReviewAgentOutput | None, expected=None, agent_input: ReviewAgentInput | None = None) -> EvaluationData:
    agent_input = agent_input or ReviewAgentInput(document_paths=["doc.pdf"], check_name="n", check_description="d", language_name="Korean")
    return EvaluationData(input=agent_input, actual_output=output, expected_output=expected or {"result": "fail"}, name="t")


# --------------------------------------------------------------------------- language
def test_language_korean_prose_passes():
    out = OutputLanguageEvaluator("ko").evaluate(_case(_output()))[0]
    assert out.test_pass and out.score == 1.0


def test_language_latin_terms_within_ratio_pass():
    o = _output(explanation="RTO/RPO 목표는 문서 3쪽의 BCP 절에 기재되어 있습니다.", short_explanation="BCP 절에 기재됨")
    assert OutputLanguageEvaluator("ko").evaluate(_case(o))[0].test_pass


def test_language_japanese_leak_fails_korean():
    o = _output(explanation="문서には連絡先が記載されていません。")
    res = OutputLanguageEvaluator("ko").evaluate(_case(o))[0]
    assert not res.test_pass
    assert parse_reason(res.reason)["foreign_letters"] != "0"


def test_language_english_output_fails_korean():
    o = _output(explanation="The contact information is missing.", short_explanation="Contact missing")
    assert not OutputLanguageEvaluator("ko").evaluate(_case(o))[0].test_pass


def test_language_japanese_mode_accepts_kanji_kana():
    o = _output(explanation="連絡先が記載されていません。", short_explanation="連絡先なし")
    assert OutputLanguageEvaluator("ja").evaluate(_case(o))[0].test_pass


def test_language_code_from_name():
    assert language_code_from_name("Korean") == "ko"
    assert language_code_from_name("日本語") == "ja"
    assert language_code_from_name("English") == "en"
    assert language_code_from_name(None) == "en"


# --------------------------------------------------------------------------- length / parse
def test_short_explanation_length_limit():
    ok = ShortExplanationLengthEvaluator(80).evaluate(_case(_output(short_explanation="가" * 80)))[0]
    over = ShortExplanationLengthEvaluator(80).evaluate(_case(_output(short_explanation="가" * 100)))[0]
    assert ok.test_pass and parse_reason(ok.reason)["length"] == "80"
    assert not over.test_pass and 0.0 <= over.score < 1.0


def test_json_parse_detects_fallbacks():
    assert JsonParseEvaluator().evaluate(_case(_output()))[0].test_pass
    bad = JsonParseEvaluator().evaluate(_case(_output(short_explanation="Failed to analyze JSON parse")))[0]
    assert not bad.test_pass and "fallback" in bad.reason


# --------------------------------------------------------------------------- citations
@pytest.fixture(scope="module")
def korean_pdf(tmp_path_factory) -> Path:
    reportlab = pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
    path = tmp_path_factory.mktemp("fx") / "doc.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("HYSMyeongJo-Medium", 11)
    c.drawString(60, 780, "제9조 개인정보 보호책임자 성명: 김가온 / 직위: 경영지원본부장")
    c.showPage()
    c.setFont("HYSMyeongJo-Medium", 11)
    c.drawString(60, 780, "회사는 쿠키를 사용합니다.")
    c.showPage()
    c.save()
    return path


def _pdf_input(pdf: Path) -> ReviewAgentInput:
    return ReviewAgentInput(document_paths=[pdf.name], check_name="n", check_description="d",
                            language_name="Korean", fixtures_dir=str(pdf.parent))


def test_citation_on_stated_page_matches(korean_pdf):
    pytest.importorskip("pypdf")
    o = _output(extracted_text=["개인정보 보호책임자 성명: 김가온 / 직위:경영지원본부장"], page_number=1)  # spacing differs on purpose
    res = CitationFidelityEvaluator().evaluate(_case(o, agent_input=_pdf_input(korean_pdf)))[0]
    r = parse_reason(res.reason)
    assert res.test_pass and r["page_match"] == "1" and r["mismatch"] == "0"


def test_citation_on_other_page_and_mismatch(korean_pdf):
    pytest.importorskip("pypdf")
    o = _output(extracted_text=["회사는 쿠키를 사용합니다.", "이 문장은 문서에 없습니다."], page_number=1)
    res = CitationFidelityEvaluator().evaluate(_case(o, agent_input=_pdf_input(korean_pdf)))[0]
    r = parse_reason(res.reason)
    assert not res.test_pass and r["other_page"] == "1" and r["mismatch"] == "1"


def test_citation_empty_is_only_ok_for_insufficient_cases(korean_pdf):
    o = _output(extracted_text=[], confidence=0.4)
    plain = CitationFidelityEvaluator().evaluate(_case(o, agent_input=_pdf_input(korean_pdf)))[0]
    insufficient = CitationFidelityEvaluator().evaluate(
        _case(o, expected={"result": "fail", "insufficient_evidence": True}, agent_input=_pdf_input(korean_pdf)))[0]
    assert not plain.test_pass and "no_citation" in plain.reason
    assert insufficient.test_pass


def test_citation_not_applicable_for_image_reviews(korean_pdf):
    o = _output(review_type="IMAGE", extracted_text=None)
    res = CitationFidelityEvaluator().evaluate(_case(o, agent_input=_pdf_input(korean_pdf)))[0]
    assert res.test_pass and parse_reason(res.reason)["applicable"] == "0"


def test_normalize_for_match_ignores_whitespace_and_width():
    assert normalize_for_match("ＡＢＣ 가, 나\r\n다 / 라: 1") == "ABC가나다라1"


# --------------------------------------------------------------------------- insufficient evidence
def test_insufficient_evidence_protocol():
    ev = InsufficientEvidenceEvaluator()
    expected = {"result": "fail", "insufficient_evidence": True}
    good = ev.evaluate(_case(_output(confidence=0.4, extracted_text="", short_explanation="근거 불충분"), expected))[0]
    bad = ev.evaluate(_case(_output(confidence=0.9, extracted_text=["x"]), expected))[0]
    skip = ev.evaluate(_case(_output()))[0]
    assert good.test_pass and parse_reason(good.reason)["phrase"] == "근거 불충분"
    assert not bad.test_pass and bad.score == pytest.approx(1 / 3)
    assert skip.test_pass and parse_reason(skip.reason)["applicable"] == "0"


# --------------------------------------------------------------------------- aggregation
class _Report:
    def __init__(self, reasons, passes, scores=None):
        self.reasons, self.test_passes = reasons, passes
        self.scores = scores or [1.0] * len(reasons)


def test_calculate_quality_metrics_aggregates_reasons():
    reports = {
        "OutputLanguageEvaluator": _Report(
            ["language=ko|explanation_ratio=0.95|short_ratio=1.00|foreign_letters=0|letters=40",
             "language=ko|explanation_ratio=0.50|short_ratio=0.90|foreign_letters=3|letters=30"], [True, False]),
        "ShortExplanationLengthEvaluator": _Report(["length=40|max=80|empty=0", "length=95|max=80|empty=0"], [True, False]),
        "JsonParseEvaluator": _Report(["parsed=1", "parsed=0|cause=fallback_short_explanation"], [True, False]),
        "CitationFidelityEvaluator": _Report(
            ["applicable=1|citations=2|page_match=2|other_page=0|mismatch=0|page_number=3",
             "applicable=1|citations=0|cause=no_citation"], [True, False]),
        "InsufficientEvidenceEvaluator": _Report(
            ["applicable=0", "applicable=1|result_fail=1|low_confidence=1|empty_extracted=1|confidence=0.40|phrase=근거 불충분"], [True, True]),
    }
    m = calculate_quality_metrics(reports)
    assert m["language"]["compliance_rate"] == 0.5 and m["language"]["foreign_letter_cases"] == 1
    assert m["short_explanation"]["over_limit_count"] == 1 and m["short_explanation"]["max_chars"] == 95
    assert m["json_parse"]["parse_rate"] == 0.5 and m["json_parse"]["failed_cases"] == ["fallback_short_explanation"]
    assert m["citation"]["page_match_rate"] == 1.0 and m["citation"]["no_citation_cases"] == 1
    assert m["insufficient_evidence"]["phrases"] == {"근거 불충분": 1}


# --------------------------------------------------------------------------- suite loading
def test_suite_loader_honours_per_case_fixtures_dir(tmp_path):
    (tmp_path / "docs").mkdir()
    suite = tmp_path / "suite.json"
    suite.write_text(json.dumps([{
        "name": "c1",
        "input": {"document_paths": ["a.pdf"], "fixtures_dir": "docs", "check_name": "n", "check_description": "d", "language_name": "Korean"},
        "expected_output": {"result": "pass"},
        "metadata": {"kind": "pass"},
    }]), encoding="utf-8")
    cases = load_test_suite_from_json(suite, fixtures_dir=tmp_path / "elsewhere")
    assert cases[0].input.fixtures_dir == str((tmp_path / "docs").resolve())
    assert cases[0].metadata == {"kind": "pass"}


def test_generated_korean_suite_is_consistent():
    suite = Path(__file__).resolve().parent.parent / "evals" / "ko" / "examples" / "korean_examples_suite.json"
    if not suite.exists():
        pytest.skip("korean suite not generated")
    cases = json.loads(suite.read_text(encoding="utf-8"))
    names = [c["name"] for c in cases]
    assert len(names) == len(set(names))
    kinds = {c["metadata"]["kind"] for c in cases}
    assert kinds == {"fail", "pass", "insufficient"}
    for c in cases:
        assert c["input"]["language_name"] == "Korean"
        if c["metadata"]["kind"] == "insufficient":
            assert c["expected_output"] == {"result": "fail", "insufficient_evidence": True}
        else:
            assert c["expected_output"]["result"] == c["metadata"]["kind"]
