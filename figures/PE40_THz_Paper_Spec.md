# PE40 THz-TDS 온도 의존성 논문 — 분석 스크립트 생성 지침서

## 문서 목적

이 문서는 Claude Code에서 `scripts/analyze_pe40_paper.py` 스크립트를 생성하기 위한 **완전한 사양서**입니다.
PE20 분리막 2장 겹침(40 μm) 시료의 온도별 THz-TDS 측정 데이터를 분석하여,
논문용 그래프(Figure)와 도표(Table)를 생성합니다.

---

## 1. 연구 배경 및 논문 핵심 논지

### 배경
- 이차전지 PE 분리막은 기공 구조로 리튬 이온 수송을 "적절히 제한"하도록 설계됨
- 기존 연구는 130°C 이상의 셧다운(기공 폐쇄) 메커니즘에 집중
- 상온~셧다운 사이 "중간 영역"에서의 미세구조 변화는 거의 보고되지 않음

### 핵심 발견
- 40°C부터 유효 굴절률 감소 시작 → 열팽창에 의한 기공률 증가
- 50°C 이후 plateau → 네트워크 연화 또는 기계적 평형 도달
- 설계 의도보다 빠른 시점에 기공 구조 변화 → 비균일 이온 플럭스 위험

### 논문 핵심 주장
1. THz-TDS로 PE 분리막의 온도별 미세구조 변화를 비파괴적으로 검출 (최초)
2. 40°C에서 onset, 50°C 이후 plateau 확인 → EMA 모델로 기공률 역산
3. 급속 충전 시 도달 가능한 온도(40-60°C)에서 이미 구조 변화가 시작됨
4. 후속 연구(실시간 충방전 중 THz 모니터링)를 위한 기초 데이터 확립

---

## 2. 데이터 소스

### 측정 데이터 위치
```
MeaData/260406_Temp/
├── Ref_20.txt ~ Ref_110.txt          # 온도별 레퍼런스 (10°C 간격)
├── PE40_20-1.txt ~ PE40_110-5.txt    # 온도별 시료 (5회 반복)
└── Ref_60_return.txt ~ Ref_110_return.txt  # 드리프트 확인용 (참고만)
```

### 분석 결과 CSV (이미 생성됨, 재사용 가능)
```
results/260406_Temp/pe40_summary_stats.csv
results/260406_Temp/pe40_optical_properties.csv
```

### DSC 데이터 (수동 입력)
```python
DSC_PE20 = {
    "Tm_cycle1": 139.37,      # °C, 용융 피크
    "Tm_cycle2": 134.72,      # °C
    "dH_cycle1": 198.6543,    # J/g, 용융 엔탈피
    "dH_cycle2": 132.2636,    # J/g
    "dH_100pct": 293.0,       # J/g, 100% 결정 PE 기준값
    "crystallinity_cycle1": 198.6543 / 293.0,  # = 0.678 (67.8%)
}
```

### 핵심 파라미터
```python
THICKNESS_MM = 0.04           # 40 μm (PE20 × 2장)
TEMPS = [20, 30, 40, 50, 60, 70, 80, 90, 100, 110]
N_REPLICATES = 5              # S1-S5
FREQ_TARGETS = [0.5, 1.0, 1.5]  # THz, 주요 분석 주파수
FREQ_RANGE = (0.3, 2.0)      # THz, 유효 스펙트럼 범위
```

---

## 3. 분석 방법론

### 3.1 Matched Reference 방식
- 전달함수: H(ω) = E_sam(T) / E_ref(T)
- 각 온도의 Ref와 해당 온도의 Sample만 비교
- 공기 경로의 온도 효과 자동 상쇄 → 시료 고유 물성만 추출

### 3.2 EMA (Effective Medium Approximation) 기공률 역산
- 3상 모델: 결정 PE + 비정질 PE + 공기(기공)
- 입력: DSC 결정화도(67.8%), 벌크 PE 굴절률, 측정된 n_eff(T)
- Bruggeman EMA로 f_air(T) 역산

```python
# Bruggeman EMA: 3상
# f_cryst * (eps_cryst - eps_eff)/(eps_cryst + 2*eps_eff)
# + f_amorph * (eps_amorph - eps_eff)/(eps_amorph + 2*eps_eff)
# + f_air * (eps_air - eps_eff)/(eps_air + 2*eps_eff) = 0
#
# 여기서:
#   n_PE_cryst = 1.53    (결정 PE, 문헌값)
#   n_PE_amorph = 1.49   (비정질 PE, 문헌값)
#   n_air = 1.0
#   eps = n^2 (비자성 근사)
#   f_cryst + f_amorph + f_air = 1
#   f_cryst / (f_cryst + f_amorph) = crystallinity = 0.678 (DSC)
#
# 실온(20°C)에서 n_eff 측정값으로 초기 f_air 결정
# 각 온도에서 n_eff(T)로 f_air(T) 역산
```

