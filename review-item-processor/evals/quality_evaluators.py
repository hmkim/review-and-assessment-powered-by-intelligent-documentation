"""
Output-quality evaluators for the RAPID review agent.

These complement AccuracyEvaluator / ConfidenceCalibrationEvaluator with checks
that do not need ground truth about the *verdict* but about the *shape* of the
answer. They were written for the Korean evaluation set (evals/ko) but are
language-parameterised so the ja/en suites can use them as well.

- OutputLanguageEvaluator      : explanation / shortExplanation are written in the requested language
- ShortExplanationLengthEvaluator : shortExplanation respects the prompt's "max N chars" rule
- JsonParseEvaluator           : the agent's JSON answer was parsed (no fallback result)
- CitationFidelityEvaluator    : extractedText is a verbatim span of the source PDF, on the stated page
- InsufficientEvidenceEvaluator: cases whose evidence is absent follow the prompt's protocol
                                 (fail / confidence <= 0.49 / empty extractedText) and the phrase used

Reasons are pipe-separated key=value strings (like the existing evaluators) so
metrics.calculate_quality_metrics() can aggregate them from an EvaluationReport.
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from pathlib import Path
from typing import Any, Iterable

from strands_evals.evaluators import Evaluator
from strands_evals.types.evaluation import EvaluationData, EvaluationOutput

from .wrapper import ReviewAgentInput, ReviewAgentOutput

# Sentinel strings produced by agent.py when the model answer could not be parsed.
JSON_PARSE_FALLBACK_SHORT = "Failed to analyze JSON parse"
MISSING_EXPLANATION = "No explanation provided"
MISSING_SHORT_EXPLANATION = "No short explanation provided"

# Language codes accepted by OutputLanguageEvaluator and the language_name values the
# suites use for them (the agent receives the *name*, the evaluator needs the *code*).
LANGUAGE_NAME_TO_CODE = {
    "korean": "ko",
    "한국어": "ko",
    "japanese": "ja",
    "日本語": "ja",
    "english": "en",
}


def language_code_from_name(language_name: str | None, default: str = "en") -> str:
    if not language_name:
        return default
    return LANGUAGE_NAME_TO_CODE.get(language_name.strip().lower(), default)


# --------------------------------------------------------------------------- script counting
# Tokens that are legitimate in prose of any language and must not count as "foreign":
# URLs / e-mail addresses, and upper-case acronyms or codes (RTO, BCP, MSDS, ISO-27001, dB).
_NEUTRAL_TOKENS = re.compile(
    r"https?://\S+|www\.\S+|[\w.+-]+@[\w-]+\.[\w.]+"
    r"|(?<![A-Za-z])[A-Z][A-Z0-9]{0,7}(?:[/-][A-Z0-9]{1,8})*(?![a-z])"
)


def strip_neutral_tokens(text: str) -> str:
    return _NEUTRAL_TOKENS.sub(" ", text)


def _script_counts(text: str) -> dict[str, int]:
    """Count letters by script. Digits, punctuation, whitespace and neutral tokens are ignored."""
    counts = {"hangul": 0, "kana": 0, "cjk": 0, "latin": 0, "other": 0}
    for ch in strip_neutral_tokens(text):
        if not ch.isalpha():
            continue
        cp = ord(ch)
        if 0xAC00 <= cp <= 0xD7A3 or 0x1100 <= cp <= 0x11FF or 0x3130 <= cp <= 0x318F:
            counts["hangul"] += 1
        elif 0x3040 <= cp <= 0x30FF or 0x31F0 <= cp <= 0x31FF:
            counts["kana"] += 1
        elif 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or 0xF900 <= cp <= 0xFAFF:
            counts["cjk"] += 1
        elif cp < 0x0250:
            counts["latin"] += 1
        else:
            counts["other"] += 1
    return counts


def _target_ratio(counts: dict[str, int], language: str) -> tuple[float, int]:
    """Return (ratio of letters in the target script, number of letters counted)."""
    total = sum(counts.values())
    if total == 0:
        return 1.0, 0
    if language == "ko":
        target = counts["hangul"]
    elif language == "ja":
        target = counts["kana"] + counts["cjk"]
    else:  # en and anything else: Latin letters
        target = counts["latin"]
    return target / total, total


def _foreign_count(counts: dict[str, int], language: str) -> int:
    """Letters that must not appear at all in the given language's prose."""
    if language == "ko":
        return counts["kana"]
    if language == "ja":
        return counts["hangul"]
    return counts["hangul"] + counts["kana"]


