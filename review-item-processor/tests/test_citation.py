#!/usr/bin/env python3
"""Citation tests for agent.py.

Offline tests cover _should_use_document_block (routing) and
_extract_citations_text (parsing). An opt-in Bedrock integration test runs only
with RUN_BEDROCK_INTEGRATION=1 (needs AWS credentials).
"""
import os
import sys
from pathlib import Path

import pytest

# Add parent directory to path so `import agent` works when run from any cwd.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent
from agent import _extract_citations_text, _should_use_document_block
from model_config import ModelConfig

# A registered model that supports the document block + citations.
CITATION_MODEL_ID = "global.anthropic.claude-sonnet-4-6"
# An unregistered model falls back to _DEFAULT_CONFIG (no document block).
UNKNOWN_MODEL_ID = "example.unknown-model-v1"


# ---------------------------------------------------------------------------
# _should_use_document_block: citation routing
# ---------------------------------------------------------------------------


def test_document_block_used_for_pdf_when_citations_enabled(monkeypatch):
    """PDF + citations enabled + capable model -> document block path."""
    monkeypatch.setattr(agent, "ENABLE_CITATIONS", True)
    assert (
        _should_use_document_block(["/tmp/a.pdf"], CITATION_MODEL_ID, has_images=False)
        is True
    )


def test_file_read_used_when_citations_disabled(monkeypatch):
    """ENABLE_CITATIONS=false falls back to the file_read tool path."""
    monkeypatch.setattr(agent, "ENABLE_CITATIONS", False)
    assert (
        _should_use_document_block(["/tmp/a.pdf"], CITATION_MODEL_ID, has_images=False)
        is False
    )


def test_file_read_used_for_images(monkeypatch):
    """Images always use the file_read/image_reader path, regardless of the flag."""
    monkeypatch.setattr(agent, "ENABLE_CITATIONS", True)
    assert (
        _should_use_document_block(["/tmp/a.png"], CITATION_MODEL_ID, has_images=True)
        is False
    )


def test_file_read_used_for_unknown_model(monkeypatch):
    """Unknown models fall back to defaults without document block support."""
    monkeypatch.setattr(agent, "ENABLE_CITATIONS", True)
    assert (
        _should_use_document_block(["/tmp/a.pdf"], UNKNOWN_MODEL_ID, has_images=False)
        is False
    )


def test_default_model_supports_citation():
    """The default model supports the document block and citations."""
    config = ModelConfig.create(CITATION_MODEL_ID)
    assert config.supports_document_block is True
    assert config.supports_citation is True


# ---------------------------------------------------------------------------
# _extract_citations_text: citations parsing from the JSON response
# ---------------------------------------------------------------------------


def _message_with_text(text: str) -> dict:
    """Build an AgentResult.message-shaped dict with a single text block."""
    return {"content": [{"text": text}]}


def test_extract_citations_returns_array():
    """A citations array in the marker JSON is returned as-is."""
    message = _message_with_text(
        '<<JSON_START>>{"result": "pass",'
        ' "citations": ["p.3 保管スペース", "p.5 避難経路"]}<<JSON_END>>'
    )
    assert _extract_citations_text(message) == ["p.3 保管スペース", "p.5 避難経路"]


def test_extract_citations_empty_when_absent():
    """JSON without a citations field yields an empty list."""
    message = _message_with_text('<<JSON_START>>{"result": "pass"}<<JSON_END>>')
    assert _extract_citations_text(message) == []


def test_extract_citations_empty_on_non_json():
    """Non-JSON output yields an empty list instead of raising."""
    assert _extract_citations_text(_message_with_text("no json here")) == []


# ---------------------------------------------------------------------------
# citationsContent blocks (Converse Citations API, non-streaming)
# ---------------------------------------------------------------------------