### 3.3 Two-regime fitting (전이 온도 결정)
- n(T) 데이터를 piecewise linear fitting
- 두 직선의 교점 = 전이 온도 T_transition
- 방법: scipy.optimize로 breakpoint 최적화

### 3.4 열팽창 모델
```python
# 선형 열팽창 모델:
# f_air(T) = 1 - (1 - f_air_0) * (1 / (1 + beta * (T - T_ref)))
# beta = 체적 열팽창계수 (fitting parameter)
# T_ref = 20°C
```

---

## 4. Figure 사양 (총 8개)

### 공통 스타일
```python
# Figure 크기 및 스타일
CM = 1 / 2.54
SINGLE_COL_W = 8.5 * CM    # 단일 컬럼 (journal 기준)
DOUBLE_COL_W = 17.0 * CM   # 더블 컬럼
FIG_H = 6.5 * CM           # 기본 높이
DPI = 600

# 폰트
plt.rcParams.update({
    "font.family": "Arial",
    "font.size": 8,
    "axes.labelsize": 9,
    "axes.titlesize": 9,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 7,
    "lines.linewidth": 0.8,
    "axes.linewidth": 0.5,
    "xtick.major.width": 0.4,
    "ytick.major.width": 0.4,
})

# 온도 색상 (10단계, 파랑→빨강)
TEMP_COLORS = [
    "#3B4CC0", "#5A7BC6", "#7AAAD0", "#9DC8D9", "#BDDDDD",
    "#E8C8A0", "#F0A672", "#E87B52", "#D44E3D", "#B40426",
]

# 샘플별 색상/마커 (S1-S5)
SAMPLE_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
SAMPLE_MARKERS = ["o", "s", "^", "D", "v"]

# y축 자동 최적화: 데이터 범위 + margin, 빈 영역 제외
```

---

### Fig. 1: 시간 영역 파형 — 피크 영역 확대

| 항목 | 사양 |
|------|------|
| **목적** | 온도 증가에 따른 신호 감쇠와 시간 지연을 시각적으로 증명 |
| **크기** | DOUBLE_COL_W × (FIG_H × 0.8), 2행 5열 subplot |
| **x축** | `Time (ps)`, 범위: -1.5 ~ 2.0 ps (Ref 피크 기준 정렬) |
| **y축** | `Amplitude (a.u.)`, auto_ylim (데이터 범위에 맞춤) |
| **내용** | 각 subplot = 하나의 온도. 검정선: Ref(T), 컬러선: S1-S5(투명도 0.7) |
| **subplot 제목** | `20 °C`, `30 °C`, ... `110 °C` |
| **핵심** | Ref 최대 피크를 t=0으로 정렬. 시료 신호의 지연과 감쇠가 한눈에 보여야 함 |
| **저장** | `fig01_time_domain_zoom.png`, `.pdf` |

---

### Fig. 2: 피크 상세 — 전 온도 오버레이

| 항목 | 사양 |
|------|------|
| **목적** | 모든 온도의 신호를 하나의 그래프에 겹쳐서 감쇠/지연 경향 직관적 확인 |
| **크기** | DOUBLE_COL_W × FIG_H, 1행 2열 subplot |
| **좌측 (Positive peak)** | x: -0.3 ~ 0.5 ps, 모든 온도 S1만 + 20°C Ref(검정) |
| **우측 (Negative peak)** | x: neg_peak ± 0.3 ps |
| **y축** | `Amplitude (a.u.)`, auto_ylim |
| **색상** | TEMP_COLORS (20°C=파랑, 110°C=빨강) |
| **colorbar** | 오른쪽에 온도 colorbar (20-110°C) |
| **저장** | `fig02_peak_detail.png`, `.pdf` |

---

### Fig. 3: n(T) — 샘플별 + EMA 모델 (★ 논문 핵심 그래프)

