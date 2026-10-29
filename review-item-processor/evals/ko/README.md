# RAPID 심사 에이전트 한국어 평가 세트

[English](../README.md) | [日本語](../ja/README.md) | 한국어

`examples/ko`의 한국어 예제 문서로 심사 에이전트(`review-item-processor`)의 **출력 품질**을 측정하는 평가 세트입니다. 기존 평가 프레임워크(strands-evals 기반, [영어 README](../README.md) 참조)에 한국어 출력 검증에 필요한 evaluator를 더해 `--experiment quality`로 실행합니다.

## 빠른 시작

```bash
cd review-item-processor
uv sync --extra evals

# 1) 평가 세트 생성 (examples/ko 문서와 체크리스트 정의에서 케이스를 만듭니다)
uv run python evals/ko/examples/generate_suite.py

# 2) 실행 (Bedrock 자격 증명 필요, 기본 모델은 agent.py의 DEFAULT_DOCUMENT_MODEL_ID)
export AWS_REGION=us-west-2 BEDROCK_REGION=us-west-2 ENABLE_CITATIONS=true
uv run --extra evals python evals/scripts/run_eval.py \
  --suite ko/examples/korean_examples_suite.json \
  --experiment quality --output results/ko_quality_run1.json
```

`--suite` 경로는 `evals/` 디렉터리 기준입니다. 결과 JSON에는 케이스별 에이전트 출력(`explanation`, `shortExplanation`, `extractedText`, `pageNumber`, `reviewMeta`)과 evaluator별 점수·세부 사유, 집계 지표(`aggregated_metrics`)가 저장됩니다. LLM-as-judge 호출을 생략하려면 `--no-llm-judge`를 붙입니다.

## 평가 세트 구성

`generate_suite.py`는 `.claude/skills/add-example/scripts/korean_examples/`의 체크리스트 항목 정의와 결함 목록(`DEFECTS`)에서 케이스를 **생성**합니다. 정답을 두 곳에 적지 않기 위한 구조이며, 예제 문서나 체크리스트가 바뀌면 다시 실행합니다.

| 유스케이스 | 심사 대상 | fail (결함) | pass (정상) | 근거 부족 |
| --- | --- | --- | --- | --- |
| 001 개인정보 처리방침 | `심사대상_가온누리투어_개인정보_처리방침.pdf` | 6 | 9 | 1 (홈페이지 게재 여부) |
| 002 설계개요 검산 | `심사대상_근린생활시설_신축_설계개요서.pdf` | 4 | 5 | 1 (설계도서와 면적 일치) |
| 003 위험성평가 | `심사대상_프레스공정_위험성평가_결과서.pdf` | 5 | 8 | 1 (작업환경측정 결과서 원본) |
| 합계 | | 15 | 22 | 3 → **40 케이스** |

- 케이스 1건 = 체크리스트 항목 1개(`check_name` / `check_description`는 체크리스트 PDF 본문과 동일) × 심사 대상 PDF.
- **fail**: 문서에 의도적으로 넣은 결함을 겨냥한 항목(정답표는 `examples/ko/README.md`). UC002 항목 4(제외 면적 확인)와 항목 5(용적률 재계산)는 같은 결함(지하층 포함 용적률)을 입력·결과 양쪽에서 보는 것이라 둘 다 fail입니다.
- **pass**: 문서가 충족하는 항목.
- **근거 부족**: 문서 밖의 정보가 필요한 점검(홈페이지 게재 여부 등). 프롬프트 규약대로 `result: fail`, `confidence ≤ 0.49`, `extractedText: ""`가 기대값이며 `expected_output.insufficient_evidence: true`로 표시됩니다.
- 판정이 갈릴 수 있는 항목(해당 처리가 없는 '해당 시' 항목 등)은 `generate_suite.py`의 `AMBIGUOUS`에 사유와 함께 제외되어 있습니다.
- 문서는 복사하지 않고 케이스별 `fixtures_dir`로 `examples/ko/…`를 가리킵니다. `fixtures_manifest.json`에 참조한 PDF의 sha256·크기가 기록되므로 결과를 비교할 때 같은 문서였는지 확인할 수 있습니다.
- `--with-image-variants`: `fixtures/image/<유스케이스>/` 아래에 래스터화(스캔 가정)한 PDF가 있으면 fail 케이스를 이미지 경로용으로 복제합니다(코퍼스 준비 단계에서 사용).

