#!/usr/bin/env python3
"""
Corpus D5: a Korean document that mixes English terms, acronyms, units and symbols.

The review target is a fictional cloud operations / disaster-recovery (DR) plan of an
IT department: RTO/RPO, SLO percentages, "≤ 300 ms", "①②③", 「법령」 quotation marks,
product names and ISO identifiers all appear inside Korean sentences. It exercises
tokenisation and citation boundaries that the all-Korean examples (D1) do not.

Three defects are planted (DEFECTS); ITEMS defines the checklist items used as cases and
how each one is expected to come out. The PDF is rendered with the same deterministic
builder as examples/ko (Noto Sans KR, no timestamps), so regenerating it is byte-stable.

Usage (from review-item-processor/):
    uv run --extra evals python evals/ko/corpus/d5_mixed_document.py            # -> fixtures/d5/<FILENAME>
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent.parent.parent
GENERATOR_DIR = REPO_ROOT / ".claude" / "skills" / "add-example" / "scripts"
OUT_DIR = HERE / "fixtures" / "d5"

FILENAME = "클라우드_운영_및_재해복구_계획서_가온누리.pdf"
TAGS = ["it-operations"]

# Planted defects (1-based index, referenced from ITEMS)
DEFECTS = [
    "RPO 목표는 1시간이지만 운영 DB 스냅샷의 DR 리전 복제는 1일 1회(24시간 주기)로 기재되어 복제 주기가 RPO를 초과한다.",
    "DR 전환 모의훈련 주기가 연 1회로, 점검 기준(반기 1회 이상)에 미달한다.",
    "DR 리전이 해외(Asia Pacific (Tokyo))여서 개인정보가 국외로 이전되는데 「개인정보 보호법」 제28조의8에 따른 근거(동의 또는 고지)가 기재되어 있지 않다.",
]

# (item no, check_name, check_description, kind, defect index or None)
ITEMS = [
    ("1", "RTO/RPO 목표 정의",
     "복구시간목표(RTO)와 복구시점목표(RPO)가 각각 수치(시간 단위)로 정의되어 있는가.", "pass", None),
    ("2", "RPO와 DR 데이터 복제 주기의 정합성",
     "RPO 목표와 DR 리전으로의 데이터 복제 주기가 정합하는가(복제 주기 ≤ RPO). 운영 DB와 객체 스토리지 각각에 대해 확인한다.", "fail", 1),
    ("3", "가용성 목표(SLA) 수치",
     "서비스 가용성 목표가 백분율(%)로 명시되어 있고, 그에 상응하는 허용 다운타임이 함께 기재되어 있는가.", "pass", None),
    ("4", "DR 모의훈련 주기",
     "DR 전환 모의훈련(Failover Test)을 반기 1회 이상 실시하도록 정하고 있는가.", "fail", 2),
    ("5", "저장 데이터 암호화 강도",
     "저장 데이터(Data at Rest) 암호화에 AES-256 이상의 알고리즘과 키 관리 방식(KMS 등)이 기재되어 있는가.", "pass", None),
    ("6", "개인정보 국외 이전 근거",
     "개인정보가 국외(해외 리전 등)에 저장·이전되는 경우, 그 사실과 「개인정보 보호법」 제28조의8에 따른 근거(정보주체 동의 또는 고지 등)가 기재되어 있는가.", "fail", 3),
    ("7", "정보보호 인증 현황",
     "ISO/IEC 27001 또는 ISMS-P 등 정보보호 인증의 보유 현황과 유지 계획이 기재되어 있는가.", "pass", None),
    ("8", "모니터링 경보 임계치",
     "CPU 사용률, 오류율 등 핵심 지표에 대한 경보(Alarm) 임계치가 수치로 정의되어 있는가.", "pass", None),
    ("9", "변경관리 절차",
     "변경자문위원회(CAB) 등 정기 변경관리 절차와 긴급 변경의 처리 방식이 기재되어 있는가.", "pass", None),
]

# Needs information the document cannot contain -> insufficient-evidence protocol.
INSUFFICIENT = [
    ("ISO/IEC 27001 인증서 유효기간",
     "문서에 기재된 ISO/IEC 27001 인증이 현재 유효한지 인증서의 유효기간(발급일·만료일)과 인증기관을 확인한다."),
]

DOC = {
    "title": "「가온누리 통합예약시스템」 클라우드 운영 및 재해복구(DR) 계획서",
    "subtitle": "주식회사 가온누리투어 정보시스템팀 · 문서번호 IT-OPS-2025-07 · v1.2 (2025-03-14) · 대외비",
    "header_label": "가온누리투어 정보시스템팀 — 클라우드 운영 및 DR 계획서 v1.2",
    "footer": "본 문서는 RAPID 평가용으로 작성된 가상 문서입니다. 등장하는 회사·시스템·수치·일자는 모두 허구이며 실제 조직과 무관합니다.",
    "blocks": [
        ("h2", "1. 개요"),
        ("p", "본 계획서는 「가온누리 통합예약시스템」(이하 \"시스템\")을 퍼블릭 클라우드에서 운영하기 위한 서비스 수준 목표(SLO; Service Level Objective), "
              "재해복구(DR; Disaster Recovery) 전략 및 보안·개인정보 보호 조치를 정한다. 적용 범위는 예약 API, 결제 연동 모듈, 고객 포털(Web/Mobile) 및 운영 데이터베이스이다."),
        ("bullets", [
            "① 운영 리전: Asia Pacific (Seoul)",
            "② DR 리전: Asia Pacific (Tokyo) — 운영 리전 장애 시 전환 대상",
            "③ 운영 방식: Active-Standby(Warm Standby), 전환은 DNS 가중치 변경으로 수행",
        ]),
        ("h2", "2. 서비스 수준 목표 (SLO/SLA)"),
        ("table", {
            "header": ["지표", "목표", "측정 방법"],
            "widths": [0.24, 0.40, 0.36],
            "rows": [
                ["가용성 (Availability)", "월 99.9% 이상 (허용 다운타임 ≤ 43.8분/월)", "합성 모니터링(Synthetics) 5분 간격 헬스체크"],
                ["응답시간 (Latency)", "p95 ≤ 300 ms, p99 ≤ 800 ms", "로드밸런서 액세스 로그 집계"],
                ["처리량 (Throughput)", "최대 1,200 TPS (성수기 기준)", "부하시험 결과서 LT-2025-02"],
                ["오류율 (Error rate)", "HTTP 5xx ≤ 0.1%", "로드밸런서 메트릭"],
            ],
        }),
        ("h2", "3. 재해복구(DR) 목표 및 전략"),
        ("h3", "3.1 복구 목표"),
        ("table", {
            "header": ["구분", "목표", "비고"],
            "widths": [0.34, 0.18, 0.48],
            "rows": [
                ["RTO (Recovery Time Objective)", "4시간", "재해 선언 시점부터 서비스 재개까지"],
                ["RPO (Recovery Point Objective)", "1시간", "허용 가능한 최대 데이터 손실 범위"],
            ],
        }),
        ("p", "복구 목표는 2024년 11월 사업영향분석(BIA; Business Impact Analysis) 결과에 따라 설정하였으며, 매년 재검토한다."),
        ("h3", "3.2 백업 및 복제 정책"),
        ("bullets", [
            "운영 DB(관리형 PostgreSQL 15): 자동 스냅샷 1일 1회(03:00 KST) 및 트랜잭션 로그 5분 간격 보관으로 운영 리전 내 시점 복구(PITR)를 지원한다.",
            "운영 DB 스냅샷의 DR 리전 복제: 1일 1회(24시간 주기) 교차 리전 복사.",
            "객체 스토리지: 버전 관리(Versioning) 활성화, DR 리전으로 교차 리전 복제(CRR) 실시간 수행.",
            "보존기간: 스냅샷 35일, 월간 아카이브 13개월. 백업 데이터는 저장 시 암호화한다.",
        ]),
        ("h3", "3.3 DR 전환 모의훈련"),
        ("p", "DR 전환 모의훈련(Failover Test)은 연 1회(매년 10월) 실시하고, 결과를 정보보호위원회에 보고한다. "
              "최근 훈련(2024-10-22) 측정값: RTO 3시간 20분, RPO 42분으로 목표를 충족하였다."),
        ("h2", "4. 보안 및 개인정보 보호"),
        ("bullets", [
            "전송 구간 암호화: TLS 1.2 이상(TLS 1.3 권장). 저장 데이터 암호화: AES-256, 고객 관리형 KMS 키 사용, 키는 연 1회 교체한다.",
            "접근통제: 최소권한(Least Privilege) 원칙의 IAM 정책, 운영자 MFA 필수, 특권 세션 로그 1년 보존.",
            "정보보호 인증: ISO/IEC 27001:2022 인증 유지(갱신심사 2025-09 예정), ISMS-P 인증 범위에 본 시스템을 포함한다.",
            "개인정보 보호: 「개인정보 보호법」 제29조 및 「개인정보의 안전성 확보조치 기준」(개인정보보호위원회 고시)에 따라 접근권한 관리, 접속기록 보관(1년 이상) 및 암호화를 적용한다.",
        ]),
        ("h2", "5. 모니터링 및 변경관리"),
        ("bullets", [
            "경보 임계치: CPU 사용률 ≥ 80% 5분 지속, HTTP 5xx 오류율 > 0.5% 1분 지속, DB 여유 스토리지 < 10%.",
            "변경관리: 변경자문위원회(CAB; Change Advisory Board) 주 1회(매주 화요일) 개최. 긴급 변경(Emergency Change)은 선조치 후 48시간 이내 사후 승인.",
            "로그 관리: 애플리케이션·시스템 로그 90일 온라인 보관, 이후 1년 아카이브.",
        ]),
        ("h2", "6. 역할과 책임"),
        ("table", {
            "header": ["역할", "담당", "책임"],
            "widths": [0.22, 0.26, 0.52],
            "rows": [
                ["서비스 책임자", "정보시스템팀장", "SLO 달성 관리, 재해 선언 및 DR 전환 결정"],
                ["DR 담당자", "인프라 파트", "전환 절차 수행, 모의훈련 주관, 복제 상태 점검"],
                ["보안 담당자", "정보보호 파트", "인증 유지, 접근통제 및 암호화 정책 운영"],
            ],
        }),
    ],
}


def build(out_dir: Path = OUT_DIR) -> Path:
    sys.path.insert(0, str(GENERATOR_DIR))
    import create_korean_example_pdfs as gen  # noqa: E402  (reportlab font setup + build_pdf)

    gen.register_fonts(None)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / FILENAME
    gen.build_pdf(DOC, out)
    return out


if __name__ == "__main__":
    path = build()
    print(f"wrote {path.relative_to(REPO_ROOT)} ({path.stat().st_size // 1024} KB)")