def _citation_block(generated: str, *sources: str) -> dict:
    """A citationsContent block as returned by Converse: generated text + cited spans."""
    return {
        "citationsContent": {
            "content": [{"text": generated}],
            "citations": [
                {
                    "title": "policy",
                    "sourceContent": [{"text": src}],
                    "location": {"documentPage": {"documentIndex": 0, "start": 3, "end": 4}},
                }
                for src in sources
            ],
        }
    }


def _split_message() -> dict:
    """The model's JSON answer split across text and citationsContent blocks."""
    return {
        "content": [
            {"text": '<<JSON_START>>{"result": "fail", "explanation": "제9조에는 '},
            _citation_block(
                "성명: 김가온 / 직위: 경영지원본부장",
                "개인정보 보호책임자 성명: 김가온 / 직위: 경영지원본부장",
            ),
            {"text": '으로 기재되어 있으나 연락처가 없다.", "extractedText": "제9조 표", '},
            {"text": '"pageNumber": 3}<<JSON_END>>'},
        ]
    }


def test_json_is_reassembled_across_citation_blocks():
    """Cited sentences inside citationsContent must stay in the explanation text."""
    parsed, combined = agent._extract_json_from_message(_split_message())
    assert parsed is not None
    assert parsed["explanation"] == (
        "제9조에는 성명: 김가온 / 직위: 경영지원본부장으로 기재되어 있으나 연락처가 없다."
    )
    assert "<<JSON_END>>" in combined


def test_extracted_text_comes_from_citation_sources():
    """extractedText is the verbatim cited source span(s), deduplicated, in order."""
    message = _split_message()
    # a second block citing the same span and one new span
    message["content"].insert(
        3,
        _citation_block(
            "쿠키 안내",
            "개인정보 보호책임자 성명: 김가온 / 직위: 경영지원본부장",
            "회사는 쿠키를 사용합니다.",
        ),
    )
    assert _extract_citations_text(message) == [
        "개인정보 보호책임자 성명: 김가온 / 직위: 경영지원본부장",
        "회사는 쿠키를 사용합니다.",
    ]


def test_extracted_text_falls_back_to_json_field_without_citation_blocks():
    """Without citation blocks the model's own extractedText string is kept."""
    message = _message_with_text(
        '<<JSON_START>>{"result": "fail", "extractedText": "제9조 표"}<<JSON_END>>'
    )
    assert _extract_citations_text(message) == ["제9조 표"]


def test_claude_5_models_omit_temperature():
    """Claude 5.x rejects `temperature`; the registry flags it so the agent omits it."""
    assert ModelConfig.create("global.anthropic.claude-sonnet-5-5").supports_temperature is False
    assert ModelConfig.create("us.anthropic.claude-sonnet-5-5").supports_temperature is False
    assert ModelConfig.create(CITATION_MODEL_ID).supports_temperature is True
    assert ModelConfig.create(agent.DEFAULT_DOCUMENT_MODEL_ID).supports_citation is True


# ---------------------------------------------------------------------------
# Opt-in Bedrock integration test (real API call, requires AWS credentials)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("RUN_BEDROCK_INTEGRATION") != "1",
    reason="Set RUN_BEDROCK_INTEGRATION=1 to run the live Bedrock integration test",
)
def test_citation_review_integration():
    """Run a real review over the bundled sample PDF via the citations path."""
    test_pdf = Path(__file__).parent / "office_planning.pdf"
    assert test_pdf.exists(), f"Test file not found: {test_pdf}"

    from agent import process_review_from_local

    result = process_review_from_local(
        document_paths=[str(test_pdf)],
        check_name="保管スペース確保",
        check_description="指定エリア内に整理保管され、避難経路を塞いでいない",
        language_name="日本語",
    )

    assert result.get("result") in ["pass", "fail"]
    assert 0 <= result.get("confidence", 0) <= 1
    assert result.get("explanation", "") != ""
    assert result.get("reviewType") == "PDF"


if __name__ == "__main__":
    os.environ["RUN_BEDROCK_INTEGRATION"] = "1"
    test_citation_review_integration()
    print("Integration test passed")
