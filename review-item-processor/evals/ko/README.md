# RAPID 심사 에이전트 한국어 평가 세트

[English](../README.md) | [日本語](../ja/README.md) | 한국어

한국어 문서로 심사 에이전트(`review-item-processor`)의 **출력 품질**을 측정하는 평가 세트입니다. 기존 평가 프레임워크(strands-evals 기반, [영어 README](../README.md) 참조)에 한국어 출력 검증에 필요한 evaluator를 더해 `--experiment quality`로 실행합니다.

## 빠른 시작

```bash
cd review-item-processor
uv sync --extra evals

# 1) 세트 생성
uv run --extra evals python evals/ko/examples/generate_suite.py --with-image-variants   # D1 + D4
uv run --extra evals python evals/ko/corpus/d5_mixed_document.py                       # D5 문서 생성
bash evals/ko/corpus/fetch_external.sh                                                 # D2/D3 다운로드(law.go.kr)
uv run --extra evals python evals/ko/corpus/generate_corpus_suite.py                   # D2/D3/D5 세트
uv run --extra evals python evals/ko/corpus/verify_corpus.py                           # fixture 검증

# 2) 실행 (Bedrock 자격 증명 필요, 기본 모델은 agent.py의 DEFAULT_DOCUMENT_MODEL_ID)
export AWS_REGION=us-west-2 BEDROCK_REGION=us-west-2 ENABLE_CITATIONS=true
uv run --extra evals python evals/scripts/run_eval.py \
  --suite ko/examples/korean_examples_suite.json \
  --experiment quality --output results/ko_quality_run1.json
```

`--suite` 경로는 `evals/` 디렉터리 기준입니다. `--filter KO-D2`처럼 케이스 이름 부분 문자열로 일부만 실행할 수 있습니다(여러 번 지정 가능). 결과 JSON에는 케이스별 에이전트 출력(`explanation`, `shortExplanation`, `extractedText`, `pageNumber`, `reviewMeta`)과 evaluator별 점수·세부 사유, 집계 지표(`aggregated_metrics`)가 저장됩니다. LLM-as-judge 호출을 생략하려면 `--no-llm-judge`를 붙입니다.

D4 fixture(래스터화 PDF·PNG, 약 9 MB)와 D2/D3 fixture(law.go.kr 첨부 파일)는 저장소에 넣지 않고 위 명령으로 재생성·다운로드합니다. `verify_corpus.py`가 세 세트가 참조하는 모든 파일의 존재, pypdf·pdfium 열림, 매니페스트 sha256·쪽수 일치, 스캔 변형의 텍스트 레이어 부재를 확인합니다(실패 시 종료 코드 1).

## 문서 코퍼스와 세트

| 코퍼스 | 문서 | 노리는 것 | 세트 파일 | 케이스 |
| --- | --- | --- | --- | --- |
| D1 | `examples/ko`의 심사 대상 PDF 3건(Noto Sans KR 임베딩, 텍스트 레이어 정상) | 기준선 | `examples/korean_examples_suite.json` | 40 (fail 15 / pass 22 / 근거 부족 3) |
| D4 | D1 심사 대상을 300 dpi로 래스터화한 스캔 PDF(텍스트 레이어 없음)와 쪽별 PNG | 스캔 PDF 경로와 이미지 경로의 한국어 판독·판정 | `examples/korean_examples_image_suite.json` | 30 (IMGPDF 15 / PNG 15, fail 항목만) |
| D2 | 「사업장 위험성평가에 관한 지침」 고시 전문 PDF 18쪽(law.go.kr 첨부). 텍스트 레이어의 띄어쓰기가 대부분 소실 | 띄어쓰기 없는 텍스트에서의 인용 정합·설명 가독성 | `corpus/corpus_suite.json` | 6 (pass 3 / fail 2 / 근거 부족 1) |
| D3 | 같은 고시의 별표·별지 서식 4건, HWP 서식의 law.go.kr PDF 변환본 | 한국 공공문서의 실제 입력 경로(서식 구조 점검) | `corpus/corpus_suite.json` | 9 (pass 5 / fail 3 / 근거 부족 1) |
| D5 | 생성한 한·영 혼합 IT 운영·재해복구(DR) 계획서: RTO/RPO, 99.9 %, ≤ 300 ms, ①②③, 「법령」, 제품명 | 토큰화·인용 경계 | `corpus/corpus_suite.json` | 10 (pass 6 / fail 3 / 근거 부족 1) |
| D6 | 185쪽 장문 PDF | 분할 추출의 시간·비용 | — | 계획상 선택 항목, 미구성 |

