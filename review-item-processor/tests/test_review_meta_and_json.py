#!/usr/bin/env python3
"""Offline tests for ReviewMetaTracker token accounting and lenient JSON parsing in agent.py."""
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent
from agent import (
    CACHE_READ_PRICE_MULTIPLIER,
    CACHE_WRITE_PRICE_MULTIPLIER,
    ReviewMetaTracker,
    _extract_json_from_message,
    _repair_unescaped_quotes,
)

MODEL_ID = "global.anthropic.claude-sonnet-5-5"


def _result_with_usage(**usage):
    return SimpleNamespace(metrics=SimpleNamespace(accumulated_usage=usage))


# ---------------------------------------------------------------------------
# ReviewMetaTracker: prompt-cache tokens are part of the input count and cost
# ---------------------------------------------------------------------------


def test_review_meta_counts_cache_tokens_as_input():
    """With auto prompt caching the document lands in cacheRead/Write; those must be billed."""
    tracker = ReviewMetaTracker(MODEL_ID)
    meta = tracker.get_review_meta(
        _result_with_usage(inputTokens=4, outputTokens=900, totalTokens=904,
                           cacheReadInputTokens=11_000, cacheWriteInputTokens=1_000)
    )
    assert meta["input_tokens"] == 12_004
    assert meta["uncached_input_tokens"] == 4
    assert meta["cache_read_input_tokens"] == 11_000
    assert meta["cache_write_input_tokens"] == 1_000
    price_in = tracker.model.input_per_1k
    expected_input_cost = (
        4 * price_in + 11_000 * price_in * CACHE_READ_PRICE_MULTIPLIER + 1_000 * price_in * CACHE_WRITE_PRICE_MULTIPLIER
    ) / 1000
    assert meta["input_cost"] == pytest.approx(expected_input_cost)
    assert meta["total_cost"] == pytest.approx(expected_input_cost + 900 / 1000 * tracker.model.output_per_1k)


def test_review_meta_without_cache_fields_is_unchanged():
    """Models/paths without caching report plain inputTokens; cache fields default to 0."""
    tracker = ReviewMetaTracker(MODEL_ID)
    meta = tracker.get_review_meta(_result_with_usage(inputTokens=5_000, outputTokens=500, totalTokens=5_500))
    assert meta["input_tokens"] == 5_000
    assert meta["cache_read_input_tokens"] == 0
    assert meta["cache_write_input_tokens"] == 0
    assert meta["input_cost"] == pytest.approx(5_000 / 1000 * tracker.model.input_per_1k)


# ---------------------------------------------------------------------------
# JSON repair: unescaped quotes inside string values (Korean direct quotation)
# ---------------------------------------------------------------------------

BROKEN_PAYLOAD = (
    "<<JSON_START>>\n"
    "{\n"
    '  "result": "fail",\n'
    '  "confidence": 0.93,\n'
    '  "explanation": "제1조 ④항에서 "다음의 개인정보는 관계 법령에 따라 아래 기간 동안 보존합니다."라고 안내하고, '
    '보존 항목을 표로 제시하고 있습니다. 그러나 파기 절차와 파기 방법이 빠져 있습니다.",\n'
    '  "shortExplanation": "파기 절차·방법 항목 누락(법령상 보존 항목만 기재)",\n'
    '  "extractedText": "④ 다음의 개인정보는 관계 법령에 따라 아래 기간 동안 보존합니다.",\n'
    '  "pageNumber": 2\n'
    "}\n"
    "<<JSON_END>>"
)


def test_repair_unescaped_quotes_recovers_korean_quotation():
    body = BROKEN_PAYLOAD.split("<<JSON_START>>")[1].split("<<JSON_END>>")[0]
    with pytest.raises(json.JSONDecodeError):
        json.loads(body)
    repaired = _repair_unescaped_quotes(body)
    assert repaired is not None
    assert repaired["result"] == "fail"
    assert repaired["confidence"] == 0.93
    assert '"다음의 개인정보는' in repaired["explanation"]
    assert repaired["pageNumber"] == 2


def test_extract_json_from_message_uses_repair():
    message = {"role": "assistant", "content": [{"text": BROKEN_PAYLOAD}]}
    parsed, _ = _extract_json_from_message(message)
    assert parsed is not None
    assert parsed["shortExplanation"] == "파기 절차·방법 항목 누락(법령상 보존 항목만 기재)"


def test_repair_leaves_valid_json_untouched():
    valid = '{"result": "pass", "explanation": "이미 \\"이스케이프된\\" 인용", "pageNumber": 1}'
    assert _repair_unescaped_quotes(valid) == json.loads(valid)


def test_repair_returns_none_when_still_broken():
    assert _repair_unescaped_quotes('{"result": "pass", "explanation": ') is None