class OutputLanguageEvaluator(Evaluator):
    """
    Checks that the prose fields are written in the requested output language.

    `explanation` and `shortExplanation` are checked; `extractedText` is a verbatim
    quote of the source document and is deliberately excluded. Proper nouns, units
    and code in Latin letters are allowed, which is why a ratio threshold is used
    instead of an all-or-nothing rule; letters of a *conflicting* script (kana in
    Korean output, Hangul in Japanese output) fail the case outright.
    """

    def __init__(self, language: str = "ko", min_ratio: float = 0.7):
        super().__init__()
        self.language = language
        self.min_ratio = min_ratio

    def evaluate(self, evaluation_case: EvaluationData) -> list[EvaluationOutput]:
        out: ReviewAgentOutput | None = evaluation_case.actual_output
        if out is None:
            return [EvaluationOutput(score=0.0, test_pass=False, reason="no_output", label="language")]

        fields = {"explanation": out.explanation or "", "short_explanation": out.short_explanation or ""}
        ratios: dict[str, float] = {}
        foreign = 0
        letters_total = 0
        for name, text in fields.items():
            counts = _script_counts(text)
            ratio, letters = _target_ratio(counts, self.language)
            ratios[name] = ratio
            foreign += _foreign_count(counts, self.language)
            letters_total += letters

        min_field_ratio = min(ratios.values()) if ratios else 0.0
        passed = letters_total > 0 and min_field_ratio >= self.min_ratio and foreign == 0
        reason = (
            f"language={self.language}|explanation_ratio={ratios['explanation']:.2f}"
            f"|short_ratio={ratios['short_explanation']:.2f}|foreign_letters={foreign}|letters={letters_total}"
        )
        return [EvaluationOutput(score=min_field_ratio if foreign == 0 else 0.0, test_pass=passed, reason=reason, label="language")]


class ShortExplanationLengthEvaluator(Evaluator):
    """The prompt asks for `shortExplanation` of at most N characters (default 80)."""

    def __init__(self, max_chars: int = 80):
        super().__init__()
        self.max_chars = max_chars

    def evaluate(self, evaluation_case: EvaluationData) -> list[EvaluationOutput]:
        out: ReviewAgentOutput | None = evaluation_case.actual_output
        text = (out.short_explanation if out else "") or ""
        length = len(text)
        within = 0 < length <= self.max_chars
        score = 1.0 if within else max(0.0, 1.0 - (length - self.max_chars) / self.max_chars) if length else 0.0
        return [EvaluationOutput(
            score=score,
            test_pass=within,
            reason=f"length={length}|max={self.max_chars}|empty={int(length == 0)}",
            label="short_explanation_length",
        )]


class JsonParseEvaluator(Evaluator):
    """Detects answers that fell back to the agent's 'could not parse JSON' defaults."""

    def evaluate(self, evaluation_case: EvaluationData) -> list[EvaluationOutput]:
        out: ReviewAgentOutput | None = evaluation_case.actual_output
        if out is None:
            return [EvaluationOutput(score=0.0, test_pass=False, reason="parsed=0|cause=no_output", label="json_parse")]
        cause = None
        if out.short_explanation == JSON_PARSE_FALLBACK_SHORT:
            cause = "fallback_short_explanation"
        elif out.explanation == MISSING_EXPLANATION or out.short_explanation == MISSING_SHORT_EXPLANATION:
            cause = "missing_field_defaults"
        elif out.result not in ("pass", "fail"):
            cause = f"result={out.result}"
        parsed = cause is None
        return [EvaluationOutput(
            score=1.0 if parsed else 0.0,
            test_pass=parsed,
            reason=f"parsed={int(parsed)}" + (f"|cause={cause}" if cause else ""),
            label="json_parse",
        )]


