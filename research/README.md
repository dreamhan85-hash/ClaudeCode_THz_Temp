# Research — THz-TDS PE Separator Temperature Study

## Current Research Status

| Topic | Status | Recent Progress |
|-------|--------|-----------------|
| optical_properties | Active | 2-phase Bruggeman EMA, f_air 44→59%, n_offset=+0.146 |
| signal_processing | Complete | Matched Ref, rectangular window, 0.2–2.5 THz, SNR 52 dB |
| thermal_analysis | Active | T_onset=55.2°C (two-regime), β=3.50e-03/°C |
| statistics | **In Progress** | ANOVA η²=0.74, FDR/bootstrap/AIC 미적용 → config_modify 판정 |

## Recent Key Decisions

- 2026-04-07: EMA 3상 → **2상** 모델 전환 (Δf_air < 0.1%p, 3상 분리 불가)
- 2026-04-07: S4/S5 글로벌 offset 보정 (Δn=0.106, σ 0.051→0.014)
- 2026-04-07: Multi-agent review → Judge **config_modify** 판정
- 2026-04-07: α 음수값 클리핑, A4 논문용 폰트/범례 개선
- 2026-04-06: Matched Reference only, sample-specific features only in correlation

## Open Questions (from Judge config_modify)

1. FDR (Benjamini-Hochberg) 다중비교 보정 미적용
2. Bootstrap CI (B=1000) 미산출
3. n_offset 불확도 전파 미완성
4. α 클리핑 범위, S4/S5 근거, 저주파 배제 기준 미문서화
5. Piecewise fit AIC/BIC 비교 미수행
6. 측정 온도 불확도 ±1-2°C, run-order effect 미기재

## Log Structure

```
logs/
├── YYYY-MM-DD/log.md         ← daily log
│   └── {experiment_title}/   ← automated experiment sessions
└── archive/                  ← weekly archive
topics/                       ← topic-specific cumulative notes
related_work/                 ← related papers/techniques
```
