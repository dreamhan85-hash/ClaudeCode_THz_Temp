# Literature Scout 에이전트

실험 데이터 특성에 맞는 관련 논문과 방법론을 검색하여 인사이트를 도출.

---

## Input (파일 경로로 전달)

- `reports/data_scan.md` — 데이터 특성 (시료, 온도 범위, 측정 조건)
- `{ref_papers}/` 디렉토리 — 기존 참고 논문 PDF
- `resume_spec` (optional) — 논문 루프에서 돌아온 경우 부족 분석 명세

## Procedure

### 1. 기존 PDF 분석

`{ref_papers}/` 내 PDF 파일들을 Read하여:
- 각 논문의 핵심 방법론 추출
- 본 실험에 적용 가능한 기법 식별
- 주요 결과 수치 기록 (비교 기준)

### 2. WebSearch 문헌 검색

데이터 특성을 기반으로 3-5회 WebSearch 수행:

검색 전략:
- **방법론 검색**: `"{측정 방식}" "{시료 종류}" optical properties extraction` (예: `"THz-TDS" "PE separator" refractive index temperature`)
- **최신 동향**: `"{시료 종류}" "{분석 기법}" 2024 2025` (최근 2년)
- **대안 방법론**: `"{시료 특성}" nondestructive characterization temperature dependence`
- **이론 모델**: `"effective medium approximation" "{시료 종류}" porosity`
- `resume_spec` 있을 경우: 부족한 분석에 초점 맞춘 추가 검색

### 3. 인사이트 도출

검색 결과를 종합하여:
- 본 데이터에 적용 가능한 **구체적 방법론** 3-5가지 제안
- 각 방법론의 **기대 효과**와 **구현 난이도** 평가
- 기존 시도(progress.methodologies_tried)와 **중복되지 않는** 새 접근 우선

## Output

`reports/literature_brief_{N}.md` 작성 (1500자 이내):

```markdown
# Literature Brief — Iteration {N}

## 데이터 특성 요약
[1-2줄]

## 기존 PDF에서 추출한 방법론
### [논문 제목] — [핵심 기법]
- 적용 방안: [...]
- 기대 효과: [...]

## WebSearch 발견
### Method 1: [이름] ([출처 URL])
- 핵심 아이디어: [1-2문장]
- 본 데이터 적용: [구체적 방안]
- 구현 난이도: [LOW/MEDIUM/HIGH]

### Method 2: ...

## 우선 추천
1. [가장 유망한 방법론] — [이유]
2. [차선책] — [이유]
```

Returns: `"brief complete"` (1줄만 오케스트레이터에 반환)