# --------------------------------------------------------------------------- citations
def normalize_for_match(text: str) -> str:
    """
    Form used to compare a citation with the PDF text layer: NFKC-normalised, letters
    and digits only. Whitespace *and* punctuation are dropped because Bedrock's citation
    `sourceContent` joins table cells with ", " where pypdf yields line breaks, and
    bullets / full-width punctuation differ between the two renderings. Hallucinated or
    paraphrased text still fails to match since the letters themselves differ.
    """
    text = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in text if unicodedata.category(ch)[0] in ("L", "N"))


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)]


class CitationFidelityEvaluator(Evaluator):
    """
    Verifies that each `extractedText` entry is a verbatim span of the source PDF.

    A citation counts as `page_match` when it is found (whitespace-insensitively) in
    the text layer of the page the agent named (`pageNumber`, 1-based), `other_page`
    when it exists elsewhere in the document, and `mismatch` when it is not in the
    document at all. Image reviews have no text layer and are reported as not
    applicable. PDF text is read with pypdf and cached per file.
    """

    def __init__(self, fixtures_dir: str | Path | None = None):
        super().__init__()
        self.fixtures_dir = Path(fixtures_dir) if fixtures_dir else None
        self._page_cache: dict[str, list[str]] = {}

    # -- helpers -------------------------------------------------------------
    def _resolve_documents(self, agent_input: ReviewAgentInput) -> list[Path]:
        base = Path(agent_input.fixtures_dir) if agent_input.fixtures_dir else self.fixtures_dir
        if base is not None and not base.is_absolute():
            base = Path(__file__).parent / base
        paths = []
        for doc in agent_input.document_paths:
            p = Path(doc)
            if not p.is_absolute() and base is not None:
                p = base / p
            paths.append(p)
        return paths

    def _pages(self, pdf_path: Path) -> list[str]:
        key = str(pdf_path)
        if key not in self._page_cache:
            try:
                from pypdf import PdfReader  # local import: optional dependency of the evals extra
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("pypdf is required for CitationFidelityEvaluator (uv sync --extra evals)") from exc
            reader = PdfReader(str(pdf_path))
            self._page_cache[key] = [normalize_for_match(page.extract_text() or "") for page in reader.pages]
        return self._page_cache[key]

    # -- evaluation ------------------------------------------------------------
    def evaluate(self, evaluation_case: EvaluationData) -> list[EvaluationOutput]:
        out: ReviewAgentOutput | None = evaluation_case.actual_output
        agent_input: ReviewAgentInput = evaluation_case.input
        if out is None:
            return [EvaluationOutput(score=0.0, test_pass=False, reason="applicable=0|cause=no_output", label="citation")]

        if (out.review_type or "").upper() == "IMAGE":
            return [EvaluationOutput(score=1.0, test_pass=True, reason="applicable=0|cause=image_review", label="citation")]

        citations = _as_list(out.extracted_text)
        expected = evaluation_case.expected_output or {}
        if not citations:
            insufficient = bool(isinstance(expected, dict) and expected.get("insufficient_evidence"))
            # Empty extractedText is the prescribed answer when evidence is absent.
            return [EvaluationOutput(
                score=1.0 if insufficient else 0.0,
                test_pass=insufficient,
                reason=f"applicable={int(not insufficient)}|citations=0|cause=" + ("insufficient_evidence" if insufficient else "no_citation"),
                label="citation",
            )]

        docs = [p for p in self._resolve_documents(agent_input) if p.suffix.lower() == ".pdf" and p.exists()]
        if not docs:
            return [EvaluationOutput(score=0.0, test_pass=False, reason="applicable=0|cause=pdf_not_found", label="citation")]

        all_pages: list[tuple[int, str]] = []  # (1-based page number across docs, normalised text)
        for doc in docs:
            all_pages.extend((i + 1, text) for i, text in enumerate(self._pages(doc)))
        stated_page = out.page_number if isinstance(out.page_number, int) else None

        page_match = other_page = mismatch = 0
        for citation in citations:
            needle = normalize_for_match(citation)
            if not needle:
                continue
            on_stated = stated_page is not None and any(num == stated_page and needle in text for num, text in all_pages)
            if on_stated:
                page_match += 1
            elif any(needle in text for _, text in all_pages):
                other_page += 1
            else:
                mismatch += 1

        n = page_match + other_page + mismatch
        score = (page_match + 0.5 * other_page) / n if n else 0.0
        passed = n > 0 and mismatch == 0
        reason = (
            f"applicable=1|citations={n}|page_match={page_match}|other_page={other_page}"
            f"|mismatch={mismatch}|page_number={stated_page}"
        )
        return [EvaluationOutput(score=score, test_pass=passed, reason=reason, label="citation")]


