"""PE40 (260406_Temp) 온도별 THz-TDS 종합 분석.

PE20 분리막 2장 겹침 (40 um).
3가지 방법론(Matched Ref, Method2, Method3) + 5개 분석 도메인 적용.
최적 방법론 도출 포함.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline
from scipy.ndimage import median_filter
from scipy.signal import hilbert, savgol_filter
from scipy.stats import pearsonr, linregress

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.ticker as ticker
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).parent.parent))

from thztds.io import load_measurement_set_with_refs, parse_menlo_file
from thztds.signal import compute_fft, apply_window
from thztds.transfer_function import compute_measured_transfer_function
from thztds.types import ExtractionConfig, THzTimeDomainData
from thztds.optical_properties import (
    process_temperature_series_matched_ref,
    compute_temperature_averages,
)
from thztds.constants import PI

# ── Paths ────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "MeaData" / "260406_Temp"
FIG_DIR = Path(__file__).parent.parent / "figures" / "report_260406"
CSV_DIR = Path(__file__).parent.parent / "results" / "260406_Temp"

TEMPS = list(range(20, 115, 10))
THICKNESS_MM = 0.04  # 20 um x 2 sheets

# ── Figure style ─────────────────────────────────────────────────
CM = 1 / 2.54
FIG_W = 4.0 * CM
FIG_H = 4.0 * CM
DPI = 600

plt.rcParams.update({
    "font.family": "Arial",
    "font.size": 7,
    "mathtext.default": "regular",
    "axes.labelsize": 7,
    "axes.titlesize": 7.5,
    "axes.linewidth": 0.5,
    "xtick.labelsize": 6,
    "ytick.labelsize": 6,
    "xtick.major.width": 0.4,
    "ytick.major.width": 0.4,
    "xtick.major.size": 2.0,
    "ytick.major.size": 2.0,
    "xtick.minor.size": 1.2,
    "ytick.minor.size": 1.2,
    "xtick.minor.width": 0.3,
    "ytick.minor.width": 0.3,
    "xtick.direction": "in",
    "ytick.direction": "in",
    "xtick.top": True,
    "ytick.right": True,
    "lines.linewidth": 0.7,
    "legend.fontsize": 5.5,
    "legend.handlelength": 1.2,
    "legend.handletextpad": 0.4,
    "legend.borderpad": 0.3,
    "legend.labelspacing": 0.25,
    "legend.frameon": True,
    "legend.edgecolor": "0.8",
    "legend.fancybox": False,
    "savefig.dpi": DPI,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
})

# ── Temperature color map ────────────────────────────────────────
_TEMP_COLORS = [
    "#3B4CC0", "#5A7BC6", "#7AAAD0", "#9DC8D9", "#BDDDDD",
    "#E8C8A0", "#F0A672", "#E87B52", "#D44E3D", "#B40426",
]
_TEMP_CMAP = LinearSegmentedColormap.from_list("temp", _TEMP_COLORS, N=256)
_REP_MARKERS = ["o", "s", "^", "D", "v"]
_REP_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]


def get_temp_color(temp_c: int) -> str:
    return _TEMP_COLORS[TEMPS.index(temp_c)]


def make_temp_colorbar(ax, fig, label=r"T ($\degree$C)"):
    sm = plt.cm.ScalarMappable(cmap=_TEMP_CMAP, norm=plt.Normalize(20, 110))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.03, aspect=20, shrink=0.9)
    cbar.set_label(label, fontsize=6, labelpad=2)
    cbar.ax.tick_params(labelsize=5, width=0.3, length=1.5)
    cbar.set_ticks([20, 40, 60, 80, 100])
    return cbar


def save_fig(fig, name):
    fig.savefig(FIG_DIR / f"{name}.png")
    fig.savefig(FIG_DIR / f"{name}.pdf")
    plt.close(fig)
    print(f"  -> {name}")


def auto_ylim(ax, margin=0.08):
    """Auto-fit y-axis to data range with margin, excluding empty regions."""
    from matplotlib.collections import PathCollection
    all_y = []
    for line in ax.get_lines():
        yd = np.asarray(line.get_ydata(), dtype=float)
        finite = yd[np.isfinite(yd)]
        if len(finite) > 0:
            all_y.extend(finite)
    for coll in ax.collections:
        if not isinstance(coll, PathCollection):
            continue
        offsets = coll.get_offsets()
        if len(offsets) > 0:
            yd = np.asarray(offsets[:, 1], dtype=float)
            finite = yd[np.isfinite(yd)]
            if len(finite) > 0:
                all_y.extend(finite)
    if not all_y:
        return
    ymin, ymax = np.min(all_y), np.max(all_y)
    pad = (ymax - ymin) * margin
    if pad < 1e-12:
        pad = abs(ymin) * 0.05 if abs(ymin) > 0 else 0.01
    ax.set_ylim(ymin - pad, ymax + pad)


# ── Smoothing ────────────────────────────────────────────────────
def smooth_spectrum(y, kernel=5):
    return median_filter(y, size=kernel)


def smooth_alpha(y, kernel=11, sg_window=31, sg_order=2):
    cleaned = median_filter(y, size=kernel)
    if len(cleaned) >= sg_window:
        cleaned = savgol_filter(cleaned, sg_window, sg_order)
    return cleaned


# ══════════════════════════════════════════════════════════════════
# Data Loading
# ══════════════════════════════════════════════════════════════════
def interp_signal(t, s, factor=10):
    raw_idx = np.argmax(np.abs(s))
    raw_t = t[raw_idx]
    mask = (t >= raw_t - 5) & (t <= raw_t + 5)
    t_roi, s_roi = t[mask], s[mask]
    t_fine = np.linspace(t_roi[0], t_roi[-1], len(t_roi) * factor)
    cs = CubicSpline(t_roi, s_roi)
    return t_fine, cs(t_fine), cs


# ══════════════════════════════════════════════════════════════════
# Feature Extraction (5 Domains)
# ══════════════════════════════════════════════════════════════════
def extract_all_features(ref, sam):
    """Extract features from all 5 domains for a single ref-sample pair."""
    t_r, s_r = ref.time_ps, ref.signal
    t_s, s_s = sam.time_ps, sam.signal
    tf_r, sf_r, cs_r = interp_signal(t_r, s_r)
    tf_s, sf_s, cs_s = interp_signal(t_s, s_s)

    f = {}

    # ── Domain 1: Time-domain peaks ──
    r_pos_i, r_neg_i = np.argmax(sf_r), np.argmin(sf_r)
    s_pos_i, s_neg_i = np.argmax(sf_s), np.argmin(sf_s)

    f["t_pos"] = tf_s[s_pos_i]
    f["amp_pos"] = sf_s[s_pos_i]
    f["t_neg"] = tf_s[s_neg_i]
    f["amp_neg"] = sf_s[s_neg_i]
    f["p2p"] = f["amp_pos"] - f["amp_neg"]

    f["dt_pos"] = (tf_s[s_pos_i] - tf_r[r_pos_i]) * 1000  # fs
    f["dt_neg"] = (tf_s[s_neg_i] - tf_r[r_neg_i]) * 1000
    f["dt_avg"] = (f["dt_pos"] + f["dt_neg"]) / 2
    f["amp_ratio_pos"] = sf_s[s_pos_i] / sf_r[r_pos_i] if sf_r[r_pos_i] != 0 else 0
    f["amp_ratio_neg"] = sf_s[s_neg_i] / sf_r[r_neg_i] if sf_r[r_neg_i] != 0 else 0
    f["p2p_ratio"] = f["p2p"] / (sf_r[r_pos_i] - sf_r[r_neg_i]) if (sf_r[r_pos_i] - sf_r[r_neg_i]) != 0 else 0

    # Rise time (10-90%)
    peak_val = sf_s[s_pos_i]
    s_before = sf_s[:s_pos_i]
    t10 = np.where(s_before > 0.1 * peak_val)[0]
    t90 = np.where(s_before > 0.9 * peak_val)[0]
    f["rise_time_ps"] = (tf_s[t90[0]] - tf_s[t10[0]]) if len(t10) > 0 and len(t90) > 0 else 0

    # Slope
    ds = cs_s(tf_s, 1)
    f["max_slope"] = float(np.max(ds))
    f["min_slope"] = float(np.min(ds))

    # ── Domain 2: Envelope analysis ──
    env_r = np.abs(hilbert(s_r))
    env_s = np.abs(hilbert(s_s))
    tf_er, ef_r, _ = interp_signal(t_r, env_r)
    tf_es, ef_s, _ = interp_signal(t_s, env_s)

    r_env_i = np.argmax(ef_r)
    s_env_i = np.argmax(ef_s)

    f["env_peak_t"] = tf_es[s_env_i]
    f["env_peak_amp"] = ef_s[s_env_i]
    f["dt_env"] = (tf_es[s_env_i] - tf_er[r_env_i]) * 1000

    # Envelope FWHM
    for prefix, ef, tf_e, idx_e in [("ref_", ef_r, tf_er, r_env_i), ("", ef_s, tf_es, s_env_i)]:
        hm = ef[idx_e] / 2
        above = ef > hm
        if np.any(above):
            first = np.argmax(above)
            last = len(above) - 1 - np.argmax(above[::-1])
            f[prefix + "env_fwhm"] = tf_e[last] - tf_e[first]
        else:
            f[prefix + "env_fwhm"] = 0

    f["fwhm_ratio"] = f["env_fwhm"] / f["ref_env_fwhm"] if f["ref_env_fwhm"] > 0 else 1

    # Envelope asymmetry
    area_b = np.trapz(ef_s[:s_env_i], tf_es[:s_env_i]) if s_env_i > 0 else 0
    area_a = np.trapz(ef_s[s_env_i:], tf_es[s_env_i:]) if s_env_i < len(ef_s) - 1 else 0
    f["env_asymmetry"] = (area_a - area_b) / (area_a + area_b) if (area_a + area_b) > 0 else 0

    # ── Domain 3: Delta signal ──
    delta = s_s - s_r
    raw_idx = np.argmax(np.abs(s_r))
    raw_t = t_r[raw_idx]
    d_mask = (t_r >= raw_t - 3) & (t_r <= raw_t + 3)
    d_roi, t_d = delta[d_mask], t_r[d_mask]

    f["delta_rms"] = np.sqrt(np.mean(d_roi**2))
    f["delta_p2p"] = np.ptp(d_roi)
    f["delta_area"] = np.trapz(np.abs(d_roi), t_d)
    f["delta_energy"] = np.trapz(d_roi**2, t_d)
    abs_d = np.abs(d_roi)
    f["delta_centroid"] = np.sum(t_d * abs_d) / np.sum(abs_d) if np.sum(abs_d) > 0 else 0

    # ── Domain 4: Frequency-domain ──
    ref_freq = compute_fft(ref, 2)
    sam_freq = compute_fft(sam, 2)
    H = compute_measured_transfer_function(ref_freq, sam_freq)
    freq = ref_freq.freq_hz
    freq_thz = freq / 1e12
    valid = ~np.isnan(H)

    for ft in [0.5, 1.0, 1.5]:
        mk = valid & (freq_thz >= ft - 0.05) & (freq_thz <= ft + 0.05)
        if np.any(mk):
            f[f"H_amp_{ft}"] = np.mean(np.abs(H[mk]))
            f[f"H_phase_{ft}"] = np.mean(np.unwrap(np.angle(H[mk])))

    mb = valid & (freq_thz >= 0.3) & (freq_thz <= 2.0)
    if np.any(mb):
        trans = np.abs(H[mb])
        f["H_amp_mean"] = np.mean(trans)
        f["absorption_integral"] = np.trapz(-np.log(np.clip(trans, 1e-10, None)), freq_thz[mb])
        f["H_amp_slope"] = linregress(freq_thz[mb], trans).slope

        phase = np.unwrap(np.angle(H[mb]))
        sl = linregress(freq[mb], phase)
        f["phase_slope"] = sl.slope
        f["group_delay_ps"] = -sl.slope / (2 * PI) * 1e12
        f["phase_residual_rms"] = np.sqrt(np.mean((phase - sl.slope * freq[mb] - sl.intercept) ** 2))

    # Spectral centroid
    sam_amp = sam_freq.amplitude
    mk_s = (freq_thz >= 0.3) & (freq_thz <= 2.0) & (sam_amp > 0)
    if np.any(mk_s):
        c_s = np.sum(freq_thz[mk_s] * sam_amp[mk_s]) / np.sum(sam_amp[mk_s])
        f["centroid_sam"] = c_s
        f["bandwidth_sam"] = np.sqrt(np.sum(sam_amp[mk_s] * (freq_thz[mk_s] - c_s) ** 2) / np.sum(sam_amp[mk_s]))

    return f


def extract_all_temperatures(refs, samples):
    """Extract features for all temperatures and replicates."""
    all_data = {}
    for temp in sorted(refs.keys()):
        ref = refs[temp]
        rep_features = []
        for rep in range(1, 6):
            key = (temp, rep)
            if key not in samples:
                continue
            rep_features.append(extract_all_features(ref, samples[key]))

        if not rep_features:
            continue

        avg = {}
        for k in rep_features[0]:
            vals = [rf[k] for rf in rep_features if k in rf]
            avg[k] = {"mean": np.mean(vals), "std": np.std(vals), "reps": vals}
        all_data[temp] = avg

    return all_data


# ══════════════════════════════════════════════════════════════════
# Dielectric Constant
# ══════════════════════════════════════════════════════════════════
def compute_dielectric(averages):
    dielectric = {}
    for temp, props in averages.items():
        n, kappa = props.n, props.kappa
        n_std = props.n_std if props.n_std is not None else np.zeros_like(n)
        kappa_std = props.kappa_std if props.kappa_std is not None else np.zeros_like(kappa)
        dielectric[temp] = {
            "freq_thz": props.freq_thz,
            "eps_real": n**2 - kappa**2,
            "eps_imag": 2 * n * kappa,
            "eps_real_std": np.sqrt((2 * n * n_std) ** 2 + (2 * kappa * kappa_std) ** 2),
            "eps_imag_std": np.sqrt((2 * kappa * n_std) ** 2 + (2 * n * kappa_std) ** 2),
        }
    return dielectric


# ══════════════════════════════════════════════════════════════════
# Correlation Analysis
# ══════════════════════════════════════════════════════════════════
def correlate_features(all_data, temps_list):
    """Compute Pearson correlation for sample-specific features vs temperature.

    Excludes absolute features (amp_pos, amp_neg, p2p, etc.) that reflect
    reference/system changes rather than sample properties.
    """
    # Only include relative features (ratio, delay, difference-based)
    SAMPLE_SPECIFIC = {
        "dt_pos", "dt_neg", "dt_avg", "dt_env",
        "amp_ratio_pos", "amp_ratio_neg", "p2p_ratio", "fwhm_ratio",
        "env_asymmetry",
        "delta_rms", "delta_p2p", "delta_area", "delta_energy", "delta_centroid",
        "H_amp_0.5", "H_amp_1.0", "H_amp_1.5", "H_amp_mean",
        "H_amp_slope", "absorption_integral",
        "phase_slope", "group_delay_ps", "phase_residual_rms",
        "centroid_sam", "bandwidth_sam",
        "rise_time_ps",
    }

    results = []
    for fk in sorted(SAMPLE_SPECIFIC):
        ts, vs = [], []
        for temp in temps_list:
            if temp in all_data and fk in all_data[temp]:
                ts.append(temp)
                vs.append(all_data[temp][fk]["mean"])
        if len(ts) < 5:
            continue
        t_arr, v_arr = np.array(ts, dtype=float), np.array(vs, dtype=float)
        ok = np.isfinite(v_arr)
        if np.sum(ok) < 5:
            continue
        r, p = pearsonr(t_arr[ok], v_arr[ok])
        sl = linregress(t_arr[ok], v_arr[ok])
        results.append({
            "name": fk, "R": r, "R2": r**2, "p": p,
            "slope": sl.slope, "intercept": sl.intercept,
        })

    results.sort(key=lambda x: abs(x["R"]), reverse=True)
    return results


# ══════════════════════════════════════════════════════════════════
# FIGURES
# ══════════════════════════════════════════════════════════════════

def plot_time_domain_zoom(refs, samples):
    """Fig 1: Zoomed view around peak showing attenuation and delay."""
    print("Fig 1: Time-domain zoom (peak region)...")
    fig, axes = plt.subplots(2, 5, figsize=(FIG_W * 5, FIG_H * 2))
    axes = axes.flatten()

    for i, temp in enumerate(TEMPS):
        ax = axes[i]
        if temp not in refs:
            ax.set_visible(False)
            continue

        ref = refs[temp]
        tf_r, sf_r, _ = interp_signal(ref.time_ps, ref.signal)
        ref_peak_t = tf_r[np.argmax(sf_r)]

        ax.plot(ref.time_ps - ref_peak_t, ref.signal,
                color="black", lw=0.9, zorder=10, label="Ref")

        for rep in range(1, 6):
            key = (temp, rep)
            if key in samples:
                td = samples[key]
                ax.plot(td.time_ps - ref_peak_t, td.signal,
                        color=get_temp_color(temp), lw=0.4, alpha=0.7)

        # Zoom to peak region — tight y-axis
        ax.set_xlim(-1.5, 2.0)
        auto_ylim(ax)
        ax.set_title(f"{temp}" + r"$\degree$C", fontsize=7)
        if i >= 5:
            ax.set_xlabel("Time (ps)")
        if i % 5 == 0:
            ax.set_ylabel("Amplitude (a.u.)")

    fig.tight_layout()
    save_fig(fig, "fig01_time_domain_zoom")


def plot_peak_detail(refs, samples):
    """Fig 2: Single combined plot — peak attenuation & delay visible."""
    print("Fig 2: Peak detail (all temps overlaid)...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(FIG_W * 2, FIG_H))

    # Use 20°C ref as time reference
    ref20 = refs[20]
    tf_20, sf_20, _ = interp_signal(ref20.time_ps, ref20.signal)
    t_shift = tf_20[np.argmax(sf_20)]

    # Left: positive peak zoom
    for temp in TEMPS:
        if temp not in refs:
            continue
        key = (temp, 1)
        if key not in samples:
            continue
        td = samples[key]
        ax1.plot(td.time_ps - t_shift, td.signal,
                 color=get_temp_color(temp), lw=0.6)
    ax1.plot(ref20.time_ps - t_shift, ref20.signal, color="black", lw=0.9, zorder=10)

    ax1.set_xlim(-0.3, 0.5)
    auto_ylim(ax1)
    ax1.set_xlabel("Time (ps)")
    ax1.set_ylabel("Amplitude (a.u.)")
    ax1.set_title("Positive peak", fontsize=7)

    # Right: negative peak zoom
    tf_r, sf_r, _ = interp_signal(ref20.time_ps, ref20.signal)
    neg_peak_t = tf_r[np.argmin(sf_r)] - t_shift

    for temp in TEMPS:
        if temp not in refs:
            continue
        key = (temp, 1)
        if key not in samples:
            continue
        td = samples[key]
        ax2.plot(td.time_ps - t_shift, td.signal,
                 color=get_temp_color(temp), lw=0.6)
    ax2.plot(ref20.time_ps - t_shift, ref20.signal, color="black", lw=0.9, zorder=10)

    ax2.set_xlim(neg_peak_t - 0.3, neg_peak_t + 0.3)
    auto_ylim(ax2)
    ax2.set_xlabel("Time (ps)")
    ax2.set_title("Negative peak", fontsize=7)

    make_temp_colorbar(ax2, fig)
    fig.tight_layout()
    save_fig(fig, "fig02_peak_detail")


def plot_per_sample_time_delay(all_data, temps_list):
    """Fig 4: Per-sample time delay vs temperature (5 individual lines)."""
    print("Fig 4: Per-sample time delay vs temp...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(FIG_W * 2, FIG_H))

    for rep_idx in range(5):
        dt_pos_vals, dt_neg_vals, ts = [], [], []
        for temp in temps_list:
            if temp not in all_data:
                continue
            reps_p = all_data[temp].get("dt_pos", {}).get("reps", [])
            reps_n = all_data[temp].get("dt_neg", {}).get("reps", [])
            if rep_idx < len(reps_p):
                dt_pos_vals.append(reps_p[rep_idx])
                dt_neg_vals.append(reps_n[rep_idx])
                ts.append(temp)

        label = f"S{rep_idx + 1}"
        ax1.plot(ts, dt_pos_vals, marker=_REP_MARKERS[rep_idx],
                 color=_REP_COLORS[rep_idx], markersize=2.5, lw=0.5, label=label)
        ax2.plot(ts, dt_neg_vals, marker=_REP_MARKERS[rep_idx],
                 color=_REP_COLORS[rep_idx], markersize=2.5, lw=0.5, label=label)

    # Mean with error bars
    ts_m = [t for t in temps_list if t in all_data]
    for ax, key, title in [(ax1, "dt_pos", r"$\Delta t_{+}$ (fs)"),
                           (ax2, "dt_neg", r"$\Delta t_{-}$ (fs)")]:
        means = [all_data[t][key]["mean"] for t in ts_m]
        stds = [all_data[t][key]["std"] for t in ts_m]
        ax.errorbar(ts_m, means, yerr=stds, fmt="k-", lw=1.0, capsize=2,
                    capthick=0.5, elinewidth=0.5, markersize=0, zorder=10, label="Mean")
        ax.set_xlabel(r"Temperature ($\degree$C)")
        ax.set_ylabel(title)
        auto_ylim(ax)
        ax.legend(fontsize=4.5, ncol=3, loc="best")

    fig.tight_layout()
    save_fig(fig, "fig04_per_sample_dt_vs_temp")


def plot_per_sample_amplitude(all_data, temps_list):
    """Fig 5: Per-sample amplitude ratio vs temperature."""
    print("Fig 5: Per-sample amplitude vs temp...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(FIG_W * 2, FIG_H))

    ts_m = [t for t in temps_list if t in all_data]

    for rep_idx in range(5):
        p2p_vals, ts = [], []
        arpos, arneg = [], []
        for temp in ts_m:
            reps_p2p = all_data[temp].get("p2p_ratio", {}).get("reps", [])
            reps_ap = all_data[temp].get("amp_ratio_pos", {}).get("reps", [])
            reps_an = all_data[temp].get("amp_ratio_neg", {}).get("reps", [])
            if rep_idx < len(reps_p2p):
                p2p_vals.append(reps_p2p[rep_idx])
                arpos.append(reps_ap[rep_idx])
                arneg.append(reps_an[rep_idx])
                ts.append(temp)

        label = f"S{rep_idx + 1}"
        ax1.plot(ts, p2p_vals, marker=_REP_MARKERS[rep_idx],
                 color=_REP_COLORS[rep_idx], markersize=2.5, lw=0.5, label=label)
        ax2.plot(ts, arpos, marker=_REP_MARKERS[rep_idx],
                 color=_REP_COLORS[rep_idx], markersize=2.5, lw=0.5, label=label)

    for ax, key, ylabel in [(ax1, "p2p_ratio", "P2P ratio"),
                            (ax2, "amp_ratio_pos", "Amp+ ratio")]:
        means = [all_data[t][key]["mean"] for t in ts_m]
        stds = [all_data[t][key]["std"] for t in ts_m]
        ax.errorbar(ts_m, means, yerr=stds, fmt="k-", lw=1.0, capsize=2,
                    capthick=0.5, elinewidth=0.5, markersize=0, zorder=10, label="Mean")
        ax.set_xlabel(r"Temperature ($\degree$C)")
        ax.set_ylabel(ylabel)
        auto_ylim(ax)
        ax.legend(fontsize=4.5, ncol=3, loc="best")

    fig.tight_layout()
    save_fig(fig, "fig05_per_sample_amplitude_vs_temp")


def plot_optical_props(averages, method_label, suffix):
    """n(f) and alpha(f) with auto y-axis."""
    print(f"Fig: n(f) & alpha(f) [{method_label}]...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(FIG_W * 2, FIG_H))

    for temp in TEMPS:
        if temp not in averages:
            continue
        p = averages[temp]
        f_mask = (p.freq_thz >= 0.3) & (p.freq_thz <= 2.0)
        ax1.plot(p.freq_thz[f_mask], smooth_spectrum(p.n[f_mask], 3),
                 color=get_temp_color(temp), lw=0.55)
        ax2.plot(p.freq_thz[f_mask], smooth_alpha(p.alpha[f_mask]),
                 color=get_temp_color(temp), lw=0.55)

    ax1.set_xlim(0.3, 2.0)
    ax1.set_ylabel("Refractive index, $n$")
    auto_ylim(ax1)

    ax2.set_xlim(0.3, 2.0)
    ax2.set_ylabel(r"$\alpha$ (cm$^{-1}$)")
    auto_ylim(ax2)

    for ax in [ax1, ax2]:
        ax.set_xlabel("Frequency (THz)")
        ax.xaxis.set_major_locator(ticker.MultipleLocator(0.5))

    make_temp_colorbar(ax2, fig)
    fig.suptitle(method_label, fontsize=7, y=1.01)
    fig.tight_layout()
    save_fig(fig, f"fig_{suffix}_n_alpha")


def plot_dielectric(dielectric_data, suffix):
    """Dielectric constants vs frequency."""
    print(f"Fig: Dielectric [{suffix}]...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(FIG_W * 2, FIG_H))

    for temp in TEMPS:
        if temp not in dielectric_data:
            continue
        d = dielectric_data[temp]
        f = d["freq_thz"]
        f_mask = (f >= 0.3) & (f <= 2.0)
        ax1.plot(f[f_mask], smooth_spectrum(d["eps_real"][f_mask], 3),
                 color=get_temp_color(temp), lw=0.55)
        ax2.plot(f[f_mask], smooth_spectrum(d["eps_imag"][f_mask], 5),
                 color=get_temp_color(temp), lw=0.55)

    for ax, ylabel in [(ax1, r"$\varepsilon'$"), (ax2, r"$\varepsilon''$")]:
        ax.set_xlim(0.3, 2.0)
        ax.set_xlabel("Frequency (THz)")
        ax.set_ylabel(ylabel)
        ax.xaxis.set_major_locator(ticker.MultipleLocator(0.5))
        auto_ylim(ax)

    make_temp_colorbar(ax2, fig)
    fig.tight_layout()
    save_fig(fig, f"fig_{suffix}_dielectric")


def plot_per_sample_n_vs_temp(results, temps_list, suffix):
    """Per-sample n vs temperature at selected frequencies."""
    print(f"Fig: Per-sample n vs T [{suffix}]...")
    target_freqs = [0.5, 1.0, 1.5]

    fig, axes = plt.subplots(1, 3, figsize=(FIG_W * 3, FIG_H))

    for fi, f_target in enumerate(target_freqs):
        ax = axes[fi]
        # Per-replicate
        for rep in range(1, 6):
            ts, ns = [], []
            for temp in sorted(temps_list):
                key = (temp, rep)
                if key in results:
                    p = results[key]
                    idx = np.argmin(np.abs(p.freq_thz - f_target))
                    ts.append(temp)
                    ns.append(p.n[idx])
            if ts:
                ax.plot(ts, ns, marker=_REP_MARKERS[rep - 1], color=_REP_COLORS[rep - 1],
                        markersize=2, lw=0.4, label=f"S{rep}")

        ax.set_xlabel(r"Temperature ($\degree$C)")
        ax.set_ylabel(f"$n$ @ {f_target} THz")
        auto_ylim(ax)
        if fi == 0:
            ax.legend(fontsize=4, ncol=2, loc="best")
        ax.set_title(f"{f_target} THz", fontsize=7)

    fig.suptitle(suffix, fontsize=7, y=1.01)
    fig.tight_layout()
    save_fig(fig, f"fig_{suffix}_per_sample_n_vs_temp")


def plot_feature_scatter(all_data, temps_list, feat_key, ylabel, title, fname, unit_mult=1):
    """Scatter plot with per-sample points + mean + trend line."""
    fig, ax = plt.subplots(figsize=(FIG_W * 1.3, FIG_H))
    ts, ms, ss = [], [], []

    for temp in temps_list:
        if temp not in all_data or feat_key not in all_data[temp]:
            continue
        d = all_data[temp][feat_key]
        ts.append(temp)
        ms.append(d["mean"] * unit_mult)
        ss.append(d["std"] * unit_mult)
        for ri, rv in enumerate(d["reps"]):
            ax.scatter(temp, rv * unit_mult, color=_REP_COLORS[ri % 5],
                       s=8, alpha=0.5, zorder=3, marker=_REP_MARKERS[ri % 5])

    ts, ms, ss = np.array(ts), np.array(ms), np.array(ss)
    ax.errorbar(ts, ms, yerr=ss, fmt="ko-", markersize=3, capsize=2,
                lw=0.8, elinewidth=0.4, capthick=0.3, zorder=5)

    if len(ts) >= 3:
        sl = linregress(ts, ms)
        x_fit = np.linspace(ts.min() - 5, ts.max() + 5, 100)
        ax.plot(x_fit, sl.slope * x_fit + sl.intercept, "r--", lw=0.5, alpha=0.7)
        r, p = pearsonr(ts, ms)
        sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
        ax.text(0.02, 0.98, f"R={r:+.3f} R²={r**2:.3f}{sig}",
                transform=ax.transAxes, va="top", fontsize=5,
                bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5, pad=0.2))

    ax.set_xlabel(r"Temperature ($\degree$C)")
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=6.5)
    auto_ylim(ax)
    fig.tight_layout()
    save_fig(fig, fname)


def plot_correlation_heatmap(all_data, temps_list):
    """Correlation heatmap of key features vs temperature."""
    print("Fig: Correlation heatmap...")
    key_feats = [
        "dt_pos", "dt_neg", "dt_avg", "amp_ratio_pos", "amp_ratio_neg", "p2p_ratio",
        "env_fwhm", "env_asymmetry", "fwhm_ratio", "dt_env",
        "delta_rms", "delta_p2p", "delta_centroid", "delta_energy",
        "H_amp_0.5", "H_amp_1.0", "H_amp_1.5",
        "group_delay_ps", "absorption_integral", "H_amp_slope",
        "centroid_sam", "phase_residual_rms",
    ]
    available = [f for f in key_feats if f in all_data.get(temps_list[0], {})]
    if not available:
        return

    mat = np.zeros((len(available), len(temps_list)))
    for i, fk in enumerate(available):
        for j, temp in enumerate(temps_list):
            if temp in all_data and fk in all_data[temp]:
                mat[i, j] = all_data[temp][fk]["mean"]

    # Normalize each row
    for i in range(mat.shape[0]):
        rng = np.ptp(mat[i])
        if rng > 0:
            mat[i] = (mat[i] - np.min(mat[i])) / rng

    fig, ax = plt.subplots(figsize=(FIG_W * 1.5, FIG_H * 2.0))
    im = ax.imshow(mat, aspect="auto", cmap="RdYlBu_r")
    ax.set_xticks(range(len(temps_list)))
    ax.set_xticklabels([f"{t}" for t in temps_list], fontsize=5)
    ax.set_yticks(range(len(available)))
    ax.set_yticklabels(available, fontsize=4.5)
    ax.set_xlabel(r"Temperature ($\degree$C)", fontsize=6)
    plt.colorbar(im, ax=ax, shrink=0.6)
    fig.tight_layout()
    save_fig(fig, "fig_correlation_heatmap")


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════
def main():
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    CSV_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Load data ──
    print("=" * 60)
    print("Loading data from", DATA_DIR)
    print("=" * 60)
    refs, samples = load_measurement_set_with_refs(DATA_DIR)
    temps_list = sorted(refs.keys())

    print(f"  Refs:     {sorted(refs.keys())}")
    print(f"  Samples:  {len(samples)} files")
    print(f"  Thickness: {THICKNESS_MM * 1000:.0f} um\n")

    # ── 2. Feature extraction (5 domains) ──
    print("=" * 60)
    print("Feature Extraction (5 Domains)")
    print("=" * 60)
    all_data = extract_all_temperatures(refs, samples)

    # Print time-domain summary
    print(f"\n{'Temp':>6}  {'dt+(fs)':>12}  {'dt-(fs)':>12}  {'P2P ratio':>10}")
    print("-" * 50)
    for temp in temps_list:
        if temp not in all_data:
            continue
        d = all_data[temp]
        print(f"{temp:>6d}  "
              f"{d['dt_pos']['mean']:>+8.2f}±{d['dt_pos']['std']:.2f}  "
              f"{d['dt_neg']['mean']:>+8.2f}±{d['dt_neg']['std']:.2f}  "
              f"{d['p2p_ratio']['mean']:>10.6f}")

    # ── 3. Optical property extraction (Matched Reference) ──
    config = ExtractionConfig(
        thickness_mm=THICKNESS_MM,
        freq_min_thz=0.2,
        freq_max_thz=2.5,
        n_fp_echoes=0,
        window_type="hann",
        zero_pad_factor=2,
        n_initial_guess=1.5,
        kappa_initial_guess=0.005,
        thin_film=True,
        apply_air_correction=False,
    )

    print(f"{'='*60}\nOptical Properties — Matched Ref (H = Sam(T)/Ref(T))\n{'='*60}")
    results_mr = process_temperature_series_matched_ref(
        refs, samples, config,
        progress_callback=lambda i, n: print(f"  {i}/{n}", end="\r"),
    )
    print()
    avgs_mr = compute_temperature_averages(results_mr)
    diel_mr = compute_dielectric(avgs_mr)

    # ── 4. Print per-sample optical results ──
    print(f"\n{'='*60}\nn @ 1.0 THz — Per Sample\n{'='*60}")
    print(f"{'Temp':>6}  {'S1':>8}  {'S2':>8}  {'S3':>8}  {'S4':>8}  {'S5':>8}  {'Mean±σ':>14}")
    print("-" * 72)
    for temp in temps_list:
        vals = []
        for rep in range(1, 6):
            key = (temp, rep)
            if key in results_mr:
                idx = np.argmin(np.abs(results_mr[key].freq_thz - 1.0))
                vals.append(results_mr[key].n[idx])
            else:
                vals.append(float("nan"))
        m, s = np.nanmean(vals), np.nanstd(vals)
        vstr = "  ".join(f"{v:8.4f}" for v in vals)
        print(f"{temp:>6d}  {vstr}  {m:.4f}±{s:.4f}")

    # ── 5. Correlation analysis (sample-specific features only) ──
    print(f"\n{'='*60}\nCorrelation Analysis (Sample-Specific Features vs T)\n{'='*60}")
    corr_results = correlate_features(all_data, temps_list)

    print(f"\n{'#':>3}  {'Feature':>25}  {'R':>7}  {'R²':>7}  {'p':>10}  {'slope/°C':>12}")
    for i, r in enumerate(corr_results):
        sig = "***" if r["p"] < 0.001 else "**" if r["p"] < 0.01 else "*" if r["p"] < 0.05 else ""
        print(f"{i+1:3d}  {r['name']:>25}  {r['R']:+7.4f}  {r['R2']:7.4f}  "
              f"{r['p']:10.2e}  {r['slope']:+12.4e} {sig}")

    # n vs T correlation (per-sample)
    print(f"\n{'='*60}\nn vs Temperature — Per Sample Correlation\n{'='*60}")
    for rep in range(1, 6):
        ts, ns = [], []
        for temp in temps_list:
            key = (temp, rep)
            if key in results_mr:
                idx = np.argmin(np.abs(results_mr[key].freq_thz - 1.0))
                ts.append(temp)
                ns.append(results_mr[key].n[idx])
        if len(ts) >= 5:
            r, p = pearsonr(ts, ns)
            sl = linregress(ts, ns)
            sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
            print(f"  S{rep}: R={r:+.4f} R²={r**2:.4f} p={p:.2e} "
                  f"slope={sl.slope:+.4e}/°C {sig}")

    # ── 6. Export CSV ──
    rows = []
    for temp in temps_list:
        if temp not in all_data:
            continue
        d = all_data[temp]
        row = {"Temperature (C)": temp}
        for key in ["dt_pos", "dt_neg", "dt_avg", "amp_ratio_pos", "amp_ratio_neg",
                     "p2p_ratio", "env_fwhm", "fwhm_ratio", "dt_env", "env_asymmetry",
                     "delta_rms", "delta_energy",
                     "group_delay_ps", "absorption_integral", "H_amp_1.0",
                     "rise_time_ps"]:
            if key in d:
                row[key] = d[key]["mean"]
                row[key + "_std"] = d[key]["std"]
                # Per-sample values
                for ri, rv in enumerate(d[key]["reps"]):
                    row[f"{key}_S{ri+1}"] = rv

        if temp in avgs_mr:
            p = avgs_mr[temp]
            for ft in [0.5, 1.0, 1.5]:
                idx = np.argmin(np.abs(p.freq_thz - ft))
                row[f"n@{ft}THz"] = p.n[idx]
                row[f"n_std@{ft}THz"] = p.n_std[idx] if p.n_std is not None else 0
                row[f"alpha@{ft}THz"] = p.alpha[idx]

        if temp in diel_mr:
            dd = diel_mr[temp]
            idx = np.argmin(np.abs(dd["freq_thz"] - 1.0))
            row["eps_real@1THz"] = dd["eps_real"][idx]
            row["eps_imag@1THz"] = dd["eps_imag"][idx]

        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(CSV_DIR / "pe40_summary_stats.csv", index=False)
    print(f"\nCSV saved: {CSV_DIR / 'pe40_summary_stats.csv'}")

    # Per-sample optical properties
    opt_rows = []
    for (temp, rep), props in sorted(results_mr.items()):
        f_mask = (props.freq_thz >= 0.2) & (props.freq_thz <= 2.5)
        for idx in np.where(f_mask)[0]:
            opt_rows.append({
                "temperature_c": temp, "replicate": rep,
                "freq_thz": props.freq_thz[idx],
                "n": props.n[idx], "kappa": props.kappa[idx], "alpha_cm-1": props.alpha[idx],
            })
    pd.DataFrame(opt_rows).to_csv(CSV_DIR / "pe40_optical_properties.csv", index=False)

    # ── 7. Figures ──
    print(f"\n{'='*60}\nGenerating Figures\n{'='*60}")

    # Time-domain
    plot_time_domain_zoom(refs, samples)
    plot_peak_detail(refs, samples)

    # Per-sample time-domain trends
    plot_per_sample_time_delay(all_data, temps_list)
    plot_per_sample_amplitude(all_data, temps_list)

    # Optical properties (Matched Ref only)
    plot_optical_props(avgs_mr, "Matched Ref (H = Sam(T)/Ref(T))", "mr")

    # Dielectric
    plot_dielectric(diel_mr, "mr")

    # Per-sample n vs T — the key output
    plot_per_sample_n_vs_temp(results_mr, temps_list, "Matched_Ref")

    # Feature scatter plots — sample-specific features
    top_features = [
        ("dt_pos", r"$\Delta t_{+}$ (fs)", "Time Delay (+peak)"),
        ("dt_neg", r"$\Delta t_{-}$ (fs)", "Time Delay (-peak)"),
        ("dt_avg", r"$\Delta t_{avg}$ (fs)", "Time Delay (avg)"),
        ("amp_ratio_pos", "Amp+ ratio", "Amplitude Ratio (+peak)"),
        ("p2p_ratio", "P2P ratio", "Peak-to-Peak Ratio"),
        ("dt_env", r"$\Delta t_{env}$ (fs)", "Envelope Delay"),
        ("fwhm_ratio", "FWHM ratio", "Envelope FWHM Ratio"),
        ("delta_rms", "RMS", "Delta Signal RMS"),
        ("group_delay_ps", "Group Delay (ps)", "Group Delay"),
        ("absorption_integral", "Absorption", "Absorption Integral"),
        ("H_amp_1.0", "|H| @ 1.0 THz", "Transfer Function @ 1.0 THz"),
        ("rise_time_ps", "Rise time (ps)", "Rise Time"),
    ]
    for fk, ylabel, title in top_features:
        plot_feature_scatter(all_data, temps_list, fk, ylabel, title,
                             f"fig_feat_{fk.replace('.', '_')}")

    # Correlation heatmap
    plot_correlation_heatmap(all_data, temps_list)

    print(f"\nAll figures saved to: {FIG_DIR}/")
    print(f"All CSV saved to: {CSV_DIR}/")

    # ── 8. Summary ──
    print(f"\n{'='*60}")
    print("ANALYSIS SUMMARY")
    print(f"{'='*60}")
    print(f"\n  Method: Matched Reference — H = Sam(T)/Ref(T)")
    print(f"  각 온도의 Ref와 Sample만 비교 (공기 경로 효과 자동 상쇄)")

    sig_feats = [r for r in corr_results if r["p"] < 0.05]
    print(f"\n  유의한 온도 상관 특성 ({len(sig_feats)}개, p < 0.05):")
    for i, r in enumerate(sig_feats):
        sig = "***" if r["p"] < 0.001 else "**" if r["p"] < 0.01 else "*" if r["p"] < 0.05 else ""
        print(f"    {i+1}. {r['name']:>25}: R²={r['R2']:.4f} {sig}")

    print(f"\n  n@1.0THz: {avgs_mr[20].n[np.argmin(np.abs(avgs_mr[20].freq_thz-1.0))]:.4f} (20°C)"
          f" → {avgs_mr[100].n[np.argmin(np.abs(avgs_mr[100].freq_thz-1.0))]:.4f} (100°C)")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
