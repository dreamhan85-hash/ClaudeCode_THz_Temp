# 논문 리뷰 파이프라인

> paper-orchestrator.md에서 Step 1 실행 전 Read.

## Input (파일 경로로 전달)

- 논문 초고 파일
- 결과 CSV/Figure 파일 경로
- 이전 리뷰 기록 (`reports/paper_{N}_detail.md`)

## 리뷰어 구성 (5인 + Judge)

### Research Brief (단독, 첫 번째)

**G (Research Brief Writer)**:
- WebSearch로 최신 관련 논문 검색
- 논문 논리 강화에 활용할 레퍼런스 제안
- 근본적 논리 구조 개선안
- **Output**: `reports/paper_research_brief_{N}.md` (1500자), 반환: `"brief complete"`

### Round 1 (병렬)

**A (Data/Statistics)**:
- 통계 검정 충분성 (ANOVA, post-hoc, 다중비교 보정)
- 불확도 전파 완성도
- 수치 일관성 (본문 vs Table vs Figure)
- 데이터 완결성 (누락된 분석?)
- G의 brief 참조
- **Output**: 800자 이내

**B (Narrative/Logic)**:
- 논문 전체 흐름: Introduction → Methods → Results → Discussion
- 논리적 비약 없는지
- 핵심 주장의 근거 충분한지
- Abstract/Conclusion이 본문과 일치하는지
- G의 brief 참조
- **Output**: 800자 이내

**C (Visual/Format)**:
- Figure 품질 체크리스트:
  - y축 범위: 데이터에 맞는지
  - 텍스트: 겹침 없는지, 8pt 이상인지
  - 범례: 적절한 위치인지
  - colorbar: 적절한 컬러맵인지
  - 번호: 순차적인지
- Table 완성도
- 저널 포맷 준수 (word count, ref count 등)
- **Output**: 800자 이내

### Round 2 (단독)

**D (Devil's Advocate)**:
- A, B, C 의견을 토대로 **가장 약한 부분** 집중 공격
- 리젝터의 관점: 이 논문이 거절되는 시나리오
- "이 실험이 증명하지 못하는 것"
- 추가 데이터/분석 없이 해결 가능한 것 vs 불가능한 것 구분
- **Output**: 800자 이내

### Round 3 (병렬)

A, B, C가 D의 공격에 대한 방어/수용 의견 제출:
- 유지/수정 + 이유
- **Output**: 각 400자 이내

### Judge

**Input**: 전체 리뷰 기록 (파일 경로)

**판정 기준**:
- `submit`: 투고 수준 도달
  - A: 통계적 완결 + B: 논리적 일관 + C: 시각적 완성 + D의 공격이 방어됨
- `improve`: 추가 개선 필요하되, 현재 데이터로 해결 가능
  - 구체적 NEXT_ACTION (어디를 어떻게 수정할지)
- `need_data`: 추가 실험/분석 없이는 해결 불가
  - 부족한 분석 항목 명시 (→ 실험 루프로 handoff)

**Returns**:
```
DECISION: [submit / improve / need_data]
RATIONALE: [200자 이내]
NEXT_ACTION: [improve 시 수정 계획 / need_data 시 필요 분석 목록]
SYSTEM_SUGGESTIONS: [시스템 개선 제안 — 없으면 null]
```

---

## 시스템 개선 제안 (Meta-Improvement)

리뷰 과정에서 시스템 레벨 개선이 필요하다고 판단되면 수집:
- 리뷰어 역할/관점 조정 (예: "저널 포맷 전문 리뷰어 추가 필요")
- 논문 템플릿 개선 (예: "Discussion 구조 가이드라인 추가")
- 분석 파이프라인 기능 (예: "자동 불확도 전파 함수 필요")
- 프롬프트 개선 (예: "Writer 에이전트에 저널 스타일 가이드 추가")

Judge가 `SYSTEM_SUGGESTIONS`에 기록 → 오케스트레이터가 누적 → 사용자 승인 후 반영.

---

## Recording

`reports/paper_{N}_detail.md` 단일 파일에 기록:

```markdown
# Paper Review — Iteration {N} (v{draft_version})

## Research Brief (G)
[요약]
→ full: reports/paper_research_brief_{N}.md

## Round 1
**A (Data/Stats):** [...]
**B (Narrative):** [...]
**C (Visual):** [...]

## Round 2
**D (Devil's Advocate):** [...]

## Round 3
**A:** [maintain/revise] — [...]
**B:** [maintain/revise] — [...]
**C:** [maintain/revise] — [...]

## Judge Decision
- **Decision**: [...]
- **Rationale**: [...]
- **Next Action**: [...]
- **System Suggestions**: [...]
```
