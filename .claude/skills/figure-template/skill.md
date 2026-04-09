---
name: figure-template
description: "THz-TDS 논문 Figure 생성 규칙. matplotlib rcParams, 색상 스키마, 폰트 크기, 축 범위, 범례 배치 등 모든 그래프 품질 기준. Figure를 생성하거나 수정할 때 반드시 이 스킬을 참조할 것."
---

# Figure Template — THz-TDS Paper Graph Standards

## matplotlib rcParams
```python
plt.rcParams.update({
    "font.family": "Arial",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 11,
    "axes.linewidth": 0.6,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "xtick.major.width": 0.5,
    "ytick.major.width": 0.5,
    "xtick.direction": "in",
    "ytick.direction": "in",
    "lines.linewidth": 0.9,
    "legend.fontsize": 8,
    "savefig.dpi": 600,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.08,
})
```

## Figure 크기
- Single column: `SINGLE_COL_W = 8.5 cm`, aspect 4:3
- Double column: `DOUBLE_COL_W = 17.0 cm`, aspect 4:3
- DPI: 600 (PNG + PDF 동시 출력)

## 온도 컬러맵
10개 온도 (20–110°C): blue→red 연속 컬러맵
```python
TEMP_COLORS = ["#3B4CC0", "#5A7BC6", "#7AAAD0", "#9DC8D9", "#BDDDDD",
               "#E8C8A0", "#F0A672", "#E87B52", "#D44E3D", "#B40426"]
```

## 샘플 마커
```python
SAMPLE_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
SAMPLE_MARKERS = ["o", "s", "^", "D", "v"]
```

## 축 범위 기준
| 물리량 | 범위 | 근거 |
|--------|------|------|
| n (굴절률) | 1.2–1.5 또는 데이터 맞춤 | PE separator 범위 |
| α (흡수계수) | 0–30 cm⁻¹ | clipping 후 |
| Porosity | 30–75% | 측정 범위 + 여유 |
| Temperature | 15–115°C | 측정 범위 + 여유 |

## 범례 배치 규칙
1. 데이터와 겹치지 않는 빈 공간에 배치
2. `framealpha=0.9` 배경 투명도
3. 다수 항목(>4개) → `ncol=2` 또는 `ncol=3`
4. 공유 범례 → `fig.legend()` + `bbox_to_anchor`

## 주석(annotation) 규칙
1. 화살표: `arrowstyle="->"`, `lw=0.6`
2. 텍스트 상자: `bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8)`
3. 데이터를 가리지 않는 위치에 배치
4. T_onset 등 핵심 주석은 그래프 빈 공간에 배치
