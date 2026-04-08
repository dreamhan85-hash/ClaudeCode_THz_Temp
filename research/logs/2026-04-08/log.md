# Research Log — 2026-04-08

## /analyze 실행 결과

### 스크립트
- `scripts/analyze_pe40_paper.py` + `scripts/predict_temperature.py`
- `scripts/generate_paper_sna.py` (EN) + `scripts/generate_paper_sna_ko.py` (KO)

### 주요 수치
| 항목 | 값 |
|------|-----|
| n@0.45THz (20°C) | 1.4282 ± 0.018 |
| n@0.45THz (100°C) | 1.3515 ± 0.011 |
| T_onset | 55.2°C (T_break=51.8, RSS=3.0e-4) |
| Porosity (20→110°C) | 44.0 → 55.7% |
| β | 3.50e-03/°C |
| ANOVA η² (0.45THz) | 0.74 (p=2.84e-9) |
| Lasso LOTO-CV | R²=0.955, MAE=5.1°C |

### Figure 품질 체크리스트 (11 figures)
- **PASS**: Fig.1-5, 8-10, A1 (9/11)
- **MINOR**: Fig.6 ("large effect" 텍스트 작음), Fig.7 (|H(ω)| spike)

### Multi-Agent Review 판정: `improve`
- Fig.6: 텍스트 폰트 10pt 상향
- Fig.7: y축 0.85~1.05 클리핑

### 논문 상태
- EN: ~6135 words, 29 refs, Fig.1-10 + Scheme 1 + A1, Supplementary S1-S3
- KO: ~5100 words (동일 구조)
- 5회 자체 리뷰 + 7명 파이프라인 리뷰 완료
- Judge 판정: go (Supplementary 완성 후 투고)

### 다음 단계
- Fig.6, Fig.7 minor 수정 후 재생성
- Graphical Abstract 이미지 제작
- Cover letter 작성
- 저자/소속 기입