합계 95 케이스. D3는 계획서의 "HWP→PDF 변환 도구" 전제 대신 law.go.kr가 HWP 서식과 함께 배포하는 PDF 변환본을 사용했습니다(변환 도구 불필요, 실제 사용자가 받는 파일과 동일).

### 케이스 구성 원칙

- 케이스 1건 = 체크리스트 항목 1개(`check_name` / `check_description`) × 문서. D1·D4는 `.claude/skills/add-example/scripts/korean_examples/` 모듈의 체크리스트 정의와 결함 목록(`DEFECTS`)에서 **생성**되고, D5는 `corpus/d5_mixed_document.py`의 `ITEMS`에서 생성되므로 정답이 한 곳에만 있습니다. D2·D3의 정답은 `corpus/generate_corpus_suite.py`에 조문·쪽 근거(`truth_note`)와 함께 적혀 있습니다.
- **fail**: 문서에 의도적으로 넣은 결함(정답표는 `examples/ko/README.md`, D5는 모듈 `DEFECTS`) 또는 문서에 없는 사항을 묻는 항목. UC002 항목 4(제외 면적 확인)와 항목 5(용적률 재계산)는 같은 결함(지하층 포함 용적률)을 입력·결과 양쪽에서 보는 것이라 둘 다 fail입니다.
- **pass**: 문서가 충족하는 항목.
- **근거 부족**: 문서 밖의 정보가 필요한 점검(홈페이지 게재 여부, 최신 개정본 여부 등). 프롬프트 규약대로 `result: fail`, `confidence ≤ 0.49`, `extractedText: ""`가 기대값이며 `expected_output.insufficient_evidence: true`로 표시됩니다.
- 판정이 갈릴 수 있는 항목('해당 시' 항목 등)은 `generate_suite.py`의 `AMBIGUOUS`에 사유와 함께 제외되어 있습니다.
- 문서는 복사하지 않고 케이스별 `fixtures_dir`로 참조합니다. 각 매니페스트(`fixtures_manifest.json`, `image_fixtures_manifest.json`, `corpus_manifest.json`)에 sha256·크기·쪽수가 기록되어 결과를 비교할 때 같은 문서였는지 확인할 수 있습니다. 래스터화 결과는 pdfium·Pillow 버전에 따라 바이트가 달라질 수 있으므로, 재생성 후 `generate_suite.py --with-image-variants`로 매니페스트도 다시 만듭니다.
- D4 IMGPDF 케이스에는 `citation_reference_pdf`(텍스트 레이어가 있는 원본)가 붙어 있어 인용 정합 평가가 **OCR 정합**(모델이 이미지에서 읽어 인용한 문장이 원본에 있는가)으로 바뀝니다. PNG 케이스는 이미지 경로라 인용이 없어 평가 대상에서 제외됩니다.

## 측정 항목

`--experiment quality`는 기존 정확도·확신도 보정 evaluator에 다음을 더합니다. 모두 `evals/quality_evaluators.py`에 있고 언어 매개변수를 받으므로 ja/en 세트에도 쓸 수 있습니다.

| Evaluator | 측정 내용 | 통과 기준(케이스) | 세트 수용 기준 |
| --- | --- | --- | --- |
| `OutputLanguageEvaluator(language="ko")` | `explanation`·`shortExplanation`의 문자 종류 집계. 가나(일본어) 혼입은 즉시 실패, 영문 약어·URL·단위는 중립 처리 | 한글 비율 ≥ 70%, 가나 0 | 준수율 100% |
| `JsonParseEvaluator` | 에이전트가 JSON 파싱 폴백(`Failed to analyze JSON parse` 등)을 반환했는지 | 폴백 아님 | 100% |
| `ShortExplanationLengthEvaluator(max_chars=80)` | 프롬프트의 "80자 이내" 규칙 | 1~80자 | 80자 초과 ≤ 5%, 분포(중앙값·p95) 보고 |
| `CitationFidelityEvaluator` | `extractedText`의 각 인용이 PDF 텍스트 레이어(pypdf)에 실제로 있는지. 문자·숫자만 남기는 정규화 후 비교하고, 에이전트가 말한 `pageNumber`에서 찾으면 `page_match`, 다른 쪽이면 `other_page`, 없으면 `mismatch`. 불일치 인용에는 토큰 포함율(`mismatch_coverage`: 인용의 단어·숫자 중 문서에 있는 비율)을 함께 기록해 재구성(≈1.0)과 환각(낮음)을 구분. 스캔 fixture는 `citation_reference_pdf`와 비교(OCR 정합), 참조가 없으면 평가 제외. 이미지 심사는 해당 없음 | `mismatch` 0 | mismatch 0건 또는 건별 원인 문서화 |
| `InsufficientEvidenceEvaluator` | 근거 부족 케이스의 규약 준수(fail / ≤ 0.49 / 빈 extractedText)와 사용된 문구 수집 | 3항목 모두 충족 | 규약 100%, 문구 2종 이하 |
| `OutputEvaluator`(LLM-as-judge) | 설명의 명확성·근거·완결성·언어·관련성 | — | 평균 점수 보고 |