| 항목 | 사양 |
|------|------|
| **목적** | 온도별 굴절률 변화 + 샘플 간 변동 + EMA 기공률 모델 비교 |
| **크기** | SINGLE_COL_W × FIG_H |
| **x축** | `Temperature (°C)`, 범위: 15 ~ 115 |
| **y축 (좌)** | `Refractive index, n @ 1.0 THz` |
| **y축 (우, twin)** | `Effective porosity, f_air (%)` — EMA 역산값 |
| **데이터** | S1-S5 개별 점(SAMPLE_COLORS, 작은 마커), Mean ± σ(검정 실선 + 회색 밴드) |
| **EMA 모델** | 빨간 파선: 열팽창 모델 fitting 곡선 |
| **전이 온도** | 수직 파선: T_transition (two-regime fitting 교점), annotation |
| **DSC Tm** | 수직 점선: 139.4°C (그래프 범위 밖이므로 화살표 annotation) |
| **y축 범위** | auto_ylim, 데이터 범위에 맞춤 (빈 영역 제외) |
| **범례** | S1-S5, Mean±σ, EMA model |
| **저장** | `fig03_n_vs_temp_ema.png`, `.pdf` |

---

### Fig. 4: n(f) 스펙트럼 — 온도별

| 항목 | 사양 |
|------|------|
| **목적** | 주파수 의존성 및 온도에 따른 스펙트럼 변화 |
| **크기** | DOUBLE_COL_W × FIG_H, 1행 2열 |
| **좌측: n(f)** | x: 0.3-2.0 THz, y: `Refractive index, n`, 온도별 색상 |
| **우측: α(f)** | x: 0.3-2.0 THz, y: `Absorption coefficient, α (cm⁻¹)`, 온도별 색상 |
| **colorbar** | 공유 colorbar (20-110°C) |
| **스무딩** | n: median_filter(kernel=3), α: median(5) + savgol(21,3) |
| **y축** | auto_ylim |
| **저장** | `fig04_optical_spectra.png`, `.pdf` |

---

### Fig. 5: 시간 지연 vs 온도 — 샘플별

| 항목 | 사양 |
|------|------|
| **목적** | 시간 영역 직접 분석의 온도 민감도, 샘플별 재현성 |
| **크기** | DOUBLE_COL_W × FIG_H, 1행 2열 |
| **좌측: Δt_avg** | x: Temperature (°C), y: `Time delay, Δt (fs)` |
| **우측: P2P ratio** | x: Temperature (°C), y: `Peak-to-peak ratio` |
| **데이터** | S1-S5 개별 선(SAMPLE_COLORS+MARKERS), Mean ± σ(검정) |
| **trend line** | 좌측에 linregress 빨간 파선, R², p-value annotation |
| **y축** | auto_ylim |
| **저장** | `fig05_time_features_vs_temp.png`, `.pdf` |

---

### Fig. 6: EMA 기공률 역산 결과

| 항목 | 사양 |
|------|------|
| **목적** | THz 굴절률에서 역산한 온도별 기공률 — 논문의 차별화 포인트 |
| **크기** | SINGLE_COL_W × FIG_H |
| **x축** | `Temperature (°C)` |
| **y축** | `Effective porosity, f_air (%)` |
| **데이터** | 평균 ± σ (검정 원 + error bar) |
| **모델** | 열팽창 모델 fitting (빨간 파선) |
| **전이 온도** | 수직 파선 + annotation |
| **초기 기공률** | 수평 파선: f_air(20°C) = 설계값, annotation |
| **회색 밴드** | 설계 허용 범위 (있다면) |
| **y축** | auto_ylim |
| **저장** | `fig06_porosity_vs_temp.png`, `.pdf` |

---

### Fig. 7: 유전율 vs 온도

| 항목 | 사양 |
|------|------|
| **목적** | 유전율 관점의 온도 의존성 (전기화학 커뮤니티 친화적 표현) |
| **크기** | DOUBLE_COL_W × FIG_H, 1행 2열 |
| **좌측: ε'(f)** | x: 0.3-2.0 THz, y: `Real permittivity, ε'`, 온도별 색상 |
| **우측: ε'(T) @ 1.0 THz** | x: Temperature, y: `ε' @ 1.0 THz`, 샘플별 + Mean |
| **y축** | auto_ylim |
| **저장** | `fig07_dielectric.png`, `.pdf` |

---

### Fig. 8: 온도 상관 분석 종합 — 히트맵 + 주요 특성

