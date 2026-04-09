# 실험 탐색 오케스트레이터

## Module Loading

- **Step 0 전**: 이 파일의 규칙 숙지
- **Step 1 전**: `.claude/prompts/experiment-literature.md` Read (문헌 검색 에이전트 규칙)
- **Step 2 전**: `.claude/prompts/experiment-review.md` Read (리뷰 파이프라인)

---

## Iteration Entry Point

1. **Read state file**: `experiment_continuation.json`
2. **Branch by status**:
   - `initial` → Step 0 (데이터 스캔) + Step 1 (분석) + Step 2 (리뷰)
   - `iterating` → next_action 적용 후 Step 1 + Step 2
   - `meaningful` → 사용자에게 알림 후 종료
   - `stopped` → 종료

---

## Step 0: 데이터 스캔 + 문헌 검색

### 0-A. 데이터 특성 파악

데이터 디렉토리를 스캔하여:
- 파일 개수, 온도 범위, 반복 수
- Reference 패턴 (단일 Ref vs 온도별 Ref)
- 시료 네이밍 패턴에서 시료 정보 추론
- 대표 파일 1개를 Read하여 데이터 포맷 확인

결과를 `reports/data_scan.md`에 기록.

### 0-B. 문헌 검색 (Literature Scout 에이전트)

Read `.claude/prompts/experiment-literature.md` 후 Literature Scout 에이전트 호출:

**Input**:
- `reports/data_scan.md` (데이터 특성)
- `{ref_papers}` 디렉토리 경로 (기존 PDF)
- `resume_from` 파일 (논문 루프에서 돌아온 경우)

**Output**: `reports/literature_brief_{N}.md` — 관련 방법론, 인사이트, 적용 제안

### 0-C. 방법론 설계

문헌 검색 결과를 바탕으로 분석 방법론을 설계:
- 어떤 전달함수 방식을 쓸지 (Matched Ref, Air Ref, Differential)
- 주파수 범위, 윈도우 함수, 파라미터
- 추가 분석 (EMA, 통계 검정, ML 등)

설계를 `reports/methodology_{N}.md`에 기록.

### 0-D. 분석 스크립트 생성/수정

방법론에 맞는 분석 스크립트를 생성하거나 기존 스크립트 수정:
- `scripts/` 하에 스크립트 작성
- 기존 `thztds/` 라이브러리 함수 최대한 재사용

---

## Step 1: 분석 실행

```bash
python3 {analysis_script}
```

- stdout/stderr 캡처
- 에러 시 진단 후 수정 (최대 3회)
- 생성된 파일 목록 확인 (figures/, results/)
- 주요 수치 추출하여 `reports/experiment_{N}_results.md`에 기록

---

## Step 2: 결과 리뷰

Read `.claude/prompts/experiment-review.md` 후 리뷰 파이프라인 실행.

**Input**:
- `reports/experiment_{N}_results.md`
- `reports/methodology_{N}.md`
- `reports/literature_brief_{N}.md`
- 생성된 Figure/CSV 파일들

**Output**: Judge 판정 (`meaningful` / `iterate` / `abort`)

---

## Step 3: 판정 처리

### meaningful

1. `experiment_continuation.json` 업데이트:
   - `status`: `"meaningful"`
   - `handoff_to_paper`: 결과 디렉토리, 핵심 수치, 문헌 목록
2. 사용자에게 알림:
   ```
   🎯 의미 있는 결과 도출! (Iteration {N})

   핵심 결과:
   - [주요 수치 요약]

   /paper results_dir={results_dir} experiment_ref={state_file}
   위 명령으로 논문 작성 루프를 시작할 수 있습니다.
   ```
3. 연구 노트에 요약 삽입
4. 루프 종료

### iterate

1. `experiment_continuation.json` 업데이트:
   - `status`: `"iterating"`
   - `progress.iteration` 증가
   - `progress.methodologies_tried`에 현재 방법론 추가
   - `next_action`: 리뷰에서 도출된 개선 방향
   - `progress.decision_history`에 판정 추가
2. 연구 노트에 요약 삽입
3. `max_iterations` 확인 → 초과 시 종료
4. 다음 반복 (세션 회전)

### abort

1. `status`: `"stopped"`
2. 사용자에게 종료 사유 알림
3. 연구 노트에 요약 삽입

---

## 연구 노트 자동 요약

매 반복 종료 시 `research/logs/{YYYY-MM-DD}/log.md`에 append:

```markdown
## 실험 탐색: {title} — Iteration {N} ({HH:MM})
- **방법론**: {methodology 1줄 요약}
- **주요 결과**: {핵심 수치}
- **판정**: {meaningful/iterate/abort}
- **다음 방향**: {next_action 요약 또는 "논문 루프 연결"}
```

Bash `echo >>` 방식으로 append (Read 없이, sync-safe).

---

## Communication Principles

- **File-as-IPC**: 에이전트 간 파일 경로로만 데이터 전달
- **서브에이전트 출력 제한**: Literature Scout 1500자, Reviewer 800자, Judge 200자
- **GitHub 동기화**: 매 반복 종료 시 research/ sync
- **컨텍스트 보존**: 큰 데이터는 파일로, 오케스트레이터는 요약만 보유
