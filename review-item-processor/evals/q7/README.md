# Q7 cross-language suites: insufficient-evidence protocol

`generate_q7_suites.py` builds two small suites (`q7_en_suite.json`, `q7_ja_suite.json`, 6 cases each) on the shipped `examples/en` and `examples/ja` documents. Every check asks for information the document cannot contain, so the expected answer is the prompt's insufficient-evidence protocol (`result: fail`, `confidence ≤ 0.49`, the "insufficient evidence" phrase, and — as written today — an empty `extractedText`). They complement the Korean cases in `evals/ko` and were used to show that the empty-`extractedText` rule fails on the Citations (document-block) path in every language, not only in Korean.

```bash
uv run python evals/q7/generate_q7_suites.py
uv run python evals/scripts/run_eval.py --suite q7/q7_en_suite.json --experiment quality --language en --output <dir>/run1_en.json
uv run python evals/scripts/run_eval.py --suite q7/q7_ja_suite.json --experiment quality --language ja --output <dir>/run1_ja.json
python evals/ko/aggregate_runs.py --results-dir <dir> --out <dir>/aggregate   # phrase table + protocol components
```

Known case notes: `EN-UC004-PDF-insufficient-2` (budget line) is answerable from the document (it states the remaining budget), so exclude it from protocol statistics; `JA-UC005-PDF-insufficient-1` hits a genuinely blank approval field, so the model may report a real defect with high confidence.

Results and the resulting proposal are summarised in `docs/ko/m4-quality-report.md` §4.6.