| 항목 | 사양 |
|------|------|
| **목적** | 다양한 특성의 온도 상관성 비교, 최적 온도 지표 도출 |
| **크기** | DOUBLE_COL_W × (FIG_H × 1.3), 1행 2열 |
| **좌측: Heatmap** | 행: 시료 특성(dt_avg, p2p_ratio, rise_time, group_delay, ...), 열: 온도 |
| **우측: R² bar chart** | 수평 바 차트, 상위 10개 특성의 R², p<0.05만 표시, 유의성 * 표기 |
| **색상** | 히트맵: RdYlBu_r, 바: 유의하면 파랑, 비유의하면 회색 |
| **주의** | 시료 고유 특성만 포함 (레퍼런스 절대값 제외) |
| **저장** | `fig08_correlation_summary.png`, `.pdf` |

---

## 5. Table 사양 (총 4개)

### Table 1: 시료 및 측정 조건

| 항목 | 값 |
|------|------|
| Sample | PE20 separator × 2 sheets (total 40 μm) |
| THz system | Menlo Systems ScanControl / Lytera |
| Temperature range | 20–110 °C (10 °C step, 10 temperatures) |
| Replicates | 5 per temperature (50 total measurements) |
| Reference | Matched reference at each temperature |
| Analysis method | H(ω) = E_sam(T) / E_ref(T) |
| DSC crystallinity | 67.8% (Cycle 1, ΔH = 198.65 J/g) |
| DSC Tm | 139.37 °C |

→ 코드에서 생성하지 않고 논문 본문에 직접 작성. CSV로는 출력하지 않음.

---

### Table 2: 온도별 광학 상수 요약

| Column | 형식 | 설명 |
|--------|------|------|
| Temperature (°C) | 정수 | 20, 30, ..., 110 |
| Δt_avg (fs) | mean ± σ | 시간 지연 평균 |
| n @ 0.5 THz | mean ± σ | 굴절률 |
| n @ 1.0 THz | mean ± σ | 굴절률 (핵심) |
| n @ 1.5 THz | mean ± σ | 굴절률 |
| α @ 1.0 THz (cm⁻¹) | mean ± σ | 흡수계수 |
| ε' @ 1.0 THz | mean ± σ | 유전율 실수부 |
| f_air (%) | EMA 역산값 | 유효 기공률 |

→ `table02_optical_summary.csv` 로 저장

---

### Table 3: 샘플별 n @ 1.0 THz

| Column | 형식 |
|--------|------|
| Temperature (°C) | 정수 |
| S1 ~ S5 | 소수점 4자리 |
| Mean | 소수점 4자리 |
| σ | 소수점 4자리 |

→ `table03_per_sample_n.csv` 로 저장

---

### Table 4: 온도 상관 분석 결과

| Column | 형식 | 설명 |
|--------|------|------|
| Rank | 정수 | 상관 순위 |
| Feature | 문자열 | 특성 이름 |
| Domain | 문자열 | 분석 도메인 (시간/엔벨로프/주파수/차이신호) |
| R | ±소수점 3자리 | Pearson 상관계수 |
| R² | 소수점 3자리 | 결정계수 |
| p-value | 과학적 표기 | 유의확률 |
| Slope (/°C) | 과학적 표기 | 온도 기울기 |
| Significance | *, **, *** | p<0.05, 0.01, 0.001 |

→ `table04_correlation_analysis.csv` 로 저장
→ **시료 고유 특성만 포함** (ratio, delay, difference 기반). 레퍼런스 절대값(amp_pos, p2p, env_peak_amp 등) 제외

---

## 6. EMA 모델링 상세

### 6.1 Bruggeman 3상 EMA 구현

```python
from scipy.optimize import brentq

def bruggeman_3phase(f_air, n_cryst, n_amorph, n_air, f_cryst_ratio):
    """
    f_air: 공기(기공) 부피 분율
    n_cryst: 결정 PE 굴절률 (1.53)
    n_amorph: 비정질 PE 굴절률 (1.49)
    n_air: 공기 굴절률 (1.0)
    f_cryst_ratio: PE 골격 중 결정 비율 (0.678 from DSC)
    
    Returns: n_eff (유효 굴절률)
    """
    f_PE = 1 - f_air
    f_c = f_PE * f_cryst_ratio
    f_a = f_PE * (1 - f_cryst_ratio)
    
    eps_c = n_cryst**2
    eps_a = n_amorph**2
    eps_air = n_air**2
    
    def equation(eps_eff):
        return (f_c * (eps_c - eps_eff) / (eps_c + 2*eps_eff) +
                f_a * (eps_a - eps_eff) / (eps_a + 2*eps_eff) +
                f_air * (eps_air - eps_eff) / (eps_air + 2*eps_eff))
    
    eps_eff = brentq(equation, 1.0, eps_c + 1)
    return np.sqrt(eps_eff)
```

