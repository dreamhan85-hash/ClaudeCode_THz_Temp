---
name: equation-format
description: "논문 수식 번호 체계, where 절 스타일, 참고논문 포맷. Eq.(1)~(N) 별도 라인 표기. 수식을 추가하거나 논문에 방정식을 작성할 때 반드시 이 스킬을 참조할 것. equation, 수식, Eq., formula 키워드에 트리거."
---

# Equation Format — Paper Equation Standards

참고논문: SNA 2023 (Yang & Han), NDT&E 2023 (Han), CS 2018 (Han & Kang)

## 수식 표기 규칙

### 1. 별도 라인 + 우측 번호
```python
def add_equation(doc, eq_text, eq_num):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(eq_text)
    run.italic = True
    run.font.size = Pt(12)
    run2 = p.add_run(f"\t({eq_num})")
    run2.italic = False
    run2.font.size = Pt(12)
```

### 2. where 절
수식 직후 새 문단으로 `where` 시작:
```python
def add_where(doc, text):
    p = doc.add_paragraph(f"where {text}")
    p.paragraph_format.space_before = Pt(2)
```

한국어 버전: `"여기서 {text}"`

### 3. 번호 체계
- 본문: Eq. (1), (2), ..., (N) 연속 번호
- Appendix: 본문 이어서 (N+1), (N+2)... 또는 별도 (A1), (B1)
- 본문 참조: "Eq. (4)" 또는 "Eqs. (2) and (3)"

## 현재 논문 수식 목록

| Eq. | 내용 | 위치 |
|-----|------|------|
| (1) | H(ω) = E_sam(ω,T) / E_ref(ω,T) | 2.3 Optical extraction |
| (2) | n(ω) = 1 + c·Δφ(ω) / (2π·f·d) | 2.3 |
| (3) | α(ω) = −(2/d)·ln|H(ω)| | 2.3 |
| (4) | Bruggeman 2-phase EMA | 2.4 EMA |
| (5) | φ(T) = 1 − (1−φ₀)/(1+β·ΔT) | 3.4 Thermal expansion |
| (6) | Lasso objective: min (1/2N)Σ(T−T̂)² + α·Σ|βⱼ| | 2.5 ML / Appendix B |
| (7) | T̂ = 65.0 + Σ βⱼ·(xⱼ−μⱼ)/σⱼ | 2.5 ML / Appendix B |

## 수식 추가 시 절차
1. 기존 마지막 Eq. 번호 확인
2. 새 수식에 연속 번호 부여
3. 본문 내 모든 참조 업데이트
4. EN/KO 양쪽 동시 반영

## 변수 표기 관례
| 변수 | 의미 | 단위 |
|------|------|------|
| n | 굴절률 | 무차원 |
| κ | 소멸계수 | 무차원 |
| α | 흡수계수 | cm⁻¹ |
| φ | 기공률 (porosity) | % |
| β | 유효 기공 팽창 계수 | /°C |
| d | 시료 두께 | mm 또는 μm |
| f | 주파수 | THz 또는 Hz |
| T | 온도 | °C |
