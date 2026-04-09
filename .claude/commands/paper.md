# /paper — 논문 개선 루프 런처

실험 결과를 기반으로 논문 초고를 생성하고, 리뷰 → 개선을 반복하여 투고 수준까지 개선.
부족한 분석이 발견되면 /experiment 루프로 재요청.

---

## Usage

```
/paper results_dir=results/paper_260406 [experiment_ref=path/to/experiment_continuation.json] [journal=SNA] [max_iterations=10] [lang=ko]
```

## Arguments

| argument | description | default |
|----------|-------------|---------|
| `results_dir` | 분석 결과 디렉토리 (CSV, figures) | required |
| `experiment_ref` | 실험 루프 상태 파일 (handoff 정보 참조) | optional |
| `journal` | 타겟 저널 약어 | optional |
| `max_iterations` | 최대 반복 횟수 | 10 |
| `title` | 논문 제목 (폴더명으로 사용) | 결과 디렉토리에서 추론 |
| `lang` | 출력 언어 | `ko` |

---

## Procedure

### Step 1: Parse and Validate

- `$ARGUMENTS` 파싱
- 결과 디렉토리 존재 확인
- `experiment_ref`가 있으면 handoff 정보 로딩 (핵심 결과, 문헌 목록)
- figures/, CSV 파일 목록 확인

### Step 2: Create Initial State

`paper_continuation.json` 생성:

Path: `research/logs/{YYYY-MM-DD}/{title}/cache/paper_continuation.json`

```json
{
  "schema_version": 1,
  "status": "initial",
  "written_at": "{ISO 8601}",
  "session": {
    "title": "{title}",
    "date": "{YYYY-MM-DD}",
    "results_dir": "{results_dir}",
    "experiment_ref": "{experiment_ref or null}",
    "journal": "{journal or null}",
    "max_iterations": {max_iterations}
  },
  "progress": {
    "iteration": 0,
    "draft_version": 0,
    "review_history": [],
    "system_suggestions": []
  },
  "handoff_to_experiment": null
}
```

### Step 3: Print Confirmation and Run Loop

```
📝 논문 개선 루프 시작

결과: {results_dir}
타겟 저널: {journal}
최대 반복: {max_iterations}

State: research/logs/{date}/{title}/cache/paper_continuation.json
```

Run `scripts/paper-loop.sh` in background:

```bash
./scripts/paper-loop.sh "results_dir={results_dir} title={title} max_iterations={max_iterations} journal={journal} lang={lang}"
```

---

## Notes

- `need_data` 판정 시 부족 분석 명세를 파일로 생성하고 사용자에게 알림
- 사용자가 `/experiment resume_from=...`으로 실험 루프 재실행
- 실험 루프에서 보충된 결과가 results_dir에 추가되면 논문 루프 재시작