### 6.2 역산: n_eff(T) → f_air(T)

```python
def invert_porosity(n_measured, n_cryst=1.53, n_amorph=1.49, crystallinity=0.678):
    """측정된 굴절률에서 기공률 역산"""
    from scipy.optimize import brentq
    
    def objective(f_air):
        return bruggeman_3phase(f_air, n_cryst, n_amorph, 1.0, crystallinity) - n_measured
    
    return brentq(objective, 0.001, 0.999)
```

### 6.3 열팽창 모델 fitting

```python
def thermal_expansion_model(T, f_air_0, beta):
    """
    T: 온도 (°C)
    f_air_0: 초기 기공률 (20°C)
    beta: 유효 체적 열팽창계수
    """
    dT = T - 20.0  # reference = 20°C
    return 1 - (1 - f_air_0) / (1 + beta * dT)
```

---

## 7. 출력 디렉토리 구조

```
figures/paper_260406/
├── fig01_time_domain_zoom.png (.pdf)
├── fig02_peak_detail.png (.pdf)
├── fig03_n_vs_temp_ema.png (.pdf)        ★ 핵심
├── fig04_optical_spectra.png (.pdf)
├── fig05_time_features_vs_temp.png (.pdf)
├── fig06_porosity_vs_temp.png (.pdf)     ★ 핵심
├── fig07_dielectric.png (.pdf)
└── fig08_correlation_summary.png (.pdf)

results/paper_260406/
├── table02_optical_summary.csv
├── table03_per_sample_n.csv
├── table04_correlation_analysis.csv
└── ema_porosity_results.csv
```

---

## 8. 기존 라이브러리 재사용 목록

| 함수/패턴 | 위치 | 용도 |
|-----------|------|------|
| `load_measurement_set_with_refs()` | `thztds/io.py` | 데이터 로딩 |
| `parse_menlo_file()` | `thztds/io.py` | 개별 파일 파싱 |
| `process_temperature_series_matched_ref()` | `thztds/optical_properties.py` | 광학 상수 추출 |
| `compute_temperature_averages()` | `thztds/optical_properties.py` | 평균/표준편차 |
| `compute_fft()` | `thztds/signal.py` | FFT |
| `apply_window()` | `thztds/signal.py` | Hann 윈도우 |
| `ExtractionConfig` | `thztds/types.py` | 추출 설정 |

### ExtractionConfig 설정
```python
config = ExtractionConfig(
    thickness_mm=0.04,
    freq_min_thz=0.2,
    freq_max_thz=2.5,
    window_type="hann",
    zero_pad_factor=2,
    n_initial_guess=1.5,
    kappa_initial_guess=0.005,
    thin_film=True,
    apply_air_correction=False,  # Matched Ref이므로 불필요
)
```

---

## 9. 그래프 품질 체크리스트

- [ ] 모든 y축: 데이터 범위에 맞춤 (빈 영역 제외, margin 8%)
- [ ] 모든 그래프: PNG(600 DPI) + PDF 동시 저장
- [ ] 폰트: Arial, 본문 8pt, 축 레이블 9pt
- [ ] 샘플별 데이터: 개별 점/선 + 평균±σ 반드시 포함
- [ ] 온도 색상: TEMP_COLORS 일관 사용
- [ ] 샘플 색상: SAMPLE_COLORS + SAMPLE_MARKERS 일관 사용
- [ ] 모든 subplot: tight_layout()
- [ ] Fig.3, Fig.6: EMA 모델 곡선 + 전이 온도 annotation 필수
- [ ] 상관 분석: 레퍼런스 절대값 제외, 시료 고유 특성만

---

## 10. 스크립트 실행 및 검증

```bash
cd /path/to/01_THz_Temp
python3 scripts/analyze_pe40_paper.py

# 검증 항목:
# 1. figures/paper_260406/ 에 8개 Figure × 2 포맷 = 16 파일
# 2. results/paper_260406/ 에 4개 CSV
# 3. n @ 1.0 THz: 20°C에서 ~1.34, 100°C에서 ~1.28
# 4. EMA 기공률: 20°C에서 ~15-25%, 온도 증가 시 증가
# 5. 전이 온도: 약 40-50°C 근처
# 6. 콘솔에 모든 테이블 출력
```
