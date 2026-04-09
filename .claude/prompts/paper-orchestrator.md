# 논문 개선 오케스트레이터

## Module Loading

- **Step 0 전**: 이 파일의 규칙 숙지
- **Step 1 전**: `.claude/prompts/paper-writer.md` Read (초고 생성/수정 에이전트)
- **Step 2 전**: `.claude/prompts/paper-review.md` Read (논문 리뷰 파이프라인)

---

## Iteration Entry Point

1. **Read state file**: `paper_continuation.json`
2. **Branch by status**:
   - `initial` → Step 0 (결과 로딩 + 초고 생성) + Step 1 (리뷰) + Step 2 (판정)
   - `improving` → next_action 적용 후 Step 1 + Step 2
   - `submit_ready` → 사용자에게 알림 후 종료
   - `need_data` → 부족 분석 명세 작성 후 사용자에게 알림
   - `stopped` → 종료

---

## Step 0: 결과 로딩 + 초고 생성/수정

### 0-A. 결과 분석

결과 디렉토리를 스캔하여:
- CSV 파일들의 핵심 수치 추출
- Figure 목록 확인 (PNG/PDF)
- `experiment_ref`에서 handoff 정보 참조 (문헌 목록, 방법론)

### 0-B. 초고 생성/수정

Read `.claude/prompts/paper-writer.md` 후 Writer 에이전트 호출:

**첫 반복**: 결과를 기반으로 논문 초고 생성
**이후 반복**: 리뷰 결과를 반영하여 기존 초고 수정

**Output**: `results/{title}/paper_draft_v{N}.docx` 또는 `.md`

---

## Step 1: 논문 리뷰

Read `.claude/prompts/paper-review.md` 후 리뷰 파이프라인 실행.

**Input**:
- 현재 논문 초고
- 결과 CSV/Figure 파일들
- 이전 리뷰 히스토리 (`reports/paper_{N}_detail.md`)

**Output**: Judge 판정 (`improve` / `submit` / `need_data`)

---

## Step 2: 판정 처리

### submit

1. `paper_continuation.json` 업데이트: `status: "submit_ready"`
2. 사용자에게 알림:
   ```
   ✅ 논문 투고 준비 완료! (v{N}, {iterations}회 리뷰)

   최종 버전: {draft_path}
   체크리스트:
   - [ ] 저자/소속 기입
   - [ ] Cover letter 작성
   - [ ] Graphical abstract
   - [ ] 저널 포맷 최종 확인
   ```
3. 연구 노트에 요약 삽입

### improve

1. `paper_continuation.json` 업데이트:
   - `status: "improving"`
   - `progress.iteration` 증가
   - `next_action`: 리뷰에서 도출된 개선 방향
   - `progress.review_history`에 판정 추가
2. 연구 노트에 요약 삽입
3. `max_iterations` 확인
4. 다음 반복 (세션 회전)

### need_data

1. `paper_continuation.json` 업데이트:
   - `status: "need_data"`
   - `handoff_to_experiment`: 부족한 분석 명세
2. 부족 분석 명세 파일 생성: `reports/need_data_spec.md`
   ```markdown
   # 추가 분석 요청

   ## 부족한 분석 항목
   1. [구체적 분석 항목]
   2. [...]

   ## 요청 근거
   - [리뷰어 의견 요약]

   ## 기대 결과
   - [추가 분석이 논문에 어떻게 기여하는지]
   ```
3. 사용자에게 알림:
   ```
   📊 추가 분석이 필요합니다.

   부족 항목: {요약}
   명세: reports/need_data_spec.md

   실험 루프로 돌아가려면:
   /experiment data_dir={data_dir} resume_from=reports/need_data_spec.md
   ```
4. 연구 노트에 요약 삽입

---

## 시스템 개선 제안 처리

리뷰에서 `SYSTEM_SUGGESTIONS`가 도출되면:

1. `reports/system_suggestions.md`에 누적
2. 3개 이상 누적 시 사용자에게 요약 제시:
   ```
   🔧 시스템 개선 제안 {N}건이 누적되었습니다.

   1. [제안 1 요약]
   2. [제안 2 요약]
   ...

   승인하시면 .claude/ 설정에 반영합니다.
   ```
3. 사용자 승인 시:
   - `.claude/prompts/` 파일 수정
   - `.claude/commands/` 업데이트
   - `CLAUDE.md` 업데이트
   - 변경 내용 커밋

---

## 연구 노트 자동 요약

매 반복 종료 시 `research/logs/{YYYY-MM-DD}/log.md`에 append:

```markdown
## 논문 개선: {title} — Iteration {N} (v{draft_version}, {HH:MM})
- **수정 사항**: {적용한 개선 1줄 요약}
- **판정**: {improve/submit/need_data}
- **남은 이슈**: {next_action 요약}
```

---

## Communication Principles

- **File-as-IPC**: 에이전트 간 파일 경로로만 데이터 전달
- **Writer 에이전트**: `"draft updated: {변경 요약}"` 1줄만 반환
- **Reviewer 출력 제한**: 각 800자, Judge 200자
- **GitHub 동기화**: 매 반복 종료 시 research/ sync
