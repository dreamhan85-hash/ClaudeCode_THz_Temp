# THz-TDS PE Separator Temperature Study

## Project Overview
THz-TDS를 이용한 이차전지 PE 분리막의 온도 의존성 미세구조 변화 분석.
Matched Reference 방식으로 광학 상수 추출 + Bruggeman EMA 기공률 역산.

## Environment
- **Python**: 3.9 (requires `from __future__ import annotations`)
- **CONDA_ENV**: (system python — no conda)
- **Running app**: `python3 -m streamlit run app.py`
- **Running analysis**: `python3 scripts/analyze_pe40_paper.py`

## Key Parameters
- **Sample**: MS-DPS 20B (dry process PE separator) × 2 sheets = 40 μm
- **Spec porosity**: 44%
- **Temperature range**: 20–110 °C (10 °C step)
- **Replicates**: 5 per temperature (S1–S5)
- **Analysis method**: Matched Reference — H(ω) = E_sam(T) / E_ref(T)
- **Window**: rectangular (no window)
- **Frequency range**: 0.2–2.5 THz
- **Best frequencies (auto-selected)**: 0.45, 1.09, 1.63 THz

## Data Locations
```
MeaData/260406_Temp/          ← raw THz data (PE40, 10 temps × 5 reps)
results/paper_260406/         ← CSV tables (optical summary, per-sample n, correlation, EMA)
figures/paper_260406/         ← paper-quality figures (12 figs, PNG+PDF)
Ref_Paper/                    ← reference papers (PDF)
```

## Core Library
```
thztds/                       ← THz-TDS analysis library
├── io.py                     ← data loading (parse_menlo_file, load_measurement_set_with_refs)
├── signal.py                 ← FFT, windowing, peak detection
├── transfer_function.py      ← H(ω), Fresnel, air correction
├── optimization.py           ← Nelder-Mead n/κ extraction
├── optical_properties.py     ← pipeline orchestration
├── noise.py                  ← noise floor detection, SNR analysis
├── phase_correction.py       ← DC phase offset correction
├── filtering.py              ← SVMAF (Spatially Variant Moving Average Filter)
├── thickness.py              ← thickness optimization
├── error_estimation.py       ← confidence intervals, alpha_max
└── types.py                  ← ExtractionConfig, OpticalProperties, NoiseAnalysis, etc.
```

## Automation System (2-Loop Architecture)

### 실험 탐색 루프 (`/experiment`)
측정 데이터 → 문헌 검색 → 방법론 도출 → 분석 → 결과 평가 → 반복.
의미 있는 결과 나오면 사용자 확인 후 논문 루프로 연결.
```
scripts/experiment-loop.sh                    ← 세션 회전 래퍼
.claude/commands/experiment.md                ← 런처 커맨드
.claude/prompts/experiment-orchestrator.md    ← 오케스트레이터
.claude/prompts/experiment-literature.md      ← Literature Scout 에이전트
.claude/prompts/experiment-review.md          ← 리뷰 파이프라인 (L/A/B/C + Judge)
```

### 논문 개선 루프 (`/paper`)
실험 결과 → 초고 생성 → 리뷰 → 개선 반복. 추가 분석 필요 시 실험 루프로 재요청.
```
scripts/paper-loop.sh                        ← 세션 회전 래퍼
.claude/commands/paper.md                    ← 런처 커맨드
.claude/prompts/paper-orchestrator.md        ← 오케스트레이터
.claude/prompts/paper-review.md              ← 리뷰 파이프라인 (G/A/B/C/D + Judge)
.claude/prompts/paper-writer.md              ← 초고 생성/수정 에이전트
```

### 루프 간 연결
- 실험 → 논문: `meaningful` 판정 시 handoff (결과 + 문헌)
- 논문 → 실험: `need_data` 판정 시 부족 분석 명세 전달
- 양방향 순환 가능

### 시스템 자기 개선 (Meta-Improvement)
리뷰 과정에서 도출된 시스템 개선 제안 → 사용자 승인 후 .claude/ 설정에 반영.
페르소나, 지침, 템플릿 등이 프로젝트와 함께 지속적으로 성장.

## Analysis Scripts
```
scripts/
├── analyze_pe40_paper.py             ← paper-quality analysis (main)
├── analyze_pe40_temp.py              ← general analysis
├── predict_temperature.py            ← ML temperature prediction pipeline
├── generate_paper_sna.py             ← SNA paper generator (EN)
├── generate_paper_sna_ko.py          ← SNA paper generator (KO)
├── generate_pe40_paper_report.py     ← DOCX report generator
├── experiment-loop.sh                ← 실험 탐색 루프 래퍼
├── paper-loop.sh                     ← 논문 개선 루프 래퍼
└── train-loop.sh                     ← legacy experiment automation
```

## Research Notes
- Research log rules → see `research/CLAUDE.md`
- Log writing templates, directory structure → see `research-log` skill
- Weekly summary → see `weekly-summary` skill
- 루프 반복 종료 시 연구 노트에 자동 요약 삽입

## Default Language
ko (한국어)
