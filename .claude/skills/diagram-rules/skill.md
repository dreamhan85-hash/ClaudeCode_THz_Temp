---
name: diagram-rules
description: "Schematic test setup, ML flowchart 등 다이어그램 생성 규칙. 직선+직각만 사용, 곡선 금지, 직사각형 박스, 제조사명 하단 표기. 다이어그램을 그리거나 수정할 때 반드시 이 스킬을 참조할 것. schematic, flowchart, block diagram 키워드에 트리거."
---

# Diagram Rules — Rectilinear Block Diagram Standards

참고논문 기준: SNA 2023 (Yang & Han), NDT&E 2023 (Han), Polymers 2023 (Hwang et al.)

## 핵심 규칙 (위반 금지)

1. **직선 + 직각만** — 곡선(arc, curve, spline) 절대 금지
2. **직사각형 박스** — 과도한 둥근 모서리 금지 (`round,pad=0.08` 이하)
3. **matplotlib만 사용** — 외부 도구(draw.io, tikz) 사용 안 함

## 박스 스타일
```python
from matplotlib.patches import Rectangle

def rect_box(ax, cx, cy, w, h, text, sublabel, fc, tc="white", fs=8.5):
    ax.add_patch(Rectangle((cx-w/2, cy-h/2), w, h, fc=fc, ec="black", lw=1.0))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, fontweight="bold", color=tc)
    if sublabel:
        ax.text(cx, cy-h/2-0.2, sublabel, ha="center", va="top",
                fontsize=5.5, color="#444", style="italic")
```

## 색상 체계
| 구성 요소 | 색상 | 코드 |
|----------|------|------|
| 레이저/전자장치 | 파랑 | `#4472C4` |
| THz 컴포넌트 | 주황 | `#ED7D31` |
| 시료/홀더 | 녹색 | `#70AD47` |
| 딜레이/광학 | 노랑 | `#FFC000` |
| 온도 제어 | 보라 | `#7030A0` |
| PC/DAQ | 회색 | `#D9D9D9` |

## 연결선 스타일
| 신호 유형 | 선 스타일 | 색상 | lw |
|----------|----------|------|-----|
| Optical Fiber | 점선 `":"` | `#808080` | 1.0 |
| THz Beam | 실선 `"-"` | `#ED7D31` | 2.0 |
| Control/Signal | 점선 `":"` | `#7030A0` | 0.8 |

## 화살표
```python
# 직선 화살표만
ax.plot([x1, x2], [y, y], ls="-", color=color, lw=lw)  # 수평
ax.plot([x, x], [y1, y2], ls="-", color=color, lw=lw)  # 수직
ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(arrowstyle="-|>", lw=lw, color=color))
```

## 라벨 배치
- **Generating Pulse**: 레이저→Emitter 연결 상단
- **Gating Pulse**: Delay→Detector 연결 하단
- **THz wave**: Emitter→Sample 연결 옆
- **제조사명**: 각 박스 하단 이탤릭 소형 텍스트

## Flowchart (위→아래)
- 입력(상단, 파랑) → 처리(주황) → 모델(녹색) → 결과(빨강)
- 분기: 수평선으로 분기 후 수직 하강
- 합류: 수직 상승 후 수평선으로 합류
- 병렬 박스: 같은 y좌표에 수평 배치

## 범례
그래프 하단에 선 스타일 범례 포함:
```
---- Optical Fiber    ━━ THz Beam    .... Control
```
