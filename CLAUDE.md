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
figures/paper_260406/         ← paper-quality figures (10 figs, PNG+PDF)
```

## Core Library
```
thztds/                       ← THz-TDS analysis library
├── io.py                     ← data loading (parse_menlo_file, load_measurement_set_with_refs)
├── signal.py                 ← FFT, windowing, peak detection
├── transfer_function.py      ← H(ω), Fresnel, air correction
├── optimization.py           ← Nelder-Mead n/κ extraction
├── optical_properties.py     ← pipeline orchestration
└── types.py                  ← ExtractionConfig, OpticalProperties
```

## Analysis Scripts
```
scripts/
├── analyze_pe40_paper.py     ← paper-quality analysis (main)
├── analyze_pe40_temp.py      ← general analysis
├── generate_pe40_paper_report.py  ← DOCX report generator
└── train-loop.sh             ← experiment automation loop
```

## Research Notes
- Research log rules → see `research/CLAUDE.md`
- Log writing templates, directory structure → see `research-log` skill
- Weekly summary → see `weekly-summary` skill

## Default Language
ko (한국어)
