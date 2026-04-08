"""RLAIF completion check for temperature correlation analysis."""
from __future__ import annotations
import json, sys
from pathlib import Path

STATE_FILE = Path("/Users/cion_mini/Desktop/DEV/01_THz_Temp/scripts/.rlaif_state.json")
MAX_ITERATIONS = 200
TARGET_SCORE = 95

def main():
    if not STATE_FILE.exists():
        sys.exit(0)
    with open(STATE_FILE) as f:
        state = json.load(f)
    it = state.get("iteration", 0)
    best = state.get("best_score", 0)
    history = state.get("history", [])
    latest = history[-1]["score"] if history else 0

    if it >= MAX_ITERATIONS or latest >= TARGET_SCORE:
        n_feat = len(state.get("features_found", []))
        print(f"RLAIF COMPLETE [{it}/{MAX_ITERATIONS}] score={latest} best={best} features={n_feat}", file=sys.stderr)
        sys.exit(0)

    print(f"RLAIF [{it}/{MAX_ITERATIONS}] score={latest} best={best}. 계속 분석을 개선하세요.", file=sys.stderr)
    sys.exit(2)

if __name__ == "__main__":
    main()