집계 결과는 결과 JSON의 `aggregated_metrics.Quality`에, 요약은 실행 끝의 `OUTPUT QUALITY` 절에 출력됩니다. 정확도 지표(재현율·정밀도·고확신 오판)는 기존과 같이 `AccuracyEvaluator` / `ConfidenceCalibrationEvaluator` 절에 나옵니다.

## 결과 해석 시 주의

- 모델 출력은 실행마다 달라집니다. 수용 기준은 **같은 세트를 3회 실행**한 결과로 판정하고, 1회 측정값을 "항상"으로 적지 않습니다.
- `CitationFidelityEvaluator`의 `other_page`는 인용은 정확하지만 `pageNumber`가 틀린 경우입니다. `mismatch`는 정규화 후에도 문서에 없는 문자열이므로 환각 또는 패러프레이즈를 뜻하며, `mismatch_coverage`로 둘을 가릅니다.
- 스캔 PDF(IMGPDF)에서 모델이 돌려주는 `extractedText`는 텍스트 레이어에서 잘라낸 인용이 아니라 이미지에서 읽어 **재구성한 문장**입니다(표의 여러 칸을 " / "로 이어 붙이는 식). 사전 측정에서 포함율 0.87의 불일치 1건이 그 예입니다. 보고서에서는 텍스트 레이어 인용과 분리해(`citation.ocr`) 해석합니다.
- 근거 부족 문구가 3종 이상이면 프롬프트에 한국어 표준 문구("근거 불충분")를 지시하는 변경을 검토합니다.
- D1·D4·D5는 문서를 만들 때 설계한 결함을 그대로 채점하므로 "최소 기능 확인"입니다. D2·D3가 실물 공공문서이지만 범위가 한 고시에 한정되므로, 일반화 여부는 다른 기관·업종 문서로 보완해야 말할 수 있습니다.

## 파일

```
evals/ko/
├── README.md
├── examples/
│   ├── generate_suite.py                 # D1(+D4) 세트 생성기 (정답 정의 포함)
│   ├── korean_examples_suite.json        # D1 40 케이스
│   ├── fixtures_manifest.json            # D1 PDF sha256
│   ├── korean_examples_image_suite.json  # D4 30 케이스 (--with-image-variants)
│   ├── image_fixtures_manifest.json      # D4 파일 sha256 (로컬 생성본 기준)
│   └── fixtures/image/<유스케이스>/       # D4 산출물 (gitignore, rasterize_pdf.py로 생성)
└── corpus/
    ├── rasterize_pdf.py                  # D4: 텍스트 PDF → 스캔 PDF(텍스트 레이어 없음) + 쪽별 PNG
    ├── d5_mixed_document.py              # D5 문서 생성기 + 체크리스트 항목·결함 정의
    ├── generate_corpus_suite.py          # D2/D3/D5 세트 생성기 (D2/D3 정답 정의 포함)
    ├── corpus_suite.json                 # 25 케이스
    ├── corpus_manifest.json              # D2/D3/D5 파일 sha256
    ├── external_sources.json             # D2/D3 출처(law.go.kr flSeq)·sha256·법적 근거
    ├── fetch_external.sh                 # D2/D3 다운로드 + sha256 검증
    ├── verify_corpus.py                  # fixture 검증 (M4-b 수용 기준)
    ├── fixtures/d5/                      # D5 PDF (커밋됨, 39 KB, 결정적 생성)
    └── external/                         # D2/D3 PDF (gitignore)
```

단위 테스트: `uv run --extra evals --extra dev pytest tests/test_quality_evaluators.py` (Bedrock 호출 없음).
