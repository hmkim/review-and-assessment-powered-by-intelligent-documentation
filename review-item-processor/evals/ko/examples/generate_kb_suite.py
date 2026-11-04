#!/usr/bin/env python3
"""
Q10 (Knowledge Base citation) suite generator.

Takes the UC001 cases of korean_examples_suite.json (the privacy-policy use case, whose
checklist cites the 개인정보위 작성지침 that lives in knowledge_base_sources/) and writes
two arms with identical cases:

  korean_kb_on_suite.json   tool_configuration.knowledgeBase = [{knowledgeBaseId: <id>}]
  korean_kb_off_suite.json  tool_configuration = {}   (control arm)

Usage:
  python evals/ko/examples/generate_kb_suite.py --kb-id <KB id> [--only-fail]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "korean_examples_suite.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb-id", required=True)
    ap.add_argument("--data-source-id", default=None)
    ap.add_argument("--only-fail", action="store_true", help="keep only the designed-defect (fail) cases")
    args = ap.parse_args()

    suite = json.loads(SRC.read_text(encoding="utf-8"))
    cases = suite["cases"] if isinstance(suite, dict) else suite
    uc = [c for c in cases if c.get("metadata", {}).get("use_case") == "001"]
    if args.only_fail:
        uc = [c for c in uc if c["metadata"].get("kind") == "fail"]
    kb = {"knowledgeBaseId": args.kb_id}
    if args.data_source_id:
        kb["dataSourceIds"] = [args.data_source_id]

    for arm, tool_conf in (("on", {"knowledgeBase": [kb]}), ("off", {})):
        out_cases = []
        for c in uc:
            d = json.loads(json.dumps(c, ensure_ascii=False))
            d["name"] = d["name"].replace("KO-UC001", f"KO-UC001-KB{arm}")
            d["input"]["tool_configuration"] = tool_conf
            d["metadata"]["kb_arm"] = arm
            out_cases.append(d)
        out = HERE / f"korean_kb_{arm}_suite.json"
        payload = {"description": f"Q10 KB citation, arm={arm}, UC001 cases from korean_examples_suite.json", "cases": out_cases} if isinstance(suite, dict) else out_cases
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{out.name}: {len(out_cases)} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
