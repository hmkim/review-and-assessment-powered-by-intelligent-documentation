#!/usr/bin/env python3
"""
Aggregate repeated `run_eval.py --experiment quality` result files into the M4 report tables.

Input:  a directory holding run{N}_{suite}.json files (N = 1..R) written by run_eval.py --output.
Output: summary.json (machine readable) + summary.md (tables ready to paste into the report).

Metrics follow docs/ko/m4-quality-plan Q1~Q7 and Q11:
  Q1 output language, Q2 JSON parse, Q3 shortExplanation length, Q4 citation fidelity,
  Q5 review accuracy (per run and pooled), Q6 determinism across runs, Q7 insufficient-evidence
  protocol + phrase variety, Q11 cost/time as recorded in review_meta.

Usage:
  python evals/ko/aggregate_runs.py --results-dir /path/to/raw --out /path/to/aggregate
"""

from __future__ import annotations

import argparse
import json
import re
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

RUN_RE = re.compile(r"^run(\d+)_([a-z0-9]+)\.json$")


def parse_details(details: str) -> dict[str, str]:
    """'a=1|b=x' -> {'a': '1', 'b': 'x'}; the phrase= value may itself contain '|' so split at most once per key."""
    out: dict[str, str] = {}
    for chunk in details.split("|"):
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def load_runs(results_dir: Path) -> dict[str, dict[int, dict]]:
    runs: dict[str, dict[int, dict]] = defaultdict(dict)
    for path in sorted(results_dir.glob("run*_*.json")):
        m = RUN_RE.match(path.name)
        if not m:
            continue
        runs[m.group(2)][int(m.group(1))] = json.loads(path.read_text(encoding="utf-8"))
    return runs


def pct(num: float, den: float) -> str:
    return f"{100.0 * num / den:.1f}%" if den else "n/a"


