# 실험 탐색 리뷰 파이프라인

> experiment-orchestrator.md에서 Step 2 실행 전 Read.

## Input (파일 경로로 전달)

- `reports/experiment_{N}_results.md` — 분석 결과
- `reports/methodology_{N}.md` — 적용한 방법론
- `reports/literature_brief_{N}.md` — 문헌 검색 결과
- 생성된 Figure/CSV 파일 경로

## 리뷰어 구성 (4인 + Judge)

### Round 1 (병렬)

**L (Literature Scout)**:
- 결과를 문헌과 대조: 값이 문헌 범위 내인가?
- 추가로 참조할 논문/방법론 WebSearch
- 아직 시도하지 않은 유망한 접근법 제안
- **Output**: 800자 이내

**A (Analysis Reviewer)**:
- 데이터 품질: SNR, 재현성, 이상값
- 물리적 타당성: 값 범위, 온도 트렌드 방향
- 통계적 유의성: 노이즈 대비 신호 크기
- **Output**: 800자 이내

**B (Methodology Reviewer)**:
- 분석 방법론의 적절성
- 파라미터 선택 근거
- 대안 파라미터/방법 제시
- 이전 반복에서 시도한 것과의 비교
- **Output**: 800자 이내

### Round 2 (단독)

**C (Insight Reviewer)**:
- A, B, L 의견을 종합하여 결과 해석
- 새로운 발견/패턴 식별
- 논문 가치 평가: 이 결과로 논문을 쓸 수 있는가?
- 부족한 분석/시각화 식별
- **Output**: 800자 이내

### Judge

**Input**: experiment_{N}_results.md + 모든 리뷰어 의견 (파일 경로)

**판정 기준**:
- `meaningful`: 물리적으로 유의미한 트렌드/발견이 있고, 논문 가치가 있음
  - A가 데이터 품질 OK + C가 논문 가치 있다고 판단
- `iterate`: 결과가 불충분하거나 더 나은 방법론이 제안됨
  - 구체적 NEXT_ACTION 포함 (어떤 방법론을 시도할지)
- `abort`: 데이터 자체에 근본적 문제가 있어 분석 불가

**Returns**:
```
DECISION: [meaningful / iterate / abort]
RATIONALE: [200자 이내]
NEXT_ACTION: [iterate 시 다음 분석 계획]
SYSTEM_SUGGESTIONS: [시스템 개선 제안 — 없으면 null]
```

---

## 시스템 개선 제안 (Meta-Improvement)

리뷰 과정에서 발견된 시스템 레벨 개선 사항을 수집:
- 리뷰어 역할/관점 조정 필요성
- 새로운 분석 템플릿 추가
- 방법론 라이브러리(thztds/) 기능 추가
- 지침/프롬프트 개선점

Judge가 `SYSTEM_SUGGESTIONS` 필드에 기록.
오케스트레이터가 이를 `reports/system_suggestions.md`에 누적.
사용자에게 알림 후 승인 시 `.claude/` 설정에 반영.

---

## Recording

모든 리뷰 내용을 `reports/experiment_{N}_detail.md`에 단일 파일로 기록:

```markdown
# Experiment {N}: {methodology 요약}

## Analysis Results
[결과 요약]

## Review Discussion

### Round 1
**L (Literature):** [...]
**A (Analysis):** [...]
**B (Methodology):** [...]

### Round 2
**C (Insight):** [...]

### Judge Decision
- **Decision**: [...]
- **Rationale**: [...]
- **Next Action**: [...]
- **System Suggestions**: [...]
```
