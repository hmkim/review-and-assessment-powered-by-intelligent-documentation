#!/usr/bin/env python3
"""
M4-d scoring: Q8 (checklist extraction quality) and Q9 (ambiguity detection).

Input : the raw records written by run_extraction.py  (<results>/raw/<slug>.json)
Output: <results>/scored/<slug>.json, <results>/scored/summary.json, <results>/scored/summary.md

Q8 for the three *designed* checklists (UC001 24 / UC002 9 / UC003 14 items):
  * designed-item recall   - is each designed check item represented by at least one
                             extracted item (any depth)?  Decided by an LLM judge
                             (Bedrock Converse, Korean), with a deterministic character
                             bigram overlap pre-screen stored alongside for inspection.
  * law mis-extraction     - number of extracted items whose content is a legal article /
                             paragraph copied from the "근거 법령 원문" section rather than a
                             check item of the checklist table (LLM classification:
                             designed / law_verbatim / meta / other).  Criterion: <= 20 % of
                             the designed-item count.
  * language               - name + description: no kana, Hangul ratio.
For official / law / form inputs only the classification counts and language are reported.

Q9: ambiguity suggestions - language (Hangul ratio, kana), NO_AMBIGUOUS symbol leakage,
    flagged counts, elapsed time, failure cause note.

The judge model is Claude Sonnet 5.5 (same family as the system under test); the judge
output is saved verbatim so every recall/classification decision can be audited by hand.

Usage:
  AWS creds in env/profile.  From review-item-processor/:
    uv run --extra evals python evals/ko/m4d/score_extraction.py --results <m4-results>/m4d
    uv run --extra evals python evals/ko/m4d/score_extraction.py --results ... --no-judge  (deterministic only)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent                    # evals/ko/m4d
REPO = HERE.parents[3]                                    # repository root
CONTENT_DIR = REPO / ".claude" / "skills" / "add-example" / "scripts"
sys.path.insert(0, str(CONTENT_DIR))
from korean_examples import uc001_privacy, uc002_building, uc003_risk  # noqa: E402

MODULES = {"uc001_privacy": uc001_privacy, "uc002_building": uc002_building, "uc003_risk": uc003_risk}
DESIGNED_ATTR = {"uc001_privacy": "_ITEMS", "uc002_building": "_RECHECK_ITEMS", "uc003_risk": "_ITEMS"}

JUDGE_MODEL = "global.anthropic.claude-sonnet-5-5"
REGION = "us-west-2"

HANGUL = re.compile(r"[가-힣]")
KANA = re.compile(r"[぀-ゟ゠-ヿ]")
LETTERS = re.compile(r"[가-힣A-Za-z぀-ゟ゠-ヿ一-鿿]")


# ----------------------------------------------------------------------------- helpers
def lang_stats(texts: list[str]) -> dict:
    joined = " ".join(t or "" for t in texts)
    letters = len(LETTERS.findall(joined))
    hangul = len(HANGUL.findall(joined))
    return {
        "hangul_ratio": round(hangul / letters, 3) if letters else None,
        "kana_chars": len(KANA.findall(joined)),
        "fields": len(texts),
    }


def bigrams(s: str) -> set[str]:
    s = re.sub(r"[\s\W_]+", "", s or "")
    return {s[i : i + 2] for i in range(len(s) - 1)}


def overlap(a: str, b: str) -> float:
    A, B = bigrams(a), bigrams(b)
    return len(A & B) / len(A) if A else 0.0  # recall of the designed text's bigrams


def depth_of(item: dict, byid: dict) -> int:
    n = 0
    cur = item
    while cur.get("parentId"):
        cur = byid.get(cur["parentId"], {})
        n += 1
        if n > 10:
            break
    return n


def designed_items(module_name: str) -> list[dict]:
    mod = MODULES[module_name]
    rows = getattr(mod, DESIGNED_ATTR[module_name])
    return [{"no": r[0], "name": r[1], "criteria": r[2], "basis": r[3] if len(r) > 3 else ""} for r in rows]


# ----------------------------------------------------------------------------- judge
JUDGE_SYSTEM = (
    "당신은 체크리스트 추출 결과를 채점하는 심사관입니다. 반드시 JSON만 출력합니다. "
    "설명이나 코드 펜스를 붙이지 않습니다."
)


def judge_prompt(designed: list[dict], extracted: list[dict]) -> str:
    d_lines = "\n".join(f"D{d['no']}: [{d['name']}] {d['criteria']}" for d in designed)
    e_lines = "\n".join(
        f"E{e['idx']} (depth {e['depth']}): [{e['name']}] {e['description']}" for e in extracted
    )
    d_ids = ", ".join(f"D{d['no']}" for d in designed)
    return f"""아래는 한국어 체크리스트 PDF 한 건에 대한 두 목록입니다.