def aggregate_suite(suite: str, by_run: dict[int, dict]) -> dict:
    run_ids = sorted(by_run)
    per_run: dict[int, dict] = {}
    # case_name -> run -> record
    cases: dict[str, dict[int, dict]] = defaultdict(dict)
    for r in run_ids:
        for rec in by_run[r]["case_results"]:
            cases[rec["case_name"]][r] = rec

    for r in run_ids:
        recs = by_run[r]["case_results"]
        ok = [c for c in recs if c.get("agent_output")]
        agg = by_run[r]["aggregated_metrics"]
        q = agg.get("Quality", {})
        acc = agg.get("AccuracyEvaluator", {})
        cal = agg.get("ConfidenceCalibrationEvaluator", {})
        judge = agg.get("OutputEvaluator", {})
        meta = [c["agent_output"]["review_meta"] for c in ok if c["agent_output"].get("review_meta")]
        durations = [m["duration_seconds"] for m in meta]
        out_tokens = [m["output_tokens"] for m in meta]
        in_tokens = [m["input_tokens"] for m in meta]
        per_run[r] = {
            "cases": len(recs),
            "task_errors": by_run[r].get("failed_cases", 0),
            "accuracy": acc.get("accuracy"),
            "recall": acc.get("recall"),
            "precision": acc.get("precision"),
            "false_positive_count": acc.get("false_positive_count"),
            "false_negative_count": acc.get("false_negative_count"),
            "critical_error_count": cal.get("critical_error_count"),
            "judge_mean": judge.get("mean_score"),
            "judge_min": judge.get("min_score"),
            "language_compliance": q.get("language", {}).get("compliance_rate"),
            "foreign_letter_cases": q.get("language", {}).get("foreign_letter_cases"),
            "min_explanation_ratio": q.get("language", {}).get("min_explanation_ratio"),
            "json_parse_rate": q.get("json_parse", {}).get("parse_rate"),
            "short_median": q.get("short_explanation", {}).get("median_chars"),
            "short_p95": q.get("short_explanation", {}).get("p95_chars"),
            "short_max": q.get("short_explanation", {}).get("max_chars"),
            "short_over_limit": q.get("short_explanation", {}).get("over_limit_count"),
            "citation": q.get("citation", {}),
            "insufficient": q.get("insufficient_evidence", {}),
            "duration_median_s": round(st.median(durations), 1) if durations else None,
            "duration_p95_s": round(sorted(durations)[int(0.95 * (len(durations) - 1))], 1) if durations else None,
            "duration_max_s": max(durations) if durations else None,
            "output_tokens_median": st.median(out_tokens) if out_tokens else None,
            "output_tokens_total": sum(out_tokens),
            "input_tokens_reported_total": sum(in_tokens),
            "reported_cost_usd": round(sum(m["total_cost"] for m in meta), 4),
        }

    # Q6 determinism: per-case result agreement across runs + confidence spread
    det = {"cases": 0, "all_agree": 0, "disagree_cases": [], "conf_std_median": None, "conf_std_max": None}
    conf_stds = []
    for name, by_r in cases.items():
        outs = [by_r[r]["agent_output"] for r in run_ids if r in by_r and by_r[r].get("agent_output")]
        if len(outs) < len(run_ids):
            continue
        det["cases"] += 1
        results = [o["result"] for o in outs]
        confs = [float(o["confidence"]) for o in outs]
        conf_stds.append(st.pstdev(confs))
        if len(set(results)) == 1:
            det["all_agree"] += 1
        else:
            det["disagree_cases"].append({
                "case": name,
                "expected": next(iter(by_r.values()))["expected_output"].get("result"),
                "results": results,
                "confidences": confs,
            })
    if conf_stds:
        det["conf_std_median"] = round(st.median(conf_stds), 3)
        det["conf_std_max"] = round(max(conf_stds), 3)
    det["agreement_rate"] = det["all_agree"] / det["cases"] if det["cases"] else None

    # Pooled wrong-judgement list (expected != actual) with run membership
    wrong: dict[str, dict] = {}
    for name, by_r in cases.items():
        for r in run_ids:
            rec = by_r.get(r)
            if not rec or not rec.get("agent_output"):
                continue
            exp = rec["expected_output"].get("result")
            act = rec["agent_output"]["result"]
            if exp != act:
                w = wrong.setdefault(name, {
                    "case": name, "expected": exp, "runs": [], "confidences": [], "short_explanations": [],
                    "basis": rec["metadata"].get("basis"), "check_name": rec["input"].get("check_name"),
                    "defect_text": rec["metadata"].get("defect_text"),
                })
                w["runs"].append(r)
                w["confidences"].append(rec["agent_output"]["confidence"])
                w["short_explanations"].append(rec["agent_output"]["short_explanation"])

    # Q4 citation mismatches with coverage, pooled
    cit_mismatch: list[dict] = []
    cit_totals = Counter()
    for name, by_r in cases.items():
        for r in run_ids:
            rec = by_r.get(r)
            if not rec or not rec.get("evaluations"):
                continue
            d = parse_details(rec["evaluations"].get("CitationFidelityEvaluator", {}).get("details", ""))
            if d.get("applicable") != "1":
                cit_totals["not_applicable_" + d.get("cause", "?")] += 1
                continue
            for k in ("citations", "page_match", "other_page", "mismatch"):
                cit_totals[k] += int(d.get(k, 0))
            if int(d.get("mismatch", 0)) > 0:
                cit_mismatch.append({
                    "case": name, "run": r, "mismatch": int(d["mismatch"]), "citations": int(d["citations"]),
                    "coverage": float(d["mismatch_coverage"]) if "mismatch_coverage" in d else None,
                    "reference_pdf": d.get("reference") == "1",
                    "page_number": d.get("page_number"),
                    "extracted_text": rec["agent_output"].get("extracted_text"),
                })

    # Q7 insufficient-evidence protocol + phrases, pooled
    insuf = {"applicable": 0, "protocol_pass": 0, "fail_components": Counter(), "phrases": [], "details": []}
    for name, by_r in cases.items():
        for r in run_ids:
            rec = by_r.get(r)
            if not rec or not rec.get("evaluations"):
                continue
            d = parse_details(rec["evaluations"].get("InsufficientEvidenceEvaluator", {}).get("details", ""))
            if d.get("applicable") != "1":
                continue
            insuf["applicable"] += 1
            passed = rec["evaluations"]["InsufficientEvidenceEvaluator"].get("pass")
            insuf["protocol_pass"] += int(bool(passed))
            for comp in ("result_fail", "low_confidence", "standard_phrase", "empty_extracted"):
                if d.get(comp) == "0":
                    insuf["fail_components"][comp] += 1
            phrase = rec["agent_output"].get("short_explanation", "")
            insuf["phrases"].append(phrase)
            insuf["details"].append({
                "case": name, "run": r, "result": rec["agent_output"]["result"],
                "confidence": rec["agent_output"]["confidence"],
                "extracted_count": len(rec["agent_output"].get("extracted_text") or []),
                "phrase": phrase,
            })
    insuf["fail_components"] = dict(insuf["fail_components"])
    insuf["distinct_phrases"] = len(set(insuf["phrases"]))

    # Q3 pooled distribution (all runs)
    lens = [len(by_r[r]["agent_output"]["short_explanation"]) for by_r in cases.values() for r in run_ids
            if r in by_r and by_r[r].get("agent_output")]
    q3 = {
        "n": len(lens), "median": st.median(lens) if lens else None,
        "p95": sorted(lens)[int(0.95 * (len(lens) - 1))] if lens else None, "max": max(lens) if lens else None,
        "over_80": sum(1 for x in lens if x > 80), "under_20": sum(1 for x in lens if x < 20),
    }

    # Pooled accuracy over all runs
    pooled = Counter()
    for by_r in cases.values():
        for r in run_ids:
            rec = by_r.get(r)
            if not rec or not rec.get("agent_output"):
                continue
            exp, act = rec["expected_output"].get("result"), rec["agent_output"]["result"]
            pooled["n"] += 1
            pooled["correct"] += int(exp == act)
            if exp == "fail":
                pooled["fail_n"] += 1
                pooled["fail_hit"] += int(act == "fail")
            else:
                pooled["pass_n"] += 1
                pooled["pass_hit"] += int(act == "pass")

    return {
        "suite": suite, "runs": run_ids, "per_run": per_run, "determinism": det,
        "wrong_judgements": sorted(wrong.values(), key=lambda w: (-len(w["runs"]), w["case"])),
        "citation_totals": dict(cit_totals), "citation_mismatches": cit_mismatch,
        "insufficient_evidence": insuf, "short_explanation_pooled": q3,
        "pooled_accuracy": {k: pooled.get(k, 0) for k in ("n", "correct", "fail_n", "fail_hit", "pass_n", "pass_hit")},
    }


