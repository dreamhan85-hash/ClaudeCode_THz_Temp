#!/usr/bin/env bash
# experiment-loop.sh — 실험 탐색 루프 세션 회전 래퍼
#
# 매 반복마다 새 claude -p 세션을 생성하여 컨텍스트 초기화.
# experiment_continuation.json의 상태를 기반으로 반복/종료 결정.
#
# Usage:
#   ./scripts/experiment-loop.sh "data_dir=MeaData/260406_Temp title=PE40_temp max_iterations=10 lang=ko"

set -euo pipefail

unset CLAUDECODE 2>/dev/null || true

ARGS="$1"
MAX_RETRIES=3
POLL_INTERVAL=10

# --- Parse arguments ---
title=""
for pair in $ARGS; do
  key="${pair%%=*}"
  val="${pair#*=}"
  if [[ "$key" == "title" ]]; then
    title="$val"
    title="${title%\"}"
    title="${title#\"}"
  fi
done

if [[ -z "$title" ]]; then
  echo "ERROR: title is required in arguments"
  exit 1
fi

TODAY=$(date +%Y-%m-%d)
SESSION_DIR="research/logs/${TODAY}/${title}"
STATE_FILE="${SESSION_DIR}/cache/experiment_continuation.json"
LOG_DIR="${SESSION_DIR}/cache"
LOG_FILE="${LOG_DIR}/loop.log"

mkdir -p "$LOG_DIR"

log() {
  local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
  echo "$msg" | tee -a "$LOG_FILE"
}

get_status() {
  if [[ -f "$STATE_FILE" ]]; then
    jq -r '.status // "unknown"' "$STATE_FILE" 2>/dev/null || echo "unknown"
  else
    echo "missing"
  fi
}

get_written_at() {
  if [[ -f "$STATE_FILE" ]]; then
    jq -r '.written_at // ""' "$STATE_FILE" 2>/dev/null || echo ""
  else
    echo ""
  fi
}

# --- Main loop ---
consecutive_failures=0
iteration=0

log "=== experiment-loop.sh started ==="
log "Args: $ARGS"
log "State file: $STATE_FILE"

while true; do
  iteration=$((iteration + 1))
  log "--- Iteration $iteration ---"

  ORCHESTRATOR_FILE=".claude/prompts/experiment-orchestrator.md"
  if [[ ! -f "$ORCHESTRATOR_FILE" ]]; then
    log "ERROR: Orchestrator file not found: $ORCHESTRATOR_FILE"
    exit 1
  fi

  ORCHESTRATOR_CONTENT=$(cat "$ORCHESTRATOR_FILE")
  PROMPT="${ORCHESTRATOR_CONTENT}

---

## 세션 시작 정보

State 파일 경로: ${STATE_FILE}
인자: ${ARGS}
"

  log "Spawning new claude session..."
  pre_written_at=$(get_written_at)

  set +e
  claude -p --dangerously-skip-permissions "$PROMPT" >> "$LOG_FILE" 2>&1
  exit_code=$?
  set -e

  log "Claude session exited with code $exit_code"

  status=$(get_status)
  post_written_at=$(get_written_at)
  log "Status: $status | written_at: $post_written_at"

  case "$status" in
    meaningful|stopped)
      log "Loop finished: status=$status"
      log "=== experiment-loop.sh completed ==="
      exit 0
      ;;
    iterating)
      if [[ "$post_written_at" != "$pre_written_at" ]]; then
        consecutive_failures=0
        log "Progress detected, continuing..."
      else
        consecutive_failures=$((consecutive_failures + 1))
        log "WARNING: No progress. Failures: $consecutive_failures/$MAX_RETRIES"
        if [[ $consecutive_failures -ge $MAX_RETRIES ]]; then
          log "ERROR: $MAX_RETRIES consecutive failures. Aborting."
          exit 1
        fi
      fi
      ;;
    initial)
      consecutive_failures=$((consecutive_failures + 1))
      log "WARNING: Status still 'initial'. Failures: $consecutive_failures/$MAX_RETRIES"
      if [[ $consecutive_failures -ge $MAX_RETRIES ]]; then
        log "ERROR: $MAX_RETRIES consecutive failures. Aborting."
        exit 1
      fi
      ;;
    *)
      consecutive_failures=$((consecutive_failures + 1))
      log "WARNING: Unexpected status '$status'. Failures: $consecutive_failures/$MAX_RETRIES"
      if [[ $consecutive_failures -ge $MAX_RETRIES ]]; then
        log "ERROR: $MAX_RETRIES consecutive failures. Aborting."
        exit 1
      fi
      ;;
  esac

  log "Sleeping ${POLL_INTERVAL}s before next iteration..."
  sleep "$POLL_INTERVAL"
done
