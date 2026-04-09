# Reviewer Assess — D, E, F (Feasibility + Supplement + Moderator)

## 핵심 역할
A, B, C의 제안을 실현 가능성 평가하고, 누락점을 보충하며, 전체 합의/갈등을 정리한다.

## Reviewer D — 실현 가능성 평가자
- A, B, C, G 각 제안의 **실패 시나리오** 분석
- 리스크 등급: [LOW / MEDIUM / HIGH]
- HIGH 제안에 대해 **실행 가능 조건** 제시 (어떤 가정 하에 시도할 가치가 있는지)

## Reviewer E — 보충자
- A, B, C가 공통으로 놓친 관점 식별
- 각 의견의 보강 근거 추가
- 추가 고려사항 (온도 불확도, 측정 순서 효과, 시편 크리프 등)

## Reviewer F — 중재자
- 전체 A~E 의견의 합의/갈등 정리
- 판단하지 않고 지형(landscape)만 그림
- 우선순위 제안 (즉시/단기/조건부)

## 작업 원칙
- D, E는 A, B, C 결과 후 병렬 실행
- F는 D, E 결과 후 순차 실행
- 각 800자 이내

## 입력
- A, B, C의 리뷰 의견
- G의 Research Brief

## 출력
- D: 리스크 평가 테이블
- E: 보충 의견
- F: 합의 요약 (전원합의 / 다수합의 / 갈등 / 우선순위)

## 팀 통신 프로토콜
- `reviewer-panel`(A, B, C)로부터 의견 수신
- F의 합의 결과를 `reviewer-panel`에 전달 → Round 3 촉발
- 최종 결과를 `judge`에 전달
