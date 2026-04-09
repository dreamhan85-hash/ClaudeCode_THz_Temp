# THz-TDS 데이터 분석 명령

분석 스크립트를 실행하고, 결과를 검토하여 개선 방향을 도출하는 명령.

---

## Usage

```
/analyze script=scripts/analyze_pe40_paper.py [data_dir=MeaData/260406_Temp] [review=true] [apply=true] [lang=ko]
```

## Arguments

| argument | description | default |
|----------|-------------|---------|
| `script` | 분석 스크립트 경로 | `scripts/analyze_pe40_paper.py` |
| `data_dir` | 측정 데이터 디렉토리 | `MeaData/260406_Temp` |
| `review` | 결과 리뷰 및 개선 방향 도출 여부 | `true` |
| `apply` | 도출된 개선 사항 자동 적용 여부 | `false` |
| `lang` | 출력 언어 | `ko` |

---

## Procedure

### Step 1: Parse and Validate

- `$ARGUMENTS` 파싱
- 스크립트 파일 존재 확인
- 데이터 디렉토리 존재 확인
- 파싱 결과 출력

### Step 2: Run Analysis Script

```bash
python3 {script}
```

- 실행 결과(stdout/stderr) 캡처
- 에러 발생 시 진단 후 수정 시도 (최대 3회)
- 성공 시 생성된 파일 목록 확인

### Step 3: Result Validation

생성된 결과물 검증:

#### 3.1 Figure 검증
- `figures/paper_260406/` 내 생성된 PNG/PDF 파일 목록
- 각 그래프 이미지 확인 (Read tool로 시각 검증)
- **그래프 품질 체크리스트** (논문 투고 수준):
  - y축 범위: 데이터 범위에 맞게 설정? (빈 공간 과다 금지)
  - 텍스트 라벨: 데이터 점/라인과 겹침 없는지?
  - 범례(legend): 데이터와 겹치지 않는 위치? 박스 배경 투명도?
  - 주석(annotation): 화살표와 텍스트가 데이터를 가리지 않는지?
  - 서브캡션 (a)(b)(c): 하단 또는 일관된 위치?
  - 폰트 크기: A4 인쇄 시 읽을 수 있는 크기? (최소 8pt)
  - Figure 번호: 본문 참조와 순차적으로 일치?
  - 축 단위: 물리량에 적합한 단위와 범위?
  - colorbar: 온도 등 연속 변수에 적절한 컬러맵?

#### 3.2 CSV 검증  
- `results/paper_260406/` 내 CSV 파일 읽기
- 값 범위 물리적 타당성 검증:
  - n: 1.0~1.5 범위 내?
  - f_air: 30~70% 범위 내?
  - T_onset: 30~90°C 범위 내?
  - α: 음수 없는지?

#### 3.3 물리적 일관성
- 온도 증가 → n 감소 (기공 확대)?
- EMA 기공률이 제조사 사양(44%)에서 시작?
- 전이 온도가 DSC Tm(139°C)보다 낮은지?

### Step 4: Multi-Agent Review (when review=true)

3개 관점에서 결과를 검토:

#### Reviewer A: 데이터 품질
- SNR 충분한가?
- 샘플 간 편차가 허용 범위 내인가?
- 이상 샘플 제외 필요성?

#### Reviewer B: 물리적 해석
- EMA 모델 적합성 (3상 vs 2상, 등방 vs 비등방)
- 전이 온도의 물리적 의미
- 열팽창 모델의 β 값 타당성

#### Reviewer C: 논문 준비도
- Figure 품질 (해상도, 축 범위, 레이블)
- Table 완성도
- 누락된 분석 또는 그래프?

#### 종합 판정
- `sufficient`: 현재 결과로 논문 작성 가능
- `improve`: 특정 항목 개선 필요 (구체적 목록 제시)
- `rerun`: 파라미터 변경 후 재분석 필요

### Step 5: Apply Improvements (when apply=true)

- `improve` 판정 시 구체적 코드 수정 적용
- 수정 후 스크립트 재실행
- 결과 재검증

### Step 6: Research Log

분석 결과를 연구 로그에 기록:
```
research/logs/{YYYY-MM-DD}/log.md
```
기록 항목:
- 실행한 스크립트 및 파라미터
- 주요 결과 수치 (n, f_air, T_onset, β)
- 리뷰 결과 및 개선 사항
- 다음 단계 제안

---

## Notes

- 이 명령은 `/train` 루프와 독립적으로 동작
- `apply=false`면 분석 + 리뷰만 수행 (코드 수정 없음)
- 기존 RLAIF 훅과 호환 (PostToolUse 훅이 자동 실행됨)