(1) 설계 항목: PDF의 '점검 항목' 표에 들어 있던 원래의 점검 항목 {len(designed)}개.
(2) 추출 항목: RAPID가 같은 PDF에서 LLM으로 추출한 체크리스트 항목 {len(extracted)}개 (계층 구조, depth 0 = 최상위).

PDF에는 점검 항목 표 외에 '근거 법령 원문' 장(법률·시행령·고시 조문을 그대로 수록)과 점검 개요·판정 방법 설명이 함께 있습니다.

작업 A. 설계 항목 재현: 각 설계 항목 D에 대해, 그 점검 내용(무엇을 확인하는가)을 실질적으로 담고 있는 추출 항목 E를 모두 고르십시오. 표현이 달라도 점검 대상·기준이 같으면 일치입니다. 설계 항목 하나가 여러 추출 항목으로 쪼개져 있어도 각각 고르십시오. 일치하는 것이 없으면 빈 배열.

작업 B. 추출 항목 분류: 각 추출 항목 E를 다음 중 하나로 분류하십시오.
- "designed": 설계 항목 표의 점검 항목(또는 그 일부)에 해당
- "law_verbatim": 법령·고시 조문(제N조, 제N항, 각 호 등)의 내용을 점검 항목 형태로 옮긴 것. 설계 항목 표에는 없고 '근거 법령 원문' 장에서 나온 것
- "meta": 점검 개요, 판정 방법, 검산 공식 요약, 문서 종류 확인, 종합 판정 같은 절차·설명 항목이나 단순 그룹(폴더) 제목
- "other": 위 어느 것도 아님 (환각, 중복 묶음 등)

출력 JSON 형식:
{{"recall": {{"D1": ["E3", "E7"], ...}}, "classes": {{"E0": "designed", "E1": "law_verbatim", ...}}}}
recall의 키는 정확히 {d_ids} 전부, classes의 키는 E0..E{len(extracted) - 1} 전부여야 합니다.

=== (1) 설계 항목 ===
{d_lines}

=== (2) 추출 항목 ===
{e_lines}
"""


CLASS_ONLY_PROMPT = """아래는 한국어 문서 한 건에서 RAPID가 LLM으로 추출한 체크리스트 항목 {n}개입니다 (계층 구조, depth 0 = 최상위).
문서 종류: {kind_desc}

각 추출 항목 E를 다음 중 하나로 분류하십시오.
- "check_item": 점검자가 대상 문서를 보고 확인·판정할 수 있는 구체적 점검 항목
- "law_verbatim": 법령·고시 조문(제N조, 제N항, 각 호)의 내용을 그대로 옮긴 것으로, 점검 항목이라기보다 조문 요약
- "form_field": 신청서·서식의 기재 칸(이름, 주소, 날짜 등)을 항목화한 것
- "meta": 절차·설명·그룹 제목(부칙, 시행일, 목적, 정의 등 포함)
- "other": 위 어느 것도 아님

출력 JSON 형식: {{"classes": {{"E0": "...", ...}}}}  (키는 E0..E{last} 전부)