## 측정 항목

`--experiment quality`는 기존 정확도·확신도 보정 evaluator에 다음을 더합니다. 모두 `evals/quality_evaluators.py`에 있고 언어 매개변수를 받으므로 ja/en 세트에도 쓸 수 있습니다.

| Evaluator | 측정 내용 | 통과 기준(케이스) | 세트 수용 기준 |
| --- | --- | --- | --- |
| `OutputLanguageEvaluator(language="ko")` | `explanation`·`shortExplanation`의 문자 종류 집계. 가나(일본어) 혼입은 즉시 실패, 영문 약어·URL·단위는 중립 처리 | 한글 비율 ≥ 70%, 가나 0 | 준수율 100% |
| `JsonParseEvaluator` | 에이전트가 JSON 파싱 폴백(`Failed to analyze JSON parse` 등)을 반환했는지 | 폴백 아님 | 100% |
| `ShortExplanationLengthEvaluator(max_chars=80)` | 프롬프트의 "80자 이내" 규칙 | 1~80자 | 80자 초과 ≤ 5%, 분포(중앙값·p95) 보고 |
| `CitationFidelityEvaluator` | `extractedText`의 각 인용이 PDF 텍스트 레이어(pypdf)에 실제로 있는지. 문자·숫자만 남기는 정규화 후 비교하고, 에이전트가 말한 `pageNumber`에서 찾으면 `page_match`, 다른 쪽이면 `other_page`, 없으면 `mismatch`. 이미지 심사는 해당 없음 | `mismatch` 0 | mismatch 0건 또는 건별 원인 문서화 |
| `InsufficientEvidenceEvaluator` | 근거 부족 케이스의 규약 준수(fail / ≤ 0.49 / 빈 extractedText)와 사용된 문구 수집 | 3항목 모두 충족 | 규약 100%, 문구 2종 이하 |
| `OutputEvaluator`(LLM-as-judge) | 설명의 명확성·근거·완결성·언어·관련성 | — | 평균 점수 보고 |

집계 결과는 결과 JSON의 `aggregated_metrics.Quality`에, 요약은 실행 끝의 `OUTPUT QUALITY` 절에 출력됩니다. 정확도 지표(재현율·정밀도·고확신 오판)는 기존과 같이 `AccuracyEvaluator` / `ConfidenceCalibrationEvaluator` 절에 나옵니다.

## 결과 해석 시 주의

- 모델 출력은 실행마다 달라집니다. 수용 기준은 **같은 세트를 3회 실행**한 결과로 판정하고, 1회 측정값을 "항상"으로 적지 않습니다.
- `CitationFidelityEvaluator`의 `other_page`는 인용은 정확하지만 `pageNumber`가 틀린 경우입니다. `mismatch`는 정규화 후에도 문서에 없는 문자열이므로 환각 또는 패러프레이즈를 뜻합니다.
- 근거 부족 문구가 3종 이상이면 프롬프트에 한국어 표준 문구("근거 불충분")를 지시하는 변경을 검토합니다.
- 이 세트는 예제 문서를 만들 때 설계한 결함을 그대로 채점하므로 "최소 기능 확인"입니다. 실물 문서(띄어쓰기가 소실된 법령 PDF, HWP 변환본, 스캔본)로 보완해야 일반화 여부를 말할 수 있습니다.

## 파일

```
evals/ko/
├── README.md
└── examples/
    ├── generate_suite.py          # 세트 생성기 (정답 정의 포함)
    ├── korean_examples_suite.json # 생성된 40 케이스
    └── fixtures_manifest.json     # 참조한 PDF의 sha256
```

단위 테스트: `uv run --extra evals --extra dev pytest tests/test_quality_evaluators.py` (Bedrock 호출 없음).
