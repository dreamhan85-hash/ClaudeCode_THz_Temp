# /experiment — 실험 탐색 루프 런처

측정 데이터를 입력하면 문헌 검색 → 방법론 도출 → 분석 → 결과 평가를 자동 반복.
의미 있는 결과가 나오면 사용자에게 알리고, /paper 연결을 제안.

---

## Usage

```
/experiment data_dir=MeaData/260406_Temp [title=PE40_temp_study] [max_iterations=10] [lang=ko]
```

## Arguments

| argument | description | default |
|----------|-------------|---------|
| `data_dir` | 측정 데이터 디렉토리 | required |
| `title` | 실험 제목 (폴더명으로 사용) | 디렉토리명에서 추론 |
| `max_iterations` | 최대 반복 횟수 | 10 |
| `ref_papers` | 참고 논문 디렉토리 | `Ref_Paper/` |
| `resume_from` | 논문 루프에서 돌아온 경우, 부족 분석 명세 파일 경로 | optional |
| `lang` | 출력 언어 | `ko` |

---

## Procedure

### Step 1: Parse and Validate

- `$ARGUMENTS` 파싱
- 데이터 디렉토리 존재 확인
- 파일 목록 스캔 (Ref_*.txt, Sample_*.txt 패턴)
- `resume_from`이 있으면 해당 파일을 읽어 부족 분석 명세를 컨텍스트에 로딩
- 파싱 결과 출력

### Step 2: Create Initial State

`experiment_continuation.json` 생성:

Path: `research/logs/{YYYY-MM-DD}/{title}/cache/experiment_continuation.json`

```json
{
  "schema_version": 1,
  "status": "initial",
  "written_at": "{ISO 8601}",
  "session": {
    "title": "{title}",
    "date": "{YYYY-MM-DD}",
    "data_dir": "{data_dir}",
    "ref_papers": "{ref_papers}",
    "max_iterations": {max_iterations},
    "resume_from": "{resume_from or null}"
  },
  "progress": {
    "iteration": 0,
    "methodologies_tried": [],
    "best_result": null,
    "literature_refs": [],
    "decision_history": []
  },
  "handoff_to_paper": null
}
```

### Step 3: Print Confirmation and Run Loop

```
🔬 실험 탐색 루프 시작

데이터: {data_dir}
제목: {title}
최대 반복: {max_iterations}
참고문헌: {ref_papers}

State: research/logs/{date}/{title}/cache/experiment_continuation.json
```

Run `scripts/experiment-loop.sh` in background:

```bash
./scripts/experiment-loop.sh "data_dir={data_dir} title={title} max_iterations={max_iterations} ref_papers={ref_papers} lang={lang}"
```

---

## Notes

- `/paper`에서 `need_data` 판정 시 `resume_from=path/to/need_data_spec.md`로 재호출
- 연구 노트에 자동 요약 삽입 (반복 종료 시)
- 기존 `/analyze`와 독립적으로 동작