=== 추출 항목 ===
{e_lines}
"""


def call_judge(prompt: str, max_tokens: int = 16000) -> tuple[str, dict]:
    import boto3

    client = boto3.client("bedrock-runtime", region_name=REGION)
    t0 = time.time()
    resp = client.converse(
        modelId=JUDGE_MODEL,
        system=[{"text": JUDGE_SYSTEM}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens},
    )
    text = "".join(b.get("text", "") for b in resp["output"]["message"]["content"])
    usage = resp.get("usage", {})
    usage["seconds"] = round(time.time() - t0, 1)
    usage["stopReason"] = resp.get("stopReason")
    return text, usage


def parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start = text.find("{")
    return json.loads(text[start:])


# ----------------------------------------------------------------------------- scoring
def flatten(items: list[dict]) -> list[dict]:
    byid = {i["id"]: i for i in items}
    out = []
    for idx, it in enumerate(items):
        out.append(
            {
                "idx": idx,
                "id": it["id"],
                "depth": depth_of(it, byid),
                "name": it.get("name", ""),
                "description": it.get("description", "") or "",
                "hasChildren": it.get("hasChildren", False),
            }
        )
    return out


def prescreen(designed: list[dict], extracted: list[dict]) -> dict:
    """Deterministic candidate list per designed item (top-5 by bigram overlap)."""
    out = {}
    for d in designed:
        target = f"{d['name']} {d['criteria']}"
        scored = sorted(
            ((overlap(target, f"{e['name']} {e['description']}"), e["idx"]) for e in extracted),
            reverse=True,
        )[:5]
        out[f"D{d['no']}"] = [{"E": f"E{i}", "overlap": round(s, 3)} for s, i in scored]
    return out


def score_record(rec: dict, inp: dict, use_judge: bool) -> dict:
    items = rec["items"]
    ext = flatten(items)
    res = {
        "slug": rec["slug"],
        "kind": inp["kind"],
        "set_id": rec["set_id"],
        "extraction": {
            "status": rec["extraction"]["status"],
            "seconds": rec["extraction"]["seconds"],
            "items_total": len(ext),
            "items_top_level": sum(1 for e in ext if e["depth"] == 0),
            "items_leaf": sum(1 for e in ext if not e["hasChildren"]),
            "depth_hist": dict(Counter(e["depth"] for e in ext)),
        },
        "language": lang_stats([f"{e['name']} {e['description']}" for e in ext]),
    }

    judge_text, usage = None, None
    if inp["kind"] == "designed":
        designed = designed_items(inp["module"])
        res["designed_count"] = len(designed)
        res["ratio_extracted_to_designed"] = round(len(ext) / len(designed), 2)
        res["prescreen"] = prescreen(designed, ext)
        if use_judge:
            judge_text, usage = call_judge(judge_prompt(designed, ext))
            j = parse_json(judge_text)
            recall = {k: list(v) for k, v in j["recall"].items()}
            classes = j["classes"]
            matched = {k: v for k, v in recall.items() if v}
            res["recall"] = {
                "matched": len(matched),
                "total": len(designed),
                "rate": round(len(matched) / len(designed), 3),
                "missing": [k for k in recall if not recall[k]],
                "map": recall,
            }
            cls_counter = Counter(classes.values())
            res["classes"] = dict(cls_counter)
            law_n = cls_counter.get("law_verbatim", 0)
            res["law_misextraction"] = {
                "count": law_n,
                "ratio_to_designed": round(law_n / len(designed), 2),
                "criterion_max": round(0.2 * len(designed), 1),
                "pass": law_n <= 0.2 * len(designed),
            }
            res["recall_pass"] = res["recall"]["rate"] >= 0.8
            res["items_annotated"] = [
                {**e, "class": classes.get(f"E{e['idx']}")} for e in ext
            ]
    else:
        if use_judge:
            judge_text, usage = call_judge(
                CLASS_ONLY_PROMPT.format(
                    n=len(ext),
                    kind_desc=inp.get("description", inp["kind"]),
                    last=len(ext) - 1,
                    e_lines="\n".join(
                        f"E{e['idx']} (depth {e['depth']}): [{e['name']}] {e['description']}" for e in ext
                    ),
                )
            )
            j = parse_json(judge_text)
            classes = j["classes"]
            res["classes"] = dict(Counter(classes.values()))
            res["items_annotated"] = [{**e, "class": classes.get(f"E{e['idx']}")} for e in ext]
    if not use_judge:
        res["items_annotated"] = ext
    if judge_text is not None:
        res["judge"] = {"model": JUDGE_MODEL, "usage": usage, "raw": judge_text}

    # ---- Q9 (absent when the run used --skip-ambiguity)
    amb = rec.get("ambiguity") or {"status": "skipped", "seconds": None, "items": []}
    amb_items = amb.get("items", [])
    flagged = [i for i in amb_items if i.get("ambiguityReview")]
    suggestions = [s for i in flagged for s in i["ambiguityReview"].get("suggestions", [])]
    leaf_with_desc = [i for i in amb_items if not i.get("hasChildren") and i.get("description")]
    ts = sorted(i["ambiguityReview"].get("detectedAt", "") for i in flagged)
    res["ambiguity"] = {
        "status": amb["status"],
        "seconds": amb.get("seconds"),
        "leaf_items_with_description": len(leaf_with_desc),
        "flagged": len(flagged),
        "flagged_ratio": round(len(flagged) / len(leaf_with_desc), 3) if leaf_with_desc else None,
        "suggestions_total": len(suggestions),
        "suggestions_per_flagged": round(len(suggestions) / len(flagged), 2) if flagged else None,
        "language": lang_stats(suggestions),
        "no_ambiguous_leak": sum("NO_AMBIGUOUS" in s for s in suggestions),
        "first_detected": ts[0] if ts else None,
        "last_detected": ts[-1] if ts else None,
        "seconds_per_processed_item": None,
    }
    if ts and len(flagged) > 1 and amb["status"] == "completed":
        from datetime import datetime

        span = (datetime.fromisoformat(ts[-1].replace("Z", "+00:00")) - datetime.fromisoformat(ts[0].replace("Z", "+00:00"))).total_seconds()
        res["ambiguity"]["seconds_per_processed_item"] = round(span / max(len(leaf_with_desc) - 1, 1), 1)
    return res


# ----------------------------------------------------------------------------- summary
def md_table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def write_summary(scored: list[dict], inputs: dict, out_dir: Path) -> None:
    lines = ["# M4-d Q8 · Q9 채점 요약", ""]
    lines.append(f"판정 모델(judge): `{JUDGE_MODEL}`. 원 출력은 각 `scored/<slug>.json`의 `judge.raw`.")
    lines.append("")
    lines.append("## Q8-1 설계 체크리스트 3건: 재현율과 조문 오추출")
    rows = []
    for s in scored:
        if s["kind"] != "designed":
            continue
        r = s.get("recall", {})
        lm = s.get("law_misextraction", {})
        rows.append(
            [
                inputs[s["slug"]]["name"].replace("[M4-d] ", ""),
                s["designed_count"],
                s["extraction"]["items_total"],
                f"{r.get('matched', '-')}/{r.get('total', '-')} ({r.get('rate', '-')})",
                "충족" if s.get("recall_pass") else "미달",
                f"{lm.get('count', '-')} (≤ {lm.get('criterion_max', '-')})",
                "충족" if lm.get("pass") else "미달",
                s["classes"].get("designed", "-") if "classes" in s else "-",
                s["classes"].get("meta", "-") if "classes" in s else "-",
                s["extraction"]["seconds"],
            ]
        )
    lines.append(
        md_table(
            ["문서", "설계 항목", "추출 항목", "재현 (≥ 0.80)", "판정", "조문 오추출 (기준)", "판정", "designed", "meta", "추출 s"],
            rows,
        )
    )
    lines.append("")
    lines.append("## Q8-2 공식·법령·양식 입력: 추출 항목 분류")
    rows = []
    for s in scored:
        if s["kind"] == "designed":
            continue
        c = s.get("classes", {})
        rows.append(
            [
                inputs[s["slug"]]["name"].replace("[M4-d] ", ""),
                s["kind"],
                s["extraction"]["items_total"],
                c.get("check_item", "-"),
                c.get("law_verbatim", "-"),
                c.get("form_field", "-"),
                c.get("meta", "-"),
                c.get("other", "-"),
                s["extraction"]["seconds"],
            ]
        )
    lines.append(md_table(["문서", "종류", "추출 항목", "check_item", "law_verbatim", "form_field", "meta", "other", "추출 s"], rows))
    lines.append("")
    lines.append("## Q8-3 언어 (name + description)")
    rows = [
        [inputs[s["slug"]]["name"].replace("[M4-d] ", ""), s["language"]["hangul_ratio"], s["language"]["kana_chars"]]
        for s in scored
    ]
    lines.append(md_table(["문서", "한글 비율", "가나 문자"], rows))
    lines.append("")
    lines.append("## Q9 모호성 검출")
    rows = []
    for s in scored:
        a = s["ambiguity"]
        rows.append(
            [
                inputs[s["slug"]]["name"].replace("[M4-d] ", ""),
                a["status"],
                a["leaf_items_with_description"],
                f"{a['flagged']} ({a['flagged_ratio']})",
                a["suggestions_total"],
                a["language"]["hangul_ratio"],
                a["language"]["kana_chars"],
                a["no_ambiguous_leak"],
                a["seconds"],
                a["seconds_per_processed_item"] if a["seconds_per_processed_item"] is not None else "-",
            ]
        )
    lines.append(
        md_table(
            ["문서", "상태", "대상(leaf)", "플래그 (비율)", "제안 수", "한글 비율", "가나", "NO_AMBIGUOUS 누출", "소요 s", "항목당 s"],
            rows,
        )
    )
    lines.append("")
    lines.append("## 재현 매핑 (설계 항목 -> 추출 항목)")
    for s in scored:
        if "recall" not in s:
            continue
        lines.append(f"### {inputs[s['slug']]['name']}")
        designed = designed_items(inputs[s["slug"]]["module"])
        byidx = {e["idx"]: e for e in s["items_annotated"]}
        rows = []
        for d in designed:
            ms = s["recall"]["map"].get(f"D{d['no']}", [])
            names = "; ".join(byidx[int(m[1:])]["name"] for m in ms if m[1:].isdigit() and int(m[1:]) in byidx)
            rows.append([d["no"], d["name"], len(ms), names or "**없음**"])
        lines.append(md_table(["No", "설계 항목", "일치 수", "일치한 추출 항목 name"], rows))
        lines.append("")
    lines.append("## 부록: 추출 항목 전체 (분류 포함)")
    for s in scored:
        lines.append(f"### {inputs[s['slug']]['name']} ({s['extraction']['items_total']})")
        for e in s["items_annotated"]:
            cls = e.get("class", "")
            lines.append(f"- E{e['idx']} d{e['depth']} `{cls}` **{e['name']}** - {e['description'][:140]}")
        lines.append("")
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, help="m4d results dir containing inputs.json and raw/")
    ap.add_argument("--no-judge", action="store_true", help="deterministic stats only (no Bedrock call)")
    ap.add_argument("--only", action="append", default=[], help="slug filter (repeatable)")
    args = ap.parse_args()

    results = Path(args.results)
    inputs = {i["slug"]: i for i in json.loads((results / "inputs.json").read_text())}
    out_dir = results / "scored"
    out_dir.mkdir(exist_ok=True)

    scored = []
    for slug, inp in inputs.items():
        if args.only and slug not in args.only:
            continue
        raw = results / "raw" / f"{slug}.json"
        if not raw.exists():
            print(f"skip {slug}: no raw result")
            continue
        existing = out_dir / f"{slug}.json"
        if existing.exists() and not args.no_judge and "judge" in json.loads(existing.read_text()):
            print(f"reuse {slug}")
            scored.append(json.loads(existing.read_text()))
            continue
        rec = json.loads(raw.read_text())
        print(f"scoring {slug} ({len(rec['items'])} items)...", flush=True)
        s = score_record(rec, inp, use_judge=not args.no_judge)
        existing.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
        if "judge" in s:
            print(f"  judge: {s['judge']['usage']}")
        scored.append(s)

    compact = []
    for s in scored:
        compact.append({k: v for k, v in s.items() if k not in ("items_annotated", "judge", "prescreen")})
    (out_dir / "summary.json").write_text(json.dumps(compact, ensure_ascii=False, indent=1), encoding="utf-8")
    write_summary(scored, inputs, out_dir)
    print(f"wrote {out_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