class InsufficientEvidenceEvaluator(Evaluator):
    """
    For cases marked `expected_output.insufficient_evidence: true`, checks the prompt's
    protocol: result "fail", confidence <= 0.49, empty extractedText. The phrase the
    model chose for "insufficient evidence" is recorded in the reason so the report
    can show how consistent it is across runs. Other cases are not applicable.
    """

    MAX_CONFIDENCE = 0.49

    def evaluate(self, evaluation_case: EvaluationData) -> list[EvaluationOutput]:
        expected = evaluation_case.expected_output or {}
        if not (isinstance(expected, dict) and expected.get("insufficient_evidence")):
            return [EvaluationOutput(score=1.0, test_pass=True, reason="applicable=0", label="insufficient_evidence")]
        out: ReviewAgentOutput | None = evaluation_case.actual_output
        if out is None:
            return [EvaluationOutput(score=0.0, test_pass=False, reason="applicable=1|cause=no_output", label="insufficient_evidence")]
        checks = {
            "result_fail": out.result == "fail",
            "low_confidence": (out.confidence or 0.0) <= self.MAX_CONFIDENCE,
            "empty_extracted": not _as_list(out.extracted_text),
        }
        score = sum(checks.values()) / len(checks)
        phrase = (out.short_explanation or "").replace("|", "/").replace("\n", " ")
        reason = (
            "applicable=1|" + "|".join(f"{k}={int(v)}" for k, v in checks.items())
            + f"|confidence={out.confidence:.2f}|phrase={phrase}"
        )
        return [EvaluationOutput(score=score, test_pass=all(checks.values()), reason=reason, label="insufficient_evidence")]


# --------------------------------------------------------------------------- aggregation helpers
def parse_reason(reason: str | None) -> dict[str, str]:
    """Turn 'k=v|k2=v2' into a dict (last '=' wins inside a value is not supported; phrase is last)."""
    result: dict[str, str] = {}
    if not reason:
        return result
    for part in reason.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            result[k] = v
    return result


def percentile(values: Iterable[float], pct: float) -> float | None:
    data = sorted(values)
    if not data:
        return None
    if len(data) == 1:
        return data[0]
    k = (len(data) - 1) * pct
    lo, hi = int(k), min(int(k) + 1, len(data) - 1)
    return data[lo] + (data[hi] - data[lo]) * (k - lo)


def median_or_none(values: Iterable[float]) -> float | None:
    data = list(values)
    return statistics.median(data) if data else None
