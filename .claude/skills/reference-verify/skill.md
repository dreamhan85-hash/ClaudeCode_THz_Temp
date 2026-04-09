---
name: reference-verify
description: "SCI 논문 참고문헌 실체 검증 스킬. 저자, 저널, 권호, 페이지, DOI를 WebSearch/WebFetch로 교차 검증. 참고문헌을 추가하거나 검증할 때 반드시 이 스킬을 사용할 것. reference, citation, bibliography, 참고문헌 키워드에 트리거."
---

# Reference Verify — SCI Paper Citation Verification

## 검증 절차

### Step 1: 기본 정보 파싱
```
[N] 저자, 저널, 권(호) (연도) 페이지.
```
에서 저자명, 저널명, 권, 호, 페이지, 연도 추출.

### Step 2: WebSearch 교차 검증
1. `"{제1저자 성} {저널명} {연도} {권}"` 으로 검색
2. 결과에서 실제 논문 제목, DOI 확인
3. DOI가 있으면 WebFetch로 상세 확인

### Step 3: 판정
| 판정 | 기준 |
|------|------|
| **OK** | 저자, 저널, 권, 페이지, 연도 모두 일치 |
| **CORRECTION** | 일부 불일치 → 정확한 값 제시 |
| **UNVERIFIABLE** | 검색 결과 없음 → 제거 또는 대체 권고 |
| **FABRICATED** | 해당 조합의 논문이 존재하지 않음 → 즉시 제거 |

### Step 4: 보고
```
| # | 판정 | 이슈 | 수정 |
|---|------|------|------|
| [1] | OK | — | — |
| [4] | CORRECTION | 페이지 오류 | 210→246 |
| [21] | FABRICATED | 해당 논문 없음 | 제거 |
```

## 주의사항
- Google Scholar 직접 접근은 불가 → 일반 WebSearch 사용
- 한 번에 8-10편씩 병렬 검증 (Agent 활용)
- Elsevier, Springer, Wiley, MDPI 등 출판사 사이트에서 확인
- 참고문헌 번호가 본문 인용과 일치하는지도 확인
- 검증 불가 시 "미확인" 표기 (거짓으로 "OK" 판정 금지)

## 자주 발생하는 오류 유형
1. **저자명 오류**: 제1저자가 아닌 공저자로 기재
2. **페이지/Article 번호 오류**: 연속 페이지 vs article number 혼동
3. **저널명 오류**: 약어 불일치 (J. vs Journal)
4. **연도 오류**: accepted year vs published year
5. **존재하지 않는 논문**: AI 생성 hallucination
