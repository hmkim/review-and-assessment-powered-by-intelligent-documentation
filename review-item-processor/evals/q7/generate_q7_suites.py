#!/usr/bin/env python3
"""
Q7 (insufficient-evidence protocol) suites for Japanese and English.

The Korean evaluation (evals/ko) labelled checks whose answer is NOT in the document
(`expected_output.insufficient_evidence: true`) and measured how often the agent follows
the prompt's protocol: result "fail", confidence 0.30-0.49, empty extractedText, and an
"insufficient evidence" phrase in the output language. This file builds the same kind of
cases on the shipped ja/en example documents so the protocol can be compared across the
three UI languages before proposing a prompt change upstream.

Every check below asks for information that lives outside the document (a registry, an
approval system, a laboratory report, a contract rate table), so the only defensible
answer is "cannot be determined from this document".

Usage (from review-item-processor/):
    uv run python evals/q7/generate_q7_suites.py
    uv run python evals/scripts/run_eval.py --suite q7/q7_en_suite.json --experiment quality --language en
    uv run python evals/scripts/run_eval.py --suite q7/q7_ja_suite.json --experiment quality --language ja
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLES = "../../../examples"  # relative to this directory (= the suite file's directory)

# (case id, use-case dir, document file, variant, check name, check description)
EN_CASES = [
    ("EN-UC004-PDF-insufficient-1", "en/use_case_004_internal_approval_request",
     "review_document_internal_approval_request.pdf", "pdf",
     "Prior-phase acceptance recorded",
     "Before this request, was the assessment-phase deliverable under document B-202506-0789 formally "
     "accepted, and is the acceptance (date and accepting manager) recorded in the project ledger? "
     "Confirm the acceptance date."),
    ("EN-UC004-PDF-insufficient-2", "en/use_case_004_internal_approval_request",
     "review_document_internal_approval_request.pdf", "pdf",
     "Budget line availability",
     "Is the requested contract amount within the remaining approved budget line for critical project "
     "ABC12345 in the finance system for the current fiscal year? Confirm the remaining budget after this "
     "commitment."),
    ("EN-UC005-PDF-insufficient-1", "en/use_case_005_sustainability_assessment",
     "review_document_equipment_specifications.pdf", "pdf",
     "Third-party efficiency verification",
     "Have the stated motor efficiency values been verified by an accredited test laboratory? Confirm the "
     "test report number, the laboratory and the report date."),
    ("EN-UC005-PDF-insufficient-2", "en/use_case_005_sustainability_assessment",
     "review_document_equipment_specifications.pdf", "pdf",
     "Current released revision",
     "Is ESD-2025-001 the current released revision in the document management system? Confirm that the "
     "revision number and release date registered in the system match this copy."),
    ("EN-UC001-PNG-insufficient-1", "en/use_case_001_house_maker_meeting_minutes",
     "review_document_floor_plan.png", "image",
     "Zoning setback compliance",
     "Does the floor plan comply with the municipality's current setback requirement for this lot? "
     "Confirm the zoning record and the required setback distance."),
    ("EN-UC001-PNG-insufficient-2", "en/use_case_001_house_maker_meeting_minutes",
     "review_document_floor_plan.png", "image",
     "Architect of record approval",
     "Has this drawing been stamped by the licensed architect of record and registered with the permit "
     "office? Confirm the registration number and date."),
]

JA_CASES = [
    ("JA-UC003-PDF-insufficient-1", "ja/ユースケース003_車庫申請", "申請書例.pdf", "pdf",
     "印鑑証明書との整合",
     "申請者欄の住所・氏名が、運輸支局に提出する印鑑証明書の記載と一致しているか。印鑑証明書の発行日と記載内容を確認する。"),
    ("JA-UC003-PDF-insufficient-2", "ja/ユースケース003_車庫申請", "申請書例.pdf", "pdf",
     "警察署での受理状況",
     "本申請が保管場所を管轄する警察署に受理され、受理番号と受理日が記録されているか確認する。"),
    ("JA-UC005-PDF-insufficient-1", "ja/ユースケース005_社内文書（製造部門）", "作業手順書.pdf", "pdf",
     "承認権限者との一致",
     "承認欄の承認者が、文書管理システムに登録された当該工程の承認権限者と一致し、承認日が記録されているか確認する。"),
    ("JA-UC005-PDF-insufficient-2", "ja/ユースケース005_社内文書（製造部門）", "作業手順書.pdf", "pdf",
     "最新有効版の確認",
     "本手順書（第1版）が文書管理システム上の最新有効版であるか。システムに登録された版数と発行日が本紙と一致するか確認する。"),
    ("JA-UC006-PDF-insufficient-1", "ja/ユースケース006_見積書（購買部門）", "見積書.pdf", "pdf",
     "承認済み単価契約との照合",
     "各明細の単価が、購買部門の承認済み単価契約（単価マスタ）に登録された範囲内であるか確認する。"),
    ("JA-UC006-PDF-insufficient-2", "ja/ユースケース006_見積書（購買部門）", "見積書.pdf", "pdf",
     "サプライヤー登録状況",
     "株式会社設備が承認済みサプライヤーマスタに登録され、与信状態が有効であるか。登録番号と登録日を確認する。"),
]

LANGUAGE_NAME = {"en": "English", "ja": "Japanese"}


def build(lang: str, cases) -> list[dict]:
    out = []
    for case_id, uc_dir, doc, variant, name, desc in cases:
        fixtures_dir = f"{EXAMPLES}/{uc_dir}"
        assert (HERE / fixtures_dir / doc).exists(), f"missing {fixtures_dir}/{doc}"
        out.append({
            "name": case_id,
            "input": {
                "document_paths": [doc],
                "fixtures_dir": fixtures_dir,
                "check_name": name,
                "check_description": desc,
                "language_name": LANGUAGE_NAME[lang],
            },
            "expected_output": {"result": "fail", "insufficient_evidence": True},
            "metadata": {"use_case": uc_dir.split("/")[1][:16], "kind": "insufficient", "variant": variant, "language": lang},
        })
    return out


def main() -> None:
    for lang, cases in (("en", EN_CASES), ("ja", JA_CASES)):
        suite = build(lang, cases)
        path = HERE / f"q7_{lang}_suite.json"
        path.write_text(json.dumps(suite, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {len(suite)} cases -> {path.relative_to(HERE.parent.parent)}")


if __name__ == "__main__":
    main()
