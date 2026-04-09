"""RLAIF evaluation for THz temperature correlation analysis.

PostToolUse hook: evaluates analysis script quality after each edit.
Checks: features extracted, R² values, statistical rigor, coverage.
"""
from __future__ import annotations

import json
import os
import sys
import subprocess
import re
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path("/Users/cion_mini/Desktop/DEV/01_THz_Temp")
STATE_FILE = PROJECT_DIR / "scripts" / ".rlaif_state.json"
ANALYSIS_SCRIPT = PROJECT_DIR / "scripts" / "temp_correlation.py"
MAX_ITERATIONS = 200
TARGET_SCORE = 95


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "iteration": 0,
        "max_iterations": MAX_ITERATIONS,
        "started_at": datetime.now().isoformat(),
        "best_score": 0,
        "best_r2": 0,
        "features_found": [],
        "history": [],
    }


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def run_analysis() -> dict:
    """Run the correlation analysis script and parse results."""
    if not ANALYSIS_SCRIPT.exists():
        return {"error": "temp_correlation.py not found", "score": 0}

    result = subprocess.run(
        [sys.executable, str(ANALYSIS_SCRIPT)],
        capture_output=True, text=True,
        cwd=str(PROJECT_DIR),
        env={**os.environ, "PYTHONPATH": str(PROJECT_DIR)},
        timeout=120,
    )

    output = result.stdout + result.stderr
    metrics = {
        "ran_ok": result.returncode == 0,
        "output_lines": len(output.strip().split("\n")) if output.strip() else 0,
        "r2_values": [],
        "correlations": [],
        "features": [],
        "error": result.stderr.strip()[-200:] if result.returncode != 0 else "",
    }

    # Parse R² values from output
    for m in re.finditer(r'R[²2]\s*[=:]\s*([\d.]+)', output):
        try:
            metrics["r2_values"].append(float(m.group(1)))
        except ValueError:
            pass

    # Parse correlation coefficients
    for m in re.finditer(r'[Rr]\s*[=:]\s*([+-]?[\d.]+)', output):
        try:
            v = float(m.group(1))
            if -1 <= v <= 1 and abs(v) > 0.01:
                metrics["correlations"].append(v)
        except ValueError:
            pass

    # Parse feature names
    for m in re.finditer(r'FEATURE:\s*(.+)', output):
        metrics["features"].append(m.group(1).strip())

    return metrics


def score_analysis(metrics: dict, state: dict) -> tuple[int, list[str]]:
    """Score the analysis quality. Returns (score, suggestions)."""
    score = 0
    suggestions = []

    # 1. Script runs without error (20 pts)
    if metrics.get("ran_ok"):
        score += 20
    else:
        suggestions.append(f"FIX ERROR: {metrics.get('error', 'unknown')[:100]}")
        return score, suggestions

    # 2. Output richness (15 pts)
    n_lines = metrics.get("output_lines", 0)
    if n_lines > 100:
        score += 15
    elif n_lines > 50:
        score += 10
    elif n_lines > 20:
        score += 5
    else:
        suggestions.append(f"MORE OUTPUT: only {n_lines} lines, analyze more features")

    # 3. R² values found (25 pts)
    r2s = metrics.get("r2_values", [])
    if r2s:
        best_r2 = max(r2s)
        if best_r2 > 0.8:
            score += 25
        elif best_r2 > 0.5:
            score += 20
        elif best_r2 > 0.3:
            score += 15
        elif best_r2 > 0.1:
            score += 10
        else:
            score += 5
            suggestions.append(f"IMPROVE R²: best={best_r2:.4f}, try different features")
        state["best_r2"] = max(state.get("best_r2", 0), best_r2)
    else:
        suggestions.append("NO R² FOUND: compute R² for all correlations")

    # 4. Number of features analyzed (20 pts)
    features = metrics.get("features", [])
    n_feat = len(features)
    if n_feat >= 15:
        score += 20
    elif n_feat >= 10:
        score += 15
    elif n_feat >= 5:
        score += 10
    elif n_feat >= 1:
        score += 5
    else:
        suggestions.append("EXTRACT MORE FEATURES from THz waveforms")

    new_features = [f for f in features if f not in state.get("features_found", [])]
    if new_features:
        state.setdefault("features_found", []).extend(new_features)

    # 5. Statistical significance (20 pts)
    corrs = metrics.get("correlations", [])
    sig_corrs = [c for c in corrs if abs(c) > 0.7]
    if len(sig_corrs) >= 5:
        score += 20
    elif len(sig_corrs) >= 3:
        score += 15
    elif len(sig_corrs) >= 1:
        score += 10
    elif corrs:
        score += 5
        suggestions.append("FIND STRONGER CORRELATIONS: none with |r|>0.7")
    else:
        suggestions.append("COMPUTE CORRELATIONS: Pearson r for each feature vs temperature")

    # General suggestions based on coverage
    known = set(state.get("features_found", []))
    possible = {
        "peak_time_delay", "peak_amplitude", "peak_amplitude_ratio",
        "pulse_width", "pulse_area", "rise_time", "fall_time",
        "zero_crossing_time", "spectral_centroid", "spectral_bandwidth",
        "spectral_peak_freq", "phase_slope", "group_delay",
        "envelope_width", "envelope_asymmetry",
        "fft_amplitude_ratio", "fft_phase_diff",
        "absorption_integral", "dispersion_slope",
        "time_domain_rms", "time_domain_kurtosis",
    }
    missing = possible - known
    if missing and score < TARGET_SCORE:
        suggestions.append(f"TRY: {', '.join(list(missing)[:5])}")

    return score, suggestions


def main():
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        hook_input = {}

    edited_file = hook_input.get("tool_input", {}).get("file_path", "")

    if not edited_file.endswith(".py"):
        json.dump({"hookSpecificOutput": {"hookEventName": "PostToolUse",
            "additionalContext": "RLAIF: skip (non-Python)"}}, sys.stdout)
        return

    if "evaluate_iteration" in edited_file or "check_completion" in edited_file:
        json.dump({"hookSpecificOutput": {"hookEventName": "PostToolUse",
            "additionalContext": "RLAIF: skip (self)"}}, sys.stdout)
        return

    state = load_state()
    state["iteration"] += 1
    it = state["iteration"]

    # Run and evaluate
    metrics = run_analysis()
    score, suggestions = score_analysis(metrics, state)

    state["history"].append({"iteration": it, "score": score,
        "file": Path(edited_file).name, "n_features": len(metrics.get("features", []))})
    state["best_score"] = max(state.get("best_score", 0), score)

    save_state(state)

    status = "COMPLETE" if it >= MAX_ITERATIONS or score >= TARGET_SCORE else "CONTINUE"
    fixes = " | ".join(suggestions[:3]) if suggestions else "All checks good"
    n_feat = len(state.get("features_found", []))
    best_r2 = state.get("best_r2", 0)

    feedback = (
        f"RLAIF [{it}/{MAX_ITERATIONS}] score={score}/100 status={status}\n"
        f"Features:{n_feat} BestR²:{best_r2:.4f}\n"
        f"{fixes}"
    )

    json.dump({"hookSpecificOutput": {"hookEventName": "PostToolUse",
        "additionalContext": feedback}}, sys.stdout)


if __name__ == "__main__":
    main()