def fmt(v, nd=3):
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def render_md(summary: dict) -> str:
    L: list[str] = []
    L.append("# M4-c 집계 (자동 생성: evals/ko/aggregate_runs.py)\n")
    for s in summary["suites"]:
        L.append(f"\n## 세트 `{s['suite']}` (run {', '.join(map(str, s['runs']))})\n")
        L.append("| run | 케이스 | 오류 | accuracy | recall | precision | FP | FN | 고확신 오판 | judge 평균(최소) | 언어 준수 | 가나 혼입 | JSON | short 중앙/p95/최대 | 80자 초과 | 지연 중앙/p95 (s) | 출력토큰 중앙 | 기록 비용 $ |")
        L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for r, p in s["per_run"].items():
            L.append(
                f"| {r} | {p['cases']} | {p['task_errors']} | {fmt(p['accuracy'])} | {fmt(p['recall'])} | {fmt(p['precision'])} "
                f"| {p['false_positive_count']} | {p['false_negative_count']} | {p['critical_error_count']} "
                f"| {fmt(p['judge_mean'], 2)} ({fmt(p['judge_min'], 2)}) | {pct(p['language_compliance'] or 0, 1)} | {p['foreign_letter_cases']} "
                f"| {pct(p['json_parse_rate'] or 0, 1)} | {fmt(p['short_median'], 0)}/{fmt(p['short_p95'], 0)}/{p['short_max']} | {p['short_over_limit']} "
                f"| {p['duration_median_s']}/{p['duration_p95_s']} | {fmt(p['output_tokens_median'], 0)} | {p['reported_cost_usd']} |"
            )
        pa = s["pooled_accuracy"]
        L.append(f"\n- 3회 합산: 정확도 {pa['correct']}/{pa['n']} = {pct(pa['correct'], pa['n'])}, fail 재현 {pa['fail_hit']}/{pa['fail_n']}, pass 정밀 {pa['pass_hit']}/{pa['pass_n']}")
        d = s["determinism"]
        L.append(f"- Q6 결정성: 3회 모두 같은 result인 케이스 {d['all_agree']}/{d['cases']} = {pct(d['all_agree'], d['cases'])}, confidence 표준편차 중앙 {d['conf_std_median']} / 최대 {d['conf_std_max']}")
        for dc in d["disagree_cases"]:
            L.append(f"  - 불일치: `{dc['case']}` 정답 {dc['expected']} → {dc['results']} (conf {dc['confidences']})")
        q3 = s["short_explanation_pooled"]
        L.append(f"- Q3 shortExplanation(3회 합산 {q3['n']}건): 중앙 {q3['median']}자, p95 {q3['p95']}자, 최대 {q3['max']}자, 80자 초과 {q3['over_80']}건, 20자 미만 {q3['under_20']}건")
        ct = s["citation_totals"]
        n_c = ct.get("citations", 0)
        L.append(f"- Q4 Citations(3회 합산): 인용 {n_c}건 중 지정 페이지 일치 {ct.get('page_match', 0)} ({pct(ct.get('page_match', 0), n_c)}), 다른 페이지에서 일치 {ct.get('other_page', 0)} ({pct(ct.get('other_page', 0), n_c)}), 불일치 {ct.get('mismatch', 0)} ({pct(ct.get('mismatch', 0), n_c)}); 비적용 " + ", ".join(f"{k.replace('not_applicable_', '')}={v}" for k, v in ct.items() if k.startswith("not_applicable_")))
        ie = s["insufficient_evidence"]
        if ie["applicable"]:
            L.append(f"- Q7 근거 부족({ie['applicable']}건): 규약 통과 {ie['protocol_pass']}/{ie['applicable']}, 미통과 요소 {ie['fail_components']}, 문구 종류 {ie['distinct_phrases']}")
        if s["wrong_judgements"]:
            L.append("\n### 오판 케이스 (expected ≠ actual)\n")
            L.append("| 케이스 | 정답 | 발생 run | confidence | 항목 | shortExplanation(run별) |")
            L.append("| --- | --- | --- | --- | --- | --- |")
            for w in s["wrong_judgements"]:
                se = " / ".join(x.replace("|", "／") for x in w["short_explanations"])
                L.append(f"| `{w['case']}` | {w['expected']} | {w['runs']} | {w['confidences']} | {w['check_name']} | {se} |")
        if s["citation_mismatches"]:
            L.append("\n### Citations 불일치 건\n")
            L.append("| 케이스 | run | 불일치/인용 | 토큰 포함율 | 참조 PDF | 인용문(불일치 포함, 앞 120자) |")
            L.append("| --- | --- | --- | --- | --- | --- |")
            for c in s["citation_mismatches"]:
                ex = " ‖ ".join((t or "")[:120].replace("|", "／").replace("\n", " ") for t in (c["extracted_text"] or []))
                L.append(f"| `{c['case']}` | {c['run']} | {c['mismatch']}/{c['citations']} | {fmt(c['coverage'], 2)} | {'예' if c['reference_pdf'] else '아니오'} | {ex} |")
        if ie["details"]:
            L.append("\n### 근거 부족 케이스 출력\n")
            L.append("| 케이스 | run | result | confidence | extractedText 수 | shortExplanation |")
            L.append("| --- | --- | --- | --- | --- | --- |")
            for x in ie["details"]:
                L.append(f"| `{x['case']}` | {x['run']} | {x['result']} | {x['confidence']} | {x['extracted_count']} | {x['phrase'].replace('|', '／')} |")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    runs = load_runs(args.results_dir)
    if not runs:
        raise SystemExit(f"no run*_*.json under {args.results_dir}")
    manifest_path = args.results_dir.parent / "run_manifest.json"
    summary = {
        "results_dir": str(args.results_dir),
        "manifest": json.loads(manifest_path.read_text()) if manifest_path.exists() else None,
        "suites": [aggregate_suite(suite, by_run) for suite, by_run in sorted(runs.items())],
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "summary.md").write_text(render_md(summary), encoding="utf-8")
    print(f"wrote {args.out / 'summary.json'} and {args.out / 'summary.md'}")
    for s in summary["suites"]:
        d = s["determinism"]
        pa = s["pooled_accuracy"]
        print(f"{s['suite']:9s} pooled acc {pa['correct']}/{pa['n']}  recall {pa['fail_hit']}/{pa['fail_n']}  "
              f"determinism {d['all_agree']}/{d['cases']}  citation mismatch {s['citation_totals'].get('mismatch', 0)}/{s['citation_totals'].get('citations', 0)}  "
              f"insufficient pass {s['insufficient_evidence']['protocol_pass']}/{s['insufficient_evidence']['applicable']}")


if __name__ == "__main__":
    main()
