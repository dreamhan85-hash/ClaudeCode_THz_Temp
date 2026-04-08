"""THz-TDS 시간영역 신호 → 온도 예측 ML 파이프라인.

Raw time-domain signal → 자동 feature 추출 → 온도 회귀 예측.
Feature importance 분석으로 예측에 기여하는 신호 특성 식별.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import hilbert, welch
from scipy.stats import skew, kurtosis
from scipy.interpolate import CubicSpline

from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge, Lasso
from sklearn.svm import SVR
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import LeaveOneOut, cross_val_predict
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

sys.path.insert(0, str(Path(__file__).parent.parent))
from thztds.io import load_measurement_set_with_refs
from thztds.signal import compute_fft

# ── Paths ─────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "MeaData" / "260406_Temp"
FIG_DIR = Path(__file__).parent.parent / "figures" / "paper_260406"
CSV_DIR = Path(__file__).parent.parent / "results" / "paper_260406"

FIG_DIR.mkdir(parents=True, exist_ok=True)
CSV_DIR.mkdir(parents=True, exist_ok=True)

DPI = 600
plt.rcParams.update({
    "font.family": "Arial", "font.size": 10,
    "axes.labelsize": 11, "axes.titlesize": 11,
    "xtick.labelsize": 9, "ytick.labelsize": 9,
    "legend.fontsize": 8, "savefig.dpi": DPI,
    "savefig.bbox": "tight", "savefig.pad_inches": 0.08,
})


# ══════════════════════════════════════════════════════════════════
# FEATURE EXTRACTION — raw time-domain signal
# ══════════════════════════════════════════════════════════════════

def extract_features_from_signal(time_ps, signal, ref_time_ps=None, ref_signal=None):
    """Extract comprehensive features from a single THz time-domain signal.

    Returns dict of named features.
    """
    f = {}
    t, s = time_ps, signal

    # ── 1. Peak characteristics ──
    pos_idx = np.argmax(s)
    neg_idx = np.argmin(s)
    f["peak_pos_amp"] = s[pos_idx]
    f["peak_neg_amp"] = s[neg_idx]
    f["peak_pos_time"] = t[pos_idx]
    f["peak_neg_time"] = t[neg_idx]
    f["p2p_amp"] = s[pos_idx] - s[neg_idx]
    f["p2p_time"] = t[neg_idx] - t[pos_idx]

    # ── 2. Signal statistics (around main pulse ±3 ps) ──
    t0 = t[pos_idx]
    pulse_mask = (t >= t0 - 3) & (t <= t0 + 3)
    s_pulse = s[pulse_mask]
    f["pulse_rms"] = np.sqrt(np.mean(s_pulse**2))
    f["pulse_std"] = np.std(s_pulse)
    f["pulse_skewness"] = skew(s_pulse)
    f["pulse_kurtosis"] = kurtosis(s_pulse)
    f["pulse_energy"] = np.trapezoid(s_pulse**2, t[pulse_mask])

    # ── 3. Rise/fall time ──
    peak_val = s[pos_idx]
    s_before = s[:pos_idx]
    t10_idx = np.where(s_before > 0.1 * peak_val)[0]
    t90_idx = np.where(s_before > 0.9 * peak_val)[0]
    if len(t10_idx) > 0 and len(t90_idx) > 0:
        f["rise_time"] = t[t90_idx[0]] - t[t10_idx[0]]
    else:
        f["rise_time"] = 0

    s_after = s[pos_idx:]
    t90_fall = np.where(s_after < 0.9 * peak_val)[0]
    t10_fall = np.where(s_after < 0.1 * peak_val)[0]
    if len(t90_fall) > 0 and len(t10_fall) > 0:
        f["fall_time"] = t[pos_idx + t10_fall[0]] - t[pos_idx + t90_fall[0]]
    else:
        f["fall_time"] = 0

    # ── 4. Envelope features ──
    env = np.abs(hilbert(s))
    env_pulse = env[pulse_mask]
    env_max_idx = np.argmax(env_pulse)
    f["env_peak"] = env_pulse[env_max_idx]
    hm = env_pulse[env_max_idx] / 2
    above = env_pulse > hm
    if np.any(above):
        first = np.argmax(above)
        last = len(above) - 1 - np.argmax(above[::-1])
        f["env_fwhm"] = t[pulse_mask][last] - t[pulse_mask][first]
    else:
        f["env_fwhm"] = 0

    # Envelope asymmetry
    t_pulse = t[pulse_mask]
    env_peak_t = t_pulse[env_max_idx]
    left_mask = t_pulse < env_peak_t
    right_mask = t_pulse > env_peak_t
    area_l = np.trapezoid(env_pulse[left_mask], t_pulse[left_mask]) if np.any(left_mask) else 0
    area_r = np.trapezoid(env_pulse[right_mask], t_pulse[right_mask]) if np.any(right_mask) else 0
    f["env_asymmetry"] = (area_r - area_l) / (area_r + area_l) if (area_r + area_l) > 0 else 0

    # ── 5. Zero-crossing count ──
    s_roi = s[pulse_mask]
    zc = np.sum(np.diff(np.sign(s_roi)) != 0)
    f["zero_crossings"] = zc

    # ── 6. Noise level (pre-pulse RMS) ──
    noise_mask = t < (t0 - 5)
    if np.sum(noise_mask) > 10:
        f["noise_rms"] = np.sqrt(np.mean(s[noise_mask]**2))
        f["snr_db"] = 20 * np.log10(abs(s[pos_idx]) / f["noise_rms"]) if f["noise_rms"] > 0 else 60
    else:
        f["noise_rms"] = 0
        f["snr_db"] = 60

    # ── 7. Reference-relative features (if ref provided) ──
    if ref_signal is not None and ref_time_ps is not None:
        tr, sr = ref_time_ps, ref_signal
        ref_pos = np.argmax(sr)
        ref_neg = np.argmin(sr)

        # Time delays
        # Interpolate for sub-sample precision
        for sig_arr, t_arr, prefix in [(s, t, "sam"), (sr, tr, "ref")]:
            pi = np.argmax(sig_arr)
            win = max(0, pi - 5), min(len(sig_arr), pi + 6)
            t_fine = np.linspace(t_arr[win[0]], t_arr[win[1]-1], 100)
            cs = CubicSpline(t_arr[win[0]:win[1]], sig_arr[win[0]:win[1]])
            f[f"{prefix}_peak_fine"] = t_fine[np.argmax(cs(t_fine))]

        f["dt_pos"] = (f["sam_peak_fine"] - f["ref_peak_fine"]) * 1000  # fs

        # Amplitude ratios
        f["amp_ratio_pos"] = s[pos_idx] / sr[ref_pos] if sr[ref_pos] != 0 else 1
        f["amp_ratio_neg"] = s[neg_idx] / sr[ref_neg] if sr[ref_neg] != 0 else 1
        f["p2p_ratio"] = f["p2p_amp"] / (sr[ref_pos] - sr[ref_neg])

        # Delta signal features
        min_len = min(len(s), len(sr))
        delta = s[:min_len] - sr[:min_len]
        d_mask = (t[:min_len] >= t0 - 3) & (t[:min_len] <= t0 + 3)
        if np.any(d_mask):
            f["delta_rms"] = np.sqrt(np.mean(delta[d_mask]**2))
            f["delta_max"] = np.max(np.abs(delta[d_mask]))
        else:
            f["delta_rms"] = 0
            f["delta_max"] = 0

        # Clean up temporary keys
        del f["sam_peak_fine"], f["ref_peak_fine"]

    # ── 8. Frequency domain features ──
    dt = np.mean(np.diff(t)) * 1e-12  # ps → s
    n_pts = len(s)
    freq = np.fft.rfftfreq(n_pts, dt)
    spectrum = np.fft.rfft(s * np.hanning(n_pts))
    amp = np.abs(spectrum)
    phase = np.unwrap(np.angle(spectrum))
    freq_thz = freq / 1e12

    # Band-limited features
    bands = [(0.3, 0.8, "low"), (0.8, 1.5, "mid"), (1.5, 2.5, "high")]
    for f_lo, f_hi, label in bands:
        mask = (freq_thz >= f_lo) & (freq_thz <= f_hi)
        if np.any(mask):
            f[f"spec_mean_{label}"] = np.mean(amp[mask])
            f[f"spec_std_{label}"] = np.std(amp[mask])
            f[f"phase_slope_{label}"] = np.polyfit(freq[mask], phase[mask], 1)[0] if np.sum(mask) > 2 else 0
        else:
            f[f"spec_mean_{label}"] = 0
            f[f"spec_std_{label}"] = 0
            f[f"phase_slope_{label}"] = 0

    # Spectral centroid
    valid = (freq_thz >= 0.3) & (freq_thz <= 2.5) & (amp > 0)
    if np.any(valid):
        f["spec_centroid"] = np.sum(freq_thz[valid] * amp[valid]) / np.sum(amp[valid])
        f["spec_bandwidth"] = np.sqrt(
            np.sum((freq_thz[valid] - f["spec_centroid"])**2 * amp[valid]) / np.sum(amp[valid])
        )
    else:
        f["spec_centroid"] = 0
        f["spec_bandwidth"] = 0

    # Peak frequency
    valid2 = (freq_thz >= 0.1) & (freq_thz <= 3.0)
    if np.any(valid2):
        f["peak_freq"] = freq_thz[valid2][np.argmax(amp[valid2])]
    else:
        f["peak_freq"] = 0

    return f


def build_feature_matrix(refs, samples):
    """Build feature matrix X and target vector y from all measurements."""
    print("Extracting features from raw signals...")
    rows = []
    temps_list = sorted(refs.keys())

    for temp in temps_list:
        ref = refs[temp]
        for rep in range(1, 6):
            key = (temp, rep)
            if key not in samples:
                continue
            sam = samples[key]
            feats = extract_features_from_signal(
                sam.time_ps, sam.signal,
                ref_time_ps=ref.time_ps, ref_signal=ref.signal,
            )
            feats["temperature"] = temp
            feats["replicate"] = rep
            rows.append(feats)
            print(f"  {temp}°C S{rep}", end="  ")
    print()

    df = pd.DataFrame(rows)
    feature_cols = [c for c in df.columns if c not in ("temperature", "replicate")]
    X = df[feature_cols].values.astype(float)
    y = df["temperature"].values.astype(float)

    # Handle NaN/Inf
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    print(f"  Feature matrix: {X.shape[0]} samples × {X.shape[1]} features")
    return X, y, feature_cols, df


# ══════════════════════════════════════════════════════════════════
# FEATURE SELECTION (VIF + physics-based)
# ══════════════════════════════════════════════════════════════════

def compute_vif(X, feature_names):
    """Compute Variance Inflation Factor for each feature."""
    from sklearn.linear_model import LinearRegression
    vifs = []
    for i in range(X.shape[1]):
        others = np.delete(X, i, axis=1)
        if others.shape[1] == 0:
            vifs.append(1.0)
            continue
        reg = LinearRegression().fit(others, X[:, i])
        r2 = reg.score(others, X[:, i])
        vifs.append(1 / (1 - r2) if r2 < 1.0 else 1e6)
    return pd.DataFrame({"Feature": feature_names, "VIF": vifs}).sort_values("VIF", ascending=False)


# Physics-priority features (n(T) proxies)
PHYSICS_PRIORITY = [
    "p2p_amp", "p2p_ratio", "dt_pos", "amp_ratio_pos", "amp_ratio_neg",
    "peak_pos_amp", "peak_neg_amp", "peak_pos_time", "peak_neg_time",
    "rise_time", "env_fwhm", "env_asymmetry", "pulse_energy",
    "spec_centroid", "spec_mean_low", "phase_slope_low",
]


def select_features(X, y, feature_names, vif_threshold=10, max_features=15):
    """Select features: physics priority + VIF filter."""
    print("\nFeature selection (physics + VIF)...")

    # Step 1: VIF analysis on all features
    scaler = StandardScaler()
    X_sc = scaler.fit_transform(X)
    vif_df = compute_vif(X_sc, list(feature_names))
    print(f"  VIF > {vif_threshold}: {(vif_df['VIF'] > vif_threshold).sum()}/{len(vif_df)} features")

    # Step 2: Start with physics-priority features that exist
    available = set(feature_names)
    selected = [f for f in PHYSICS_PRIORITY if f in available]

    # Step 3: Iteratively remove highest-VIF feature if VIF > threshold
    selected_idx = [list(feature_names).index(f) for f in selected]
    X_sel = X_sc[:, selected_idx]

    removed = []
    while X_sel.shape[1] > 2:
        vif_sel = compute_vif(X_sel, selected)
        max_vif = vif_sel["VIF"].max()
        if max_vif <= vif_threshold:
            break
        worst = vif_sel.loc[vif_sel["VIF"].idxmax(), "Feature"]
        selected.remove(worst)
        removed.append(worst)
        selected_idx = [list(feature_names).index(f) for f in selected]
        X_sel = X_sc[:, selected_idx]

    # Step 4: Add remaining non-physics features by correlation with y (up to max)
    if len(selected) < max_features:
        remaining = [f for f in feature_names if f not in selected and f not in removed]
        corrs = []
        for f in remaining:
            idx = list(feature_names).index(f)
            r = np.abs(np.corrcoef(X[:, idx], y)[0, 1])
            corrs.append((f, r))
        corrs.sort(key=lambda x: x[1], reverse=True)
        for f, r in corrs:
            if len(selected) >= max_features:
                break
            # Check VIF with current set
            trial = selected + [f]
            trial_idx = [list(feature_names).index(ff) for ff in trial]
            trial_vif = compute_vif(X_sc[:, trial_idx], trial)
            if trial_vif["VIF"].max() <= vif_threshold:
                selected.append(f)

    selected_idx = [list(feature_names).index(f) for f in selected]
    X_out = X[:, selected_idx]

    print(f"  Selected: {len(selected)}/{len(feature_names)} features")
    print(f"  Removed (high VIF): {removed[:5]}{'...' if len(removed) > 5 else ''}")
    for f in selected:
        idx = list(feature_names).index(f)
        r = np.abs(np.corrcoef(X[:, idx], y)[0, 1])
        phy = "★" if f in PHYSICS_PRIORITY else " "
        print(f"    {phy} {f:>25s}  |r|={r:.3f}")

    return X_out, selected


# ══════════════════════════════════════════════════════════════════
# MODEL TRAINING & EVALUATION
# ══════════════════════════════════════════════════════════════════

def make_loto_cv(y):
    """Leave-One-Temperature-Out CV: hold out all replicates of one temperature."""
    temps = y.copy()
    unique_temps = sorted(set(temps))
    folds = []
    for t_out in unique_temps:
        test_idx = np.where(temps == t_out)[0]
        train_idx = np.where(temps != t_out)[0]
        folds.append((train_idx, test_idx))
    return folds


def train_and_evaluate(X, y, feature_names):
    """Train multiple models with both LOO-CV and LOTO-CV."""
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    loo = LeaveOneOut()
    loto = make_loto_cv(y)

    models = {
        "Ridge": Ridge(alpha=1.0),
        "Lasso": Lasso(alpha=0.1, max_iter=5000),
        "SVR (RBF)": SVR(kernel="rbf", C=100, epsilon=1.0),
        "Random Forest": RandomForestRegressor(n_estimators=200, max_depth=5, random_state=42),
        "Gradient Boosting": GradientBoostingRegressor(
            n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42),
    }

    results_loo = {}
    results_loto = {}

    for cv_name, cv, results_dict in [("LOO-CV", loo, results_loo),
                                       ("LOTO-CV", loto, results_loto)]:
        print(f"\nTraining models ({cv_name})...")
        for name, model in models.items():
            use_scaled = name not in ("Random Forest", "Gradient Boosting")
            X_in = X_scaled if use_scaled else X

            y_pred = cross_val_predict(model, X_in, y, cv=cv)
            mae = mean_absolute_error(y, y_pred)
            rmse = np.sqrt(mean_squared_error(y, y_pred))
            r2 = r2_score(y, y_pred)

            results_dict[name] = {"y_pred": y_pred, "MAE": mae, "RMSE": rmse, "R2": r2}
            print(f"  {name:>20s}: MAE={mae:.2f}°C, RMSE={rmse:.2f}°C, R²={r2:.3f}")

    # Best model by LOTO-CV (stricter)
    best_name = max(results_loto, key=lambda k: results_loto[k]["R2"])
    print(f"\n  Best model (LOTO-CV): {best_name} (R²={results_loto[best_name]['R2']:.3f})")

    # Retrain on full data for feature importance
    best_model_def = models[best_name]
    X_best = X if best_name not in ("Ridge", "Lasso", "SVR (RBF)") else X_scaled
    best_model_def.fit(X_best, y)

    if hasattr(best_model_def, "feature_importances_"):
        importances = best_model_def.feature_importances_
    elif hasattr(best_model_def, "coef_"):
        importances = np.abs(best_model_def.coef_)
    else:
        importances = np.zeros(len(feature_names))

    importance_df = pd.DataFrame({
        "Feature": feature_names,
        "Importance": importances,
    }).sort_values("Importance", ascending=False)

    return results_loo, results_loto, best_name, best_model_def, importance_df


def ablation_study(X, y, feature_names):
    """Ablation: compare full ML vs single-feature baselines."""
    print("\nAblation Study...")
    scaler = StandardScaler()
    loto = make_loto_cv(y)
    model = Lasso(alpha=0.1, max_iter=5000)

    # Full model (all selected features)
    X_sc = scaler.fit_transform(X)
    y_pred_full = cross_val_predict(model, X_sc, y, cv=loto)
    r2_full = r2_score(y, y_pred_full)
    mae_full = mean_absolute_error(y, y_pred_full)

    # Single best feature only
    rows = [{"Features": f"All {len(feature_names)}", "R2": r2_full, "MAE": mae_full}]

    for feat in feature_names:
        idx = list(feature_names).index(feat)
        X_single = X[:, idx:idx+1]
        X_single_sc = StandardScaler().fit_transform(X_single)
        y_pred_s = cross_val_predict(Ridge(alpha=1.0), X_single_sc, y, cv=loto)
        r2_s = r2_score(y, y_pred_s)
        mae_s = mean_absolute_error(y, y_pred_s)
        rows.append({"Features": feat, "R2": r2_s, "MAE": mae_s})

    rows.sort(key=lambda r: r["R2"], reverse=True)
    print(f"  {'Features':>25s}  {'R²':>6}  {'MAE':>7}")
    print("  " + "-" * 42)
    for r in rows[:8]:
        marker = "★" if r["Features"].startswith("All") else " "
        print(f"  {marker}{r['Features']:>24s}  {r['R2']:>6.3f}  {r['MAE']:>6.2f}°C")

    pd.DataFrame(rows).to_csv(CSV_DIR / "ml_ablation.csv", index=False)
    return rows


# ══════════════════════════════════════════════════════════════════
# FIGURES
# ══════════════════════════════════════════════════════════════════

def save_fig(fig, name):
    fig.savefig(FIG_DIR / f"{name}.png")
    fig.savefig(FIG_DIR / f"{name}.pdf")
    plt.close(fig)
    print(f"  -> {name}")


def fig_model_comparison(results, y_true):
    """Bar chart comparing model performance."""
    print("Fig: Model comparison...")
    names = list(results.keys())
    maes = [results[n]["MAE"] for n in names]
    r2s = [results[n]["R2"] for n in names]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14 / 2.54, 5.5 / 2.54))
    colors = ["#2166AC" if r > 0.5 else "#BBBBBB" for r in r2s]

    ax1.barh(range(len(names)), maes, color=colors, height=0.6)
    ax1.set_yticks(range(len(names)))
    ax1.set_yticklabels(names)
    ax1.set_xlabel("MAE (°C)")
    ax1.invert_yaxis()

    ax2.barh(range(len(names)), r2s, color=colors, height=0.6)
    ax2.set_yticks(range(len(names)))
    ax2.set_yticklabels([])
    ax2.set_xlabel("R²")
    ax2.set_xlim(0, 1.05)
    ax2.invert_yaxis()

    fig.tight_layout(w_pad=1.0)
    save_fig(fig, "fig_ml_model_comparison")


def fig_prediction_scatter(results, best_name, y_true):
    """Predicted vs actual temperature scatter for best model."""
    print("Fig: Prediction scatter...")
    y_pred = results[best_name]["y_pred"]
    r2 = results[best_name]["R2"]
    mae = results[best_name]["MAE"]

    fig, ax = plt.subplots(figsize=(8 / 2.54, 8 / 2.54))
    ax.scatter(y_true, y_pred, c=y_true, cmap="coolwarm", s=25, edgecolors="black",
               linewidths=0.3, zorder=5)
    ax.plot([15, 115], [15, 115], "k--", lw=0.6, alpha=0.5)

    ax.set_xlabel(r"Actual temperature ($\degree$C)")
    ax.set_ylabel(r"Predicted temperature ($\degree$C)")
    ax.set_xlim(15, 115)
    ax.set_ylim(15, 115)
    ax.set_aspect("equal")
    ax.text(0.05, 0.95, f"{best_name}\nR² = {r2:.3f}\nMAE = {mae:.1f} °C",
            transform=ax.transAxes, va="top", fontsize=8,
            bbox=dict(boxstyle="round", fc="white", alpha=0.8, pad=0.3))

    fig.tight_layout()
    save_fig(fig, "fig_ml_prediction_scatter")


def fig_feature_importance(importance_df, top_n=15):
    """Horizontal bar chart of top feature importances."""
    print("Fig: Feature importance...")
    top = importance_df.head(top_n)

    fig, ax = plt.subplots(figsize=(10 / 2.54, 8 / 2.54))
    y_pos = np.arange(len(top))
    ax.barh(y_pos, top["Importance"].values, height=0.6, color="#2166AC", edgecolor="none")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(top["Feature"].values)
    ax.set_xlabel("Feature importance")
    ax.invert_yaxis()

    fig.tight_layout()
    save_fig(fig, "fig_ml_feature_importance")


def fig_prediction_by_temp(results, best_name, y_true, df):
    """Box plot of prediction error by temperature."""
    print("Fig: Prediction error by temperature...")
    y_pred = results[best_name]["y_pred"]
    errors = y_pred - y_true
    temps = df["temperature"].values

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14 / 2.54, 5.5 / 2.54))

    # Left: mean prediction per temperature
    unique_temps = sorted(set(temps))
    pred_means = [np.mean(y_pred[temps == t]) for t in unique_temps]
    pred_stds = [np.std(y_pred[temps == t]) for t in unique_temps]
    ax1.errorbar(unique_temps, pred_means, yerr=pred_stds, fmt="o-", markersize=4,
                 capsize=2.5, color="#d62728", lw=0.9, label="Predicted")
    ax1.plot([15, 115], [15, 115], "k--", lw=0.5, alpha=0.5, label="Ideal")
    ax1.set_xlabel(r"Actual temperature ($\degree$C)")
    ax1.set_ylabel(r"Predicted temperature ($\degree$C)")
    ax1.legend(fontsize=7)

    # Right: error distribution per temperature
    error_by_temp = [errors[temps == t] for t in unique_temps]
    bp = ax2.boxplot(error_by_temp, positions=unique_temps, widths=6,
                     patch_artist=True, manage_ticks=False)
    for patch in bp["boxes"]:
        patch.set_facecolor("#2166AC")
        patch.set_alpha(0.5)
    ax2.axhline(0, color="gray", ls="--", lw=0.5)
    ax2.set_xlabel(r"Temperature ($\degree$C)")
    ax2.set_ylabel("Prediction error (°C)")

    fig.tight_layout(w_pad=1.5)
    save_fig(fig, "fig_ml_error_by_temp")


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("THz-TDS Temperature Prediction — ML Pipeline v2")
    print("  (VIF feature selection + LOTO-CV)")
    print("=" * 60)

    # Load data
    refs, samples = load_measurement_set_with_refs(DATA_DIR)
    print(f"  Loaded: {len(refs)} refs, {len(samples)} samples")

    # Extract all features
    X_all, y, all_feature_names, df = build_feature_matrix(refs, samples)

    # Feature selection (VIF + physics)
    X_sel, sel_feature_names = select_features(X_all, y, all_feature_names)

    # Train & evaluate with both CV strategies
    results_loo, results_loto, best_name, best_model, importance_df = \
        train_and_evaluate(X_sel, y, sel_feature_names)

    # ── LOO vs LOTO comparison table ──
    print(f"\n{'='*60}")
    print("LOO-CV vs LOTO-CV Comparison")
    print(f"{'='*60}")
    print(f"  {'Model':>20s}  {'LOO R²':>8}  {'LOTO R²':>8}  {'LOO MAE':>8}  {'LOTO MAE':>8}  {'Δ R²':>6}")
    print("  " + "-" * 65)
    comp_rows = []
    for name in results_loo:
        lr2 = results_loo[name]["R2"]
        tr2 = results_loto[name]["R2"]
        lm = results_loo[name]["MAE"]
        tm = results_loto[name]["MAE"]
        print(f"  {name:>20s}  {lr2:>8.3f}  {tr2:>8.3f}  {lm:>7.2f}°C  {tm:>7.2f}°C  {lr2-tr2:>+6.3f}")
        comp_rows.append({"Model": name, "LOO_R2": f"{lr2:.3f}", "LOTO_R2": f"{tr2:.3f}",
                          "LOO_MAE": f"{lm:.2f}", "LOTO_MAE": f"{tm:.2f}",
                          "delta_R2": f"{lr2-tr2:+.3f}"})

    # Ablation study
    ablation_rows = ablation_study(X_sel, y, sel_feature_names)

    # Export
    importance_df.to_csv(CSV_DIR / "ml_feature_importance.csv", index=False)
    pd.DataFrame(comp_rows).to_csv(CSV_DIR / "ml_cv_comparison.csv", index=False)

    pred_df = df[["temperature", "replicate"]].copy()
    for name, res in results_loto.items():
        pred_df[f"pred_LOTO_{name}"] = res["y_pred"]
    for name, res in results_loo.items():
        pred_df[f"pred_LOO_{name}"] = res["y_pred"]
    pred_df.to_csv(CSV_DIR / "ml_predictions.csv", index=False)

    summary = []
    for name in results_loto:
        summary.append({
            "Model": name,
            "LOO_MAE": f"{results_loo[name]['MAE']:.2f}",
            "LOO_R2": f"{results_loo[name]['R2']:.3f}",
            "LOTO_MAE": f"{results_loto[name]['MAE']:.2f}",
            "LOTO_R2": f"{results_loto[name]['R2']:.3f}",
        })
    pd.DataFrame(summary).to_csv(CSV_DIR / "ml_model_summary.csv", index=False)

    # Figures — use LOTO-CV results (stricter)
    print(f"\n{'='*60}\nGenerating ML Figures\n{'='*60}")
    fig_model_comparison(results_loto, y)
    fig_prediction_scatter(results_loto, best_name, y)
    fig_feature_importance(importance_df)
    fig_prediction_by_temp(results_loto, best_name, y, df)

    # Summary
    best_loto = results_loto[best_name]
    best_loo = results_loo[best_name]
    print(f"\n{'='*60}")
    print("ML PIPELINE SUMMARY")
    print(f"{'='*60}")
    print(f"  Features: {len(all_feature_names)} → {len(sel_feature_names)} (VIF+physics selection)")
    print(f"  Samples: {X_all.shape[0]} (10 temps × 5 reps)")
    print(f"  Best model: {best_name}")
    print(f"  LOO-CV:  MAE={best_loo['MAE']:.2f}°C, R²={best_loo['R2']:.3f}")
    print(f"  LOTO-CV: MAE={best_loto['MAE']:.2f}°C, R²={best_loto['R2']:.3f}")
    print(f"  Δ R² (LOO−LOTO): {best_loo['R2']-best_loto['R2']:+.3f}")
    print(f"\n  Top 5 predictive features:")
    for i, (_, row) in enumerate(importance_df.head(5).iterrows()):
        phy = "★" if row["Feature"] in PHYSICS_PRIORITY else " "
        print(f"    {phy} {row['Feature']} ({row['Importance']:.4f})")
    print(f"\n  Figures: {FIG_DIR}/")
    print(f"  Tables: {CSV_DIR}/")
    print("\nDone.")


if __name__ == "__main__":
    main()
