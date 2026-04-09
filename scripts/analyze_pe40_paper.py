"""PE40 THz-TDS 온도 의존성 논문용 분석 스크립트.

PE20 분리막 2장 겹침(40 μm), Matched Reference 방식.
EMA 기공률 역산, 전이 온도 결정, 열팽창 모델 fitting.
8 Figures + 4 Tables.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline
from scipy.ndimage import median_filter
from scipy.optimize import brentq, minimize_scalar, curve_fit
from scipy.signal import hilbert, savgol_filter
from scipy.stats import pearsonr, linregress, f_oneway, ttest_ind, mannwhitneyu

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.ticker as ticker
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).parent.parent))

from thztds.io import load_measurement_set_with_refs
from thztds.signal import compute_fft
from thztds.transfer_function import compute_measured_transfer_function
from thztds.types import ExtractionConfig
from thztds.optical_properties import (
    process_temperature_series_matched_ref,
    compute_temperature_averages,
)
from thztds.constants import PI

# ── Paths ────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "MeaData" / "260406_Temp"
FIG_DIR = Path(__file__).parent.parent / "figures" / "paper_260406"
CSV_DIR = Path(__file__).parent.parent / "results" / "paper_260406"

TEMPS = list(range(20, 115, 10))
THICKNESS_MM = 0.04
N_REPLICATES = 5
FREQ_TARGETS = None  # auto-selected: top 3 R² frequencies

# ── Separator spec (MS-DPS 20B, dry process) ────────────────────
SEPARATOR_SPEC = {
    "product": "MS-DPS 20B",
    "process": "dry",
    "thickness_um": 20,
    "porosity": 0.44,       # 44% (제조사 사양)
    "air_permeability_s": 280,  # sec/100ml
}

# ── DSC data ─────────────────────────────────────────────────────
DSC_PE20 = {
    "Tm_cycle1": 139.37,
    "dH_cycle1": 198.6543,
    "dH_100pct": 293.0,
    "crystallinity": 198.6543 / 293.0,  # 0.678
}

# ── EMA parameters ───────────────────────────────────────────────
N_PE_CRYST = 1.53
N_PE_AMORPH = 1.49
N_AIR = 1.0
CRYSTALLINITY = DSC_PE20["crystallinity"]
N_PE_EFF = N_PE_CRYST * CRYSTALLINITY + N_PE_AMORPH * (1 - CRYSTALLINITY)  # ~1.517
F_AIR_SPEC = SEPARATOR_SPEC["porosity"]  # 44% anchoring

# ── Scientific references for methods ────────────────────────────
REFERENCES = {
    "EMA": {
        "title": "Terahertz-Based Porosity Measurement of Pharmaceutical Tablets: a Tutorial",
        "authors": "Bawuah et al.",
        "journal": "J Infrared Milli Terahz Waves",
        "year": 2020,
        "vol": "41",
        "pages": "450-469",
        "doi": "10.1007/s10762-019-00659-0",
    },
    "AB-EMA": {
        "title": "THz-TDS for powder compact porosity and pore shape measurements: "
                 "An error analysis of the anisotropic Bruggeman model",
        "authors": "Bawuah et al.",
        "journal": "Int J Pharm X",
        "year": 2021,
        "vol": "3",
        "pages": "100078",
        "doi": "10.1016/j.ijpx.2021.100078",
    },
    "thermal_expansion": {
        "title": "Effect of Porosity on the Thermal Expansion Coefficient of Porous Materials",
        "authors": "Wei et al.",
        "journal": "Proc. Eng. Mech. Inst. Conf.",
        "year": 2013,
        "doi": "10.1061/9780784412992.220",
    },
    "PE_separator": {
        "title": "Manufacturing Processes of Microporous Polyolefin Separators "
                 "for Lithium-Ion Batteries and Correlations between Mechanical "
                 "and Physical Properties",
        "authors": "Deimede et al.",
        "journal": "Crystals",
        "year": 2021,
        "vol": "11(9)",
        "pages": "1013",
        "doi": "10.3390/cryst11091013",
    },
    "compression": {
        "title": "Effect of a compressed separator on the electrochemical "
                 "performance of Li-ion battery",
        "authors": "Xu et al.",
        "journal": "J Power Sources",
        "year": 2023,
        "doi": "10.1016/j.jpowsour.2023.232900",
    },
}

# ── Figure style (journal, 4:3 aspect ratio) ────────────────────
CM = 1 / 2.54
SINGLE_COL_W = 8.5 * CM
SINGLE_COL_H = SINGLE_COL_W * 3 / 4  # 4:3
DOUBLE_COL_W = 17.0 * CM
DOUBLE_COL_H = DOUBLE_COL_W * 3 / 4   # 4:3
DPI = 600

# n(f) y축 고정 범위
N_YLIM = (1.0, 1.5)

plt.rcParams.update({
    "font.family": "Arial",
    "font.size": 10,
    "mathtext.default": "regular",
    "axes.labelsize": 11,
    "axes.titlesize": 11,
    "axes.linewidth": 0.6,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "xtick.major.width": 0.5,
    "ytick.major.width": 0.5,
    "xtick.major.size": 3.0,
    "ytick.major.size": 3.0,
    "xtick.direction": "in",
    "ytick.direction": "in",
    "xtick.top": True,
    "ytick.right": True,
    "lines.linewidth": 0.9,
    "legend.fontsize": 8,
    "legend.handlelength": 1.5,
    "legend.frameon": True,
    "legend.edgecolor": "0.8",
    "legend.fancybox": False,
    "savefig.dpi": DPI,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.08,
})

TEMP_COLORS = [
    "#3B4CC0", "#5A7BC6", "#7AAAD0", "#9DC8D9", "#BDDDDD",
    "#E8C8A0", "#F0A672", "#E87B52", "#D44E3D", "#B40426",
]
TEMP_CMAP = LinearSegmentedColormap.from_list("temp", TEMP_COLORS, N=256)
SAMPLE_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
SAMPLE_MARKERS = ["o", "s", "^", "D", "v"]


def get_temp_color(t): return TEMP_COLORS[TEMPS.index(t)]


def make_temp_colorbar(ax, fig, label=r"Temperature ($\degree$C)"):
    sm = plt.cm.ScalarMappable(cmap=TEMP_CMAP, norm=plt.Normalize(20, 110))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.03, aspect=20, shrink=0.9)
    cbar.set_label(label, fontsize=9, labelpad=3)
    cbar.ax.tick_params(labelsize=8, width=0.4, length=2.0)
    cbar.set_ticks([20, 40, 60, 80, 100])
    return cbar


def save_fig(fig, name):
    fig.savefig(FIG_DIR / f"{name}.png")
    fig.savefig(FIG_DIR / f"{name}.pdf")
    plt.close(fig)
    print(f"  -> {name}")


def auto_ylim(ax, margin=0.08):
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


def smooth_n(y): return median_filter(y, size=3)


def smooth_alpha(y):
    c = median_filter(y, size=5)
    if len(c) >= 21:
        c = savgol_filter(c, 21, 3)
    return c


def interp_signal(t, s, factor=10):
    raw_idx = np.argmax(np.abs(s))
    raw_t = t[raw_idx]
    mask = (t >= raw_t - 5) & (t <= raw_t + 5)
    t_roi, s_roi = t[mask], s[mask]
    t_fine = np.linspace(t_roi[0], t_roi[-1], len(t_roi) * factor)
    cs = CubicSpline(t_roi, s_roi)
    return t_fine, cs(t_fine), cs


# ══════════════════════════════════════════════════════════════════
# EMA Model
# ══════════════════════════════════════════════════════════════════
def bruggeman_2phase(f_air, n_pe=N_PE_EFF, n_air=N_AIR):
    """Bruggeman 2-phase EMA (PE_eff + air) → n_eff.  [PRIMARY MODEL]"""
    eps_pe = n_pe**2
    eps_air_val = n_air**2

    def equation(eps_eff):
        return ((1 - f_air) * (eps_pe - eps_eff) / (eps_pe + 2 * eps_eff) +
                f_air * (eps_air_val - eps_eff) / (eps_air_val + 2 * eps_eff))

    eps_eff = brentq(equation, 0.5, eps_pe + 1)
    return np.sqrt(eps_eff)


def bruggeman_3phase(f_air, n_cryst=N_PE_CRYST, n_amorph=N_PE_AMORPH,
                     n_air=N_AIR, f_cryst_ratio=CRYSTALLINITY):
    """Bruggeman 3-phase EMA → n_eff.  [For comparison only]"""
    f_PE = 1 - f_air
    f_c = f_PE * f_cryst_ratio
    f_a = f_PE * (1 - f_cryst_ratio)

    eps_c = n_cryst**2
    eps_a = n_amorph**2
    eps_air_val = n_air**2

    def equation(eps_eff):
        return (f_c * (eps_c - eps_eff) / (eps_c + 2 * eps_eff) +
                f_a * (eps_a - eps_eff) / (eps_a + 2 * eps_eff) +
                f_air * (eps_air_val - eps_eff) / (eps_air_val + 2 * eps_eff))

    eps_eff = brentq(equation, 0.5, eps_c + 1)
    return np.sqrt(eps_eff)


def invert_porosity(n_measured):
    """n_eff → f_air via 2-phase Bruggeman inversion."""
    def objective(f_air):
        return bruggeman_2phase(f_air) - n_measured
    try:
        return brentq(objective, 0.001, 0.999)
    except ValueError:
        return np.nan


def compute_n_offset(n_measured_20c, f_air_spec=F_AIR_SPEC):
    """Compute n offset for spec-anchored porosity (2-phase model).

    2장 겹침에 의한 n 상승분을 계산.
    n_EMA(f_air_spec) = 단일 시트 기대값
    offset = n_measured(20°C) - n_EMA(f_air_spec)
    """
    n_single = bruggeman_2phase(f_air_spec)
    return n_measured_20c - n_single


def invert_porosity_anchored(n_measured, n_offset):
    """Spec-anchored porosity: n을 보정 후 역산 (2-phase).

    n_corrected = n_measured - n_offset (2장 겹침 보정)
    f_air = Bruggeman^{-1}(n_corrected)
    """
    n_corrected = n_measured - n_offset
    return invert_porosity(n_corrected)


def select_best_frequencies(avgs_mr, temps_list, n_top=3, f_min=0.3, f_max=2.0):
    """Scan frequencies and find top-N with highest |R²| for n(T) vs T."""
    freq_hz = avgs_mr[temps_list[0]].freq_hz
    freq_thz = freq_hz / 1e12
    mask = (freq_thz >= f_min) & (freq_thz <= f_max)
    candidates = []

    for idx in np.where(mask)[0]:
        f_val = freq_thz[idx]
        ts, ns = [], []
        for temp in temps_list:
            if temp in avgs_mr:
                ts.append(temp)
                ns.append(avgs_mr[temp].n[idx])
        if len(ts) < 5:
            continue
        t_arr = np.array(ts, dtype=float)
        n_arr = np.array(ns, dtype=float)
        if not np.all(np.isfinite(n_arr)):
            continue
        r, p = pearsonr(t_arr, n_arr)
        candidates.append({"freq_thz": f_val, "idx": idx, "R": r, "R2": r**2, "p": p})

    candidates.sort(key=lambda x: x["R2"], reverse=True)

    # Pick top-N but ensure they are spread out (at least 0.2 THz apart)
    selected = []
    for c in candidates:
        if len(selected) >= n_top:
            break
        if all(abs(c["freq_thz"] - s["freq_thz"]) > 0.15 for s in selected):
            selected.append(c)

    selected.sort(key=lambda x: x["freq_thz"])
    return selected


def thermal_expansion_model(T, f_air_0, beta):
    """f_air(T) = 1 - (1 - f_air_0) / (1 + beta * (T - 20))."""
    dT = np.asarray(T, dtype=float) - 20.0
    return 1 - (1 - f_air_0) / (1 + beta * dT)


def fit_two_regime(temps, values):
    """Piecewise linear fitting to find transition temperature."""
    temps = np.asarray(temps, dtype=float)
    values = np.asarray(values, dtype=float)

    def cost(T_break):
        mask1 = temps <= T_break
        mask2 = temps >= T_break
        if np.sum(mask1) < 2 or np.sum(mask2) < 2:
            return 1e10
        sl1 = linregress(temps[mask1], values[mask1])
        sl2 = linregress(temps[mask2], values[mask2])
        res1 = np.sum((values[mask1] - sl1.slope * temps[mask1] - sl1.intercept) ** 2)
        res2 = np.sum((values[mask2] - sl2.slope * temps[mask2] - sl2.intercept) ** 2)
        return res1 + res2

    result = minimize_scalar(cost, bounds=(30, 90), method="bounded")
    T_break = result.x

    mask1 = temps <= T_break
    mask2 = temps >= T_break
    sl1 = linregress(temps[mask1], values[mask1])
    sl2 = linregress(temps[mask2], values[mask2])

    # Intersection
    if abs(sl1.slope - sl2.slope) > 1e-15:
        T_intersect = (sl2.intercept - sl1.intercept) / (sl1.slope - sl2.slope)
    else:
        T_intersect = T_break

    return {
        "T_transition": T_intersect,
        "regime1": sl1,
        "regime2": sl2,
        "T_break_opt": T_break,
    }


# ══════════════════════════════════════════════════════════════════
# Feature Extraction (sample-specific only)
# ══════════════════════════════════════════════════════════════════
def extract_sample_features(ref, sam):
    """Extract sample-specific features from one ref-sample pair."""
    t_r, s_r = ref.time_ps, ref.signal
    t_s, s_s = sam.time_ps, sam.signal
    tf_r, sf_r, cs_r = interp_signal(t_r, s_r)
    tf_s, sf_s, cs_s = interp_signal(t_s, s_s)

    f = {}

    # Time-domain
    r_pos_i, r_neg_i = np.argmax(sf_r), np.argmin(sf_r)
    s_pos_i, s_neg_i = np.argmax(sf_s), np.argmin(sf_s)

    f["dt_pos"] = (tf_s[s_pos_i] - tf_r[r_pos_i]) * 1000
    f["dt_neg"] = (tf_s[s_neg_i] - tf_r[r_neg_i]) * 1000
    f["dt_avg"] = (f["dt_pos"] + f["dt_neg"]) / 2
    f["amp_ratio_pos"] = sf_s[s_pos_i] / sf_r[r_pos_i] if sf_r[r_pos_i] != 0 else 0
    f["amp_ratio_neg"] = sf_s[s_neg_i] / sf_r[r_neg_i] if sf_r[r_neg_i] != 0 else 0
    f["p2p_ratio"] = (sf_s[s_pos_i] - sf_s[s_neg_i]) / (sf_r[r_pos_i] - sf_r[r_neg_i])

    # Rise time
    peak_val = sf_s[s_pos_i]
    s_before = sf_s[:s_pos_i]
    t10 = np.where(s_before > 0.1 * peak_val)[0]
    t90 = np.where(s_before > 0.9 * peak_val)[0]
    f["rise_time_ps"] = (tf_s[t90[0]] - tf_s[t10[0]]) if len(t10) > 0 and len(t90) > 0 else 0

    # Envelope
    env_s = np.abs(hilbert(s_s))
    tf_es, ef_s, _ = interp_signal(t_s, env_s)
    s_env_i = np.argmax(ef_s)
    hm = ef_s[s_env_i] / 2
    above = ef_s > hm
    if np.any(above):
        first = np.argmax(above)
        last = len(above) - 1 - np.argmax(above[::-1])
        f["env_fwhm"] = tf_es[last] - tf_es[first]
    else:
        f["env_fwhm"] = 0

    # Envelope asymmetry
    area_b = np.trapezoid(ef_s[:s_env_i], tf_es[:s_env_i]) if s_env_i > 0 else 0
    area_a = np.trapezoid(ef_s[s_env_i:], tf_es[s_env_i:]) if s_env_i < len(ef_s) - 1 else 0
    f["env_asymmetry"] = (area_a - area_b) / (area_a + area_b) if (area_a + area_b) > 0 else 0

    # Delta signal
    delta = s_s - s_r
    raw_idx = np.argmax(np.abs(s_r))
    raw_t = t_r[raw_idx]
    d_mask = (t_r >= raw_t - 3) & (t_r <= raw_t + 3)
    d_roi, t_d = delta[d_mask], t_r[d_mask]
    f["delta_rms"] = np.sqrt(np.mean(d_roi**2))

    # Frequency domain
    ref_freq = compute_fft(ref, 2)
    sam_freq = compute_fft(sam, 2)
    H = compute_measured_transfer_function(ref_freq, sam_freq)
    freq_thz = ref_freq.freq_hz / 1e12
    valid = ~np.isnan(H)
    mb = valid & (freq_thz >= 0.3) & (freq_thz <= 2.0)

    if np.any(mb):
        phase = np.unwrap(np.angle(H[mb]))
        sl = linregress(ref_freq.freq_hz[mb], phase)
        f["group_delay_ps"] = -sl.slope / (2 * PI) * 1e12

    # Spectral centroid
    sam_amp = sam_freq.amplitude
    mk_s = (freq_thz >= 0.3) & (freq_thz <= 2.0) & (sam_amp > 0)
    if np.any(mk_s):
        f["centroid_sam"] = np.sum(freq_thz[mk_s] * sam_amp[mk_s]) / np.sum(sam_amp[mk_s])

    return f


def extract_all_temperatures(refs, samples):
    all_data = {}
    for temp in sorted(refs.keys()):
        ref = refs[temp]
        rep_features = []
        for rep in range(1, 6):
            key = (temp, rep)
            if key not in samples:
                continue
            rep_features.append(extract_sample_features(ref, samples[key]))
        if not rep_features:
            continue
        avg = {}
        for k in rep_features[0]:
            vals = [rf[k] for rf in rep_features if k in rf]
            avg[k] = {"mean": np.mean(vals), "std": np.std(vals), "reps": vals}
        all_data[temp] = avg
    return all_data


def correlate_features(all_data, temps_list):
    results = []
    feature_keys = set()
    for temp in temps_list:
        if temp in all_data:
            feature_keys.update(all_data[temp].keys())

    DOMAIN_MAP = {
        "dt_pos": "Time", "dt_neg": "Time", "dt_avg": "Time",
        "amp_ratio_pos": "Time", "amp_ratio_neg": "Time", "p2p_ratio": "Time",
        "rise_time_ps": "Time",
        "env_fwhm": "Envelope", "env_asymmetry": "Envelope",
        "delta_rms": "Delta",
        "group_delay_ps": "Frequency", "centroid_sam": "Frequency",
    }

    for fk in sorted(feature_keys):
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
            "name": fk, "domain": DOMAIN_MAP.get(fk, "Other"),
            "R": r, "R2": r**2, "p": p, "slope": sl.slope,
        })

    results.sort(key=lambda x: abs(x["R"]), reverse=True)
    return results


# ══════════════════════════════════════════════════════════════════
# FIGURES
# ══════════════════════════════════════════════════════════════════

def fig01_time_domain_zoom(refs, samples):
    print("Fig.1: Time-domain zoom...")
    fig, axes = plt.subplots(2, 5, figsize=(DOUBLE_COL_W, DOUBLE_COL_W * 0.4))
    axes = axes.flatten()
    for i, temp in enumerate(TEMPS):
        ax = axes[i]
        ref = refs[temp]
        tf_r, sf_r, _ = interp_signal(ref.time_ps, ref.signal)
        t0 = tf_r[np.argmax(sf_r)]
        ax.plot(ref.time_ps - t0, ref.signal, color="black", lw=0.9, zorder=10,
                label="Ref" if i == 0 else None)
        for rep in range(1, 6):
            key = (temp, rep)
            if key in samples:
                td = samples[key]
                ax.plot(td.time_ps - t0, td.signal,
                        color=get_temp_color(temp), lw=0.4, alpha=0.7,
                        label="Sample" if i == 0 and rep == 1 else None)
        ax.set_xlim(-1.5, 2.0)
        auto_ylim(ax)
        ax.set_title(f"{temp} " + r"$\degree$C", fontsize=9.5)
        if i >= 5: ax.set_xlabel("Time (ps)")
        if i % 5 == 0: ax.set_ylabel("Amplitude (a.u.)")
    axes[0].legend(fontsize=7, loc="upper right")
    fig.tight_layout(w_pad=0.8, h_pad=1.0)
    save_fig(fig, "fig01_time_domain_zoom")


def fig02_peak_detail(refs, samples):
    """Sample peak overlay (2-panel) with Ref 20°C as dashed baseline."""
    print("Fig.2: Peak detail (2-panel, Sample + Ref dashed)...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(DOUBLE_COL_W, DOUBLE_COL_H * 0.75))

    ref20 = refs[20]
    tf_20, sf_20, _ = interp_signal(ref20.time_ps, ref20.signal)
    t0 = tf_20[np.argmax(sf_20)]
    neg_t = tf_20[np.argmin(sf_20)] - t0

    for temp in TEMPS:
        key = (temp, 1)
        if key not in samples:
            continue
        td = samples[key]
        ax1.plot(td.time_ps - t0, td.signal, color=get_temp_color(temp), lw=0.6)
        ax2.plot(td.time_ps - t0, td.signal, color=get_temp_color(temp), lw=0.6)

    ax1.plot(ref20.time_ps - t0, ref20.signal, "k--", lw=1.0, label="Ref (20 \u00b0C)")
    ax2.plot(ref20.time_ps - t0, ref20.signal, "k--", lw=1.0)

    ax1.set_xlim(-0.3, 0.5)
    ax2.set_xlim(neg_t - 0.3, neg_t + 0.3)
    for ax in [ax1, ax2]:
        auto_ylim(ax)
        ax.set_xlabel("Time (ps)")
    ax1.set_ylabel("Amplitude (a.u.)")
    ax1.set_title("(a) Positive peak", fontsize=10)
    ax2.set_title("(b) Negative peak", fontsize=10)
    ax1.legend(fontsize=7, loc="upper right")
    make_temp_colorbar(ax2, fig)
    fig.tight_layout(w_pad=1.5)
    save_fig(fig, "fig02_peak_detail")


def fig03_n_vs_temp_ema(results_mr, avgs_mr, porosity_data, two_regime, thermal_fit, best_freq):
    """★ Core figure: n(T) per-sample + EMA porosity at best frequency."""
    f_target = best_freq["freq_thz"]
    f_idx = best_freq["idx"]
    print(f"Fig.3: n(T) + EMA @ {f_target:.2f} THz...")
    fig, ax1 = plt.subplots(figsize=(SINGLE_COL_W * 1.3, SINGLE_COL_H * 1.05))
    ax2 = ax1.twinx()

    temps_list = sorted(avgs_mr.keys())

    # Per-sample points
    for rep in range(1, 6):
        ts, ns = [], []
        for temp in temps_list:
            key = (temp, rep)
            if key in results_mr:
                ts.append(temp)
                ns.append(results_mr[key].n[f_idx])
        ax1.plot(ts, ns, marker=SAMPLE_MARKERS[rep - 1], color=SAMPLE_COLORS[rep - 1],
                 markersize=3, lw=0, label=f"S{rep}", zorder=3, alpha=0.6)

    # Mean ± σ
    mean_n = [avgs_mr[t].n[f_idx] for t in temps_list]
    std_n = [avgs_mr[t].n_std[f_idx] if avgs_mr[t].n_std is not None else 0 for t in temps_list]
    ax1.fill_between(temps_list, np.array(mean_n) - np.array(std_n),
                     np.array(mean_n) + np.array(std_n), color="gray", alpha=0.2)
    ax1.plot(temps_list, mean_n, "k-o", markersize=4, lw=1.0, zorder=5, label=r"Mean $\pm \sigma$")

    # Two-regime lines
    tr = two_regime
    T_tr = tr["T_transition"]
    t_fit1 = np.linspace(15, T_tr, 50)
    t_fit2 = np.linspace(T_tr, 115, 50)
    ax1.plot(t_fit1, tr["regime1"].slope * t_fit1 + tr["regime1"].intercept,
             "b--", lw=0.6, alpha=0.7)
    ax1.plot(t_fit2, tr["regime2"].slope * t_fit2 + tr["regime2"].intercept,
             "r--", lw=0.6, alpha=0.7)
    ax1.axvline(T_tr, color="gray", ls=":", lw=0.5, zorder=0)
    ax1.annotate(f"$T_{{onset}}$ = {T_tr:.0f} " + r"$\degree$C",
                 xy=(T_tr, 1.35), xytext=(75, 1.33),
                 fontsize=8.5, arrowprops=dict(arrowstyle="->", lw=0.6),
                 bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="gray", alpha=0.9, lw=0.4))

    # Right axis: porosity
    p_temps = sorted(porosity_data.keys())
    p_vals = [porosity_data[t]["mean"] * 100 for t in p_temps]
    p_errs = [porosity_data[t]["std"] * 100 for t in p_temps]
    ax2.errorbar(p_temps, p_vals, yerr=p_errs, fmt="none", ecolor="red",
                 elinewidth=0.4, capsize=1.5, capthick=0.3, alpha=0.5)

    if thermal_fit is not None:
        T_model = np.linspace(15, 115, 200)
        f_model = thermal_expansion_model(T_model, *thermal_fit) * 100
        ax2.plot(T_model, f_model, "r--", lw=0.7, label="Thermal exp. model")

    ax1.set_xlabel(r"Temperature ($\degree$C)")
    ax1.set_ylabel(f"Refractive index, $n$ @ {f_target:.2f} THz")
    ax2.set_ylabel(r"Porosity (%)", color="red")
    ax2.tick_params(axis="y", labelcolor="red")
    ax1.set_ylim(*N_YLIM)

    ax1.legend(fontsize=7, ncol=3, loc="lower left",
               bbox_to_anchor=(0.02, 0.02), framealpha=0.9)
    fig.tight_layout(pad=1.2)
    save_fig(fig, "fig03_n_vs_temp_ema")


def fig04_optical_spectra(avgs_mr, best_freqs):
    print("Fig.4: n(f) + alpha(f)...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(DOUBLE_COL_W, DOUBLE_COL_H))
    for temp in TEMPS:
        if temp not in avgs_mr: continue
        p = avgs_mr[temp]
        f_mask = (p.freq_thz >= 0.3) & (p.freq_thz <= 2.0)
        ax1.plot(p.freq_thz[f_mask], smooth_n(p.n[f_mask]),
                 color=get_temp_color(temp), lw=0.6)
        alpha_clipped = np.clip(smooth_alpha(p.alpha[f_mask]), 0, None)
        ax2.plot(p.freq_thz[f_mask], alpha_clipped,
                 color=get_temp_color(temp), lw=0.6)

    # Mark best frequencies
    for i_bf, bf in enumerate(best_freqs):
        lbl = f"{bf['freq_thz']:.2f} THz" if i_bf == 0 else f"{bf['freq_thz']:.2f}"
        ax1.axvline(bf["freq_thz"], color="gray", ls=":", lw=0.4, alpha=0.6,
                    label=lbl)
    ax1.legend(fontsize=7, loc="lower left", title="Best freq.", title_fontsize=7)

    ax1.set_ylabel("Refractive index, $n$")
    ax1.set_ylim(1.2, 1.5)
    ax2.set_ylabel(r"Absorption coefficient, $\alpha$ (cm$^{-1}$)")
    ax2.set_ylim(0, 30)
    for ax in [ax1, ax2]:
        ax.set_xlim(0.3, 2.0)
        ax.set_xlabel("Frequency (THz)")
        ax.xaxis.set_major_locator(ticker.MultipleLocator(0.5))
    make_temp_colorbar(ax2, fig)
    fig.tight_layout(w_pad=1.5)
    save_fig(fig, "fig04_optical_spectra")


def fig05_time_features(all_data, temps_list):
    print("Fig.5: Time features vs temp...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(DOUBLE_COL_W, DOUBLE_COL_H))

    ts_m = [t for t in temps_list if t in all_data]

    # Left: dt_avg per-sample
    for rep_idx in range(5):
        ts, vals = [], []
        for temp in ts_m:
            reps = all_data[temp].get("dt_avg", {}).get("reps", [])
            if rep_idx < len(reps):
                ts.append(temp)
                vals.append(reps[rep_idx])
        ax1.plot(ts, vals, marker=SAMPLE_MARKERS[rep_idx], color=SAMPLE_COLORS[rep_idx],
                 markersize=2.5, lw=0.4, label=f"S{rep_idx+1}")

    means = [all_data[t]["dt_avg"]["mean"] for t in ts_m]
    stds = [all_data[t]["dt_avg"]["std"] for t in ts_m]
    ax1.errorbar(ts_m, means, yerr=stds, fmt="k-", lw=1.0, capsize=2,
                 capthick=0.4, elinewidth=0.4, markersize=0, zorder=10)

    # Trend line
    r, p = pearsonr(ts_m, means)
    sl = linregress(ts_m, means)
    x_fit = np.linspace(15, 115, 100)
    ax1.plot(x_fit, sl.slope * x_fit + sl.intercept, "r--", lw=0.5, alpha=0.7)
    sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
    ax1.text(0.03, 0.97, f"R²={r**2:.3f}{sig}", transform=ax1.transAxes,
             va="top", fontsize=8, bbox=dict(boxstyle="round", fc="wheat", alpha=0.5, pad=0.3))

    ax1.set_ylabel(r"Time delay, $\Delta t$ (fs)")
    ax1.legend(fontsize=7, ncol=3, loc="upper right")
    auto_ylim(ax1)

    # Right: P2P ratio per-sample
    for rep_idx in range(5):
        ts, vals = [], []
        for temp in ts_m:
            reps = all_data[temp].get("p2p_ratio", {}).get("reps", [])
            if rep_idx < len(reps):
                ts.append(temp)
                vals.append(reps[rep_idx])
        ax2.plot(ts, vals, marker=SAMPLE_MARKERS[rep_idx], color=SAMPLE_COLORS[rep_idx],
                 markersize=2.5, lw=0.4, label=f"S{rep_idx+1}")

    means2 = [all_data[t]["p2p_ratio"]["mean"] for t in ts_m]
    stds2 = [all_data[t]["p2p_ratio"]["std"] for t in ts_m]
    ax2.errorbar(ts_m, means2, yerr=stds2, fmt="k-", lw=1.0, capsize=2,
                 capthick=0.4, elinewidth=0.4, markersize=0, zorder=10)
    ax2.set_ylabel("Peak-to-peak ratio")
    auto_ylim(ax2)

    for ax in [ax1, ax2]:
        ax.set_xlabel(r"Temperature ($\degree$C)")
    fig.tight_layout(w_pad=1.5)
    save_fig(fig, "fig05_time_features_vs_temp")


def fig06_porosity(porosity_data, thermal_fit, two_regime):
    print("Fig.6: Porosity vs temp...")
    fig, ax = plt.subplots(figsize=(SINGLE_COL_W, SINGLE_COL_H))

    p_temps = sorted(porosity_data.keys())
    p_means = [porosity_data[t]["mean"] * 100 for t in p_temps]
    p_stds = [porosity_data[t]["std"] * 100 for t in p_temps]

    ax.errorbar(p_temps, p_means, yerr=p_stds, fmt="ko", markersize=4,
                capsize=2.5, capthick=0.4, elinewidth=0.5, lw=0.8, label="THz-EMA")

    # Thermal expansion model
    if thermal_fit is not None:
        T_model = np.linspace(15, 115, 200)
        f_model = thermal_expansion_model(T_model, *thermal_fit) * 100
        ax.plot(T_model, f_model, "r--", lw=0.8,
                label=fr"Model ($\beta$={thermal_fit[1]:.2e} /°C)")

    # Transition temperature
    T_tr = two_regime["T_transition"]
    ax.axvline(T_tr, color="gray", ls=":", lw=0.5)
    ax.annotate(f"$T_{{onset}}$ = {T_tr:.0f} " + r"$\degree$C",
                xy=(T_tr, max(p_means) - 2), xytext=(T_tr + 12, max(p_means) + 3),
                fontsize=8.5, arrowprops=dict(arrowstyle="->", lw=0.6))

    # Initial porosity line
    ax.axhline(p_means[0], color="gray", ls="--", lw=0.4, alpha=0.5)
    ax.text(112, p_means[0] + 0.8, f"{p_means[0]:.1f}%", fontsize=8, va="bottom", ha="right")

    ax.set_xlabel(r"Temperature ($\degree$C)")
    ax.set_ylabel(r"Porosity (%)")
    ax.legend(fontsize=8, loc="lower right")
    ax.set_ylim(30, 75)
    fig.tight_layout()
    save_fig(fig, "fig06_porosity_vs_temp")


def fig07_dielectric(avgs_mr, results_mr, best_freq):
    f_idx = best_freq["idx"]
    f_t = best_freq["freq_thz"]
    print(f"Fig.7: Dielectric @ {f_t:.2f} THz...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(DOUBLE_COL_W, DOUBLE_COL_H))

    # Left: eps'(f)
    for temp in TEMPS:
        if temp not in avgs_mr: continue
        p = avgs_mr[temp]
        f_mask = (p.freq_thz >= 0.3) & (p.freq_thz <= 2.0)
        eps_real = smooth_n(p.n[f_mask]**2 - p.kappa[f_mask]**2)
        ax1.plot(p.freq_thz[f_mask], eps_real, color=get_temp_color(temp), lw=0.6)
    ax1.set_ylabel(r"Real permittivity, $\varepsilon'$")
    ax1.set_xlabel("Frequency (THz)")
    ax1.set_xlim(0.3, 2.0)
    ax1.xaxis.set_major_locator(ticker.MultipleLocator(0.5))
    auto_ylim(ax1)
    make_temp_colorbar(ax1, fig)

    # Right: eps'(T) per-sample at best freq
    temps_list = sorted(avgs_mr.keys())
    for rep in range(1, 6):
        ts, es = [], []
        for temp in temps_list:
            key = (temp, rep)
            if key in results_mr:
                p = results_mr[key]
                ts.append(temp)
                es.append(p.n[f_idx]**2 - p.kappa[f_idx]**2)
        ax2.plot(ts, es, marker=SAMPLE_MARKERS[rep - 1], color=SAMPLE_COLORS[rep - 1],
                 markersize=2.5, lw=0.4, label=f"S{rep}")

    mean_eps = [avgs_mr[t].n[f_idx]**2 - avgs_mr[t].kappa[f_idx]**2 for t in temps_list]
    ax2.plot(temps_list, mean_eps, "k-o", markersize=3, lw=0.8, zorder=5, label="Mean")

    ax2.set_xlabel(r"Temperature ($\degree$C)")
    ax2.set_ylabel(fr"$\varepsilon'$ @ {f_t:.2f} THz")
    ax2.legend(fontsize=7, ncol=3, loc="upper right")
    auto_ylim(ax2)
    fig.tight_layout(w_pad=1.5)
    save_fig(fig, "fig07_dielectric")


def fig08_correlation_summary(corr_results, all_data, temps_list):
    print("Fig.8: Correlation summary...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(DOUBLE_COL_W, DOUBLE_COL_H * 1.1))

    # Left: Heatmap
    feat_keys = [r["name"] for r in corr_results]
    available = [f for f in feat_keys if f in all_data.get(temps_list[0], {})][:15]
    mat = np.zeros((len(available), len(temps_list)))
    for i, fk in enumerate(available):
        for j, temp in enumerate(temps_list):
            if temp in all_data and fk in all_data[temp]:
                mat[i, j] = all_data[temp][fk]["mean"]
    for i in range(mat.shape[0]):
        rng = np.ptp(mat[i])
        if rng > 0:
            mat[i] = (mat[i] - np.min(mat[i])) / rng

    im = ax1.imshow(mat, aspect="auto", cmap="RdYlBu_r")
    ax1.set_xticks(range(len(temps_list)))
    ax1.set_xticklabels([f"{t}" for t in temps_list], fontsize=7.5)
    ax1.set_yticks(range(len(available)))
    ax1.set_yticklabels(available, fontsize=7.5)
    ax1.set_xlabel(r"Temperature ($\degree$C)")
    cbar_h = plt.colorbar(im, ax=ax1, shrink=0.7, pad=0.02)
    cbar_h.ax.tick_params(labelsize=7)

    # Right: R² bar chart
    top = corr_results[:12]
    names = [r["name"] for r in top]
    r2s = [r["R2"] for r in top]
    colors_bar = ["#2166AC" if r["p"] < 0.05 else "#BBBBBB" for r in top]
    y_pos = np.arange(len(names))

    ax2.barh(y_pos, r2s, color=colors_bar, height=0.6, edgecolor="none")
    for i, r in enumerate(top):
        sig = "***" if r["p"] < 0.001 else "**" if r["p"] < 0.01 else "*" if r["p"] < 0.05 else ""
        ax2.text(r["R2"] + 0.01, i, sig, va="center", fontsize=7.5)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(names, fontsize=7.5)
    ax2.set_xlabel("R²")
    ax2.set_xlim(0, 1.1)
    ax2.invert_yaxis()
    ax2.axvline(0.5, color="gray", ls=":", lw=0.4)

    # Significance legend
    from matplotlib.patches import Patch
    leg_items = [
        Patch(facecolor="#2166AC", label="$p$ < 0.05"),
        Patch(facecolor="#BBBBBB", label="$p$ ≥ 0.05"),
    ]
    ax2.legend(handles=leg_items, fontsize=7, loc="lower right")

    fig.tight_layout(w_pad=1.5)
    save_fig(fig, "fig08_correlation_summary")


def fig09_per_sample_n_3freq(results_mr, avgs_mr, best_freqs, temps_list):
    """Per-sample n(T) at the 3 best frequencies with mean±σ error bars."""
    print("Fig.9: Per-sample n(T) at 3 best frequencies...")
    fig, axes = plt.subplots(1, 3, figsize=(DOUBLE_COL_W, DOUBLE_COL_H * 0.85))
    for fi, bf in enumerate(best_freqs):
        ax = axes[fi]
        f_idx = bf["idx"]
        f_t = bf["freq_thz"]
        for rep in range(1, 6):
            ts, ns = [], []
            for temp in temps_list:
                key = (temp, rep)
                if key in results_mr:
                    ts.append(temp)
                    ns.append(results_mr[key].n[f_idx])
            ax.plot(ts, ns, marker=SAMPLE_MARKERS[rep - 1], color=SAMPLE_COLORS[rep - 1],
                    markersize=3, lw=0.4, label=f"S{rep}", alpha=0.6)

        # Mean ± σ
        mean_n = [avgs_mr[t].n[f_idx] for t in temps_list]
        std_n = [avgs_mr[t].n_std[f_idx] if avgs_mr[t].n_std is not None else 0
                 for t in temps_list]
        ax.errorbar(temps_list, mean_n, yerr=std_n, fmt="k-o", markersize=3.5,
                    lw=0.9, capsize=2, capthick=0.4, elinewidth=0.5,
                    zorder=10, label=r"Mean $\pm\sigma$")

        ax.set_title(f"{f_t:.2f} THz (R²={bf['R2']:.3f})")
        ax.set_xlabel(r"Temperature ($\degree$C)")
        if fi == 0:
            ax.set_ylabel("Refractive index, $n$")
        ax.set_ylim(*N_YLIM)
    axes[0].legend(fontsize=6.5, ncol=2, loc="lower left")
    fig.tight_layout(w_pad=1.0)
    save_fig(fig, "fig09_per_sample_n_3freq")


def fig10_per_sample_overview(results_mr, porosity_data, n_offset, best_freq, temps_list):
    """Per-sample temperature trends: n, α, ε', f_air — for outlier detection."""
    f_idx = best_freq["idx"]
    f_t = best_freq["freq_thz"]
    print(f"Fig.10: Per-sample overview @ {f_t:.2f} THz...")
    fig, axes = plt.subplots(2, 2, figsize=(DOUBLE_COL_W, DOUBLE_COL_H * 1.2))

    for rep in range(1, 6):
        ts, ns, alphas, epss, fairs = [], [], [], [], []
        for temp in temps_list:
            key = (temp, rep)
            if key not in results_mr:
                continue
            p = results_mr[key]
            n_val = p.n[f_idx]
            a_val = max(p.alpha[f_idx], 0.0)  # clip negative α
            e_val = n_val**2 - p.kappa[f_idx]**2
            f_val = invert_porosity_anchored(n_val, n_offset)

            ts.append(temp)
            ns.append(n_val)
            alphas.append(a_val)
            epss.append(e_val)
            fairs.append(f_val * 100 if not np.isnan(f_val) else np.nan)

        mk = SAMPLE_MARKERS[rep - 1]
        clr = SAMPLE_COLORS[rep - 1]
        label = f"S{rep}"
        axes[0, 0].plot(ts, ns, marker=mk, color=clr, markersize=3, lw=0.5, label=label)
        axes[0, 1].plot(ts, alphas, marker=mk, color=clr, markersize=3, lw=0.5, label=label)
        axes[1, 0].plot(ts, epss, marker=mk, color=clr, markersize=3, lw=0.5, label=label)
        axes[1, 1].plot(ts, fairs, marker=mk, color=clr, markersize=3, lw=0.5, label=label)

    labels = [
        (f"$n$ @ {f_t:.2f} THz", axes[0, 0]),
        (fr"$\alpha$ @ {f_t:.2f} THz (cm$^{{-1}}$)", axes[0, 1]),
        (fr"$\varepsilon'$ @ {f_t:.2f} THz", axes[1, 0]),
        (r"Porosity (%)", axes[1, 1]),
    ]
    for ylabel, ax in labels:
        ax.set_xlabel(r"Temperature ($\degree$C)")
        ax.set_ylabel(ylabel)
        auto_ylim(ax)
    axes[0, 0].set_ylim(*N_YLIM)
    # Single shared legend at top
    handles, lbls = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, lbls, fontsize=7.5, ncol=5, loc="upper center",
               bbox_to_anchor=(0.5, 1.02), frameon=True, edgecolor="0.8")

    fig.tight_layout(rect=[0, 0, 1, 0.96], w_pad=1.2, h_pad=1.2)
    save_fig(fig, "fig10_per_sample_overview")


def fig11_phase_spectrum(refs, samples):
    """Phase difference Δφ(f) between sample and matched reference."""
    print("Fig.11: Phase spectrum Δφ(f)...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(DOUBLE_COL_W, DOUBLE_COL_H))

    for temp in TEMPS:
        ref = refs[temp]
        key = (temp, 1)  # representative sample (S1)
        if key not in samples:
            continue
        sam = samples[key]
        ref_freq = compute_fft(ref, 2)
        sam_freq = compute_fft(sam, 2)
        H = compute_measured_transfer_function(ref_freq, sam_freq)
        freq_thz = ref_freq.freq_hz / 1e12
        valid = ~np.isnan(H) & (freq_thz >= 0.2) & (freq_thz <= 2.5)

        phase_diff = np.unwrap(np.angle(H[valid]))
        phase_smooth = median_filter(phase_diff, size=5)
        ax1.plot(freq_thz[valid], phase_smooth, color=get_temp_color(temp), lw=0.6)
        h_mag = np.abs(H[valid])
        h_smooth = median_filter(h_mag, size=9)
        ax2.plot(freq_thz[valid], h_smooth, color=get_temp_color(temp), lw=0.6)

    ax1.set_xlabel("Frequency (THz)")
    ax1.set_ylabel(r"Phase difference, $\Delta\varphi$ (rad)")
    ax1.set_xlim(0.2, 2.5)
    ax1.xaxis.set_major_locator(ticker.MultipleLocator(0.5))
    auto_ylim(ax1)

    ax2.set_xlabel("Frequency (THz)")
    ax2.set_ylabel(r"$|H(\omega)|$")
    ax2.set_xlim(0.2, 2.5)
    ax2.set_ylim(0.85, 1.05)
    ax2.xaxis.set_major_locator(ticker.MultipleLocator(0.5))

    make_temp_colorbar(ax2, fig)
    fig.tight_layout(w_pad=1.5)
    save_fig(fig, "fig11_phase_spectrum")


def fig12_snr_dynamic_range(refs, samples):
    """SNR and dynamic range of the THz measurement system."""
    print("Fig.12: SNR / Dynamic range...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(DOUBLE_COL_W, DOUBLE_COL_H))

    # Left: Spectral amplitude of reference at selected temperatures
    ref_temps_show = [20, 60, 110]
    for temp in ref_temps_show:
        if temp not in refs:
            continue
        ref = refs[temp]
        ref_freq = compute_fft(ref, 2)
        freq_thz = ref_freq.freq_hz / 1e12
        mask = (freq_thz >= 0.1) & (freq_thz <= 3.0)
        amp_db = 20 * np.log10(ref_freq.amplitude[mask] + 1e-30)
        ax1.plot(freq_thz[mask], amp_db, color=get_temp_color(temp), lw=0.8,
                 label=f"Ref {temp} °C")

    # Noise floor estimate: high-frequency tail (> 3 THz)
    ref20 = refs[20]
    ref20_freq = compute_fft(ref20, 2)
    freq_all = ref20_freq.freq_hz / 1e12
    noise_mask = freq_all > 3.0
    if np.any(noise_mask):
        noise_floor_db = np.median(20 * np.log10(ref20_freq.amplitude[noise_mask] + 1e-30))
        ax1.axhline(noise_floor_db, color="gray", ls="--", lw=0.6, label="Noise floor")

    ax1.set_xlabel("Frequency (THz)")
    ax1.set_ylabel("Spectral amplitude (dB)")
    ax1.set_xlim(0.1, 3.0)
    ax1.xaxis.set_major_locator(ticker.MultipleLocator(0.5))
    ax1.legend(fontsize=7.5)
    auto_ylim(ax1)

    # Right: SNR per temperature (ratio of peak amplitude to noise rms)
    snr_vals = []
    for temp in TEMPS:
        if temp not in refs:
            continue
        ref = refs[temp]
        ref_freq = compute_fft(ref, 2)
        freq_thz_r = ref_freq.freq_hz / 1e12
        sig_mask = (freq_thz_r >= 0.3) & (freq_thz_r <= 2.0)
        noise_mask_r = freq_thz_r > 3.0
        if np.any(sig_mask) and np.any(noise_mask_r):
            signal_peak = np.max(ref_freq.amplitude[sig_mask])
            noise_rms = np.sqrt(np.mean(ref_freq.amplitude[noise_mask_r]**2))
            snr_db = 20 * np.log10(signal_peak / noise_rms) if noise_rms > 0 else 0
            snr_vals.append((temp, snr_db))

    if snr_vals:
        ts, snrs = zip(*snr_vals)
        ax2.bar(ts, snrs, width=7, color=[get_temp_color(t) for t in ts],
                edgecolor="black", linewidth=0.4)
        ax2.set_xlabel(r"Temperature ($\degree$C)")
        ax2.set_ylabel("SNR (dB)")
        ax2.set_ylim(0, max(snrs) * 1.15)

        # Usable bandwidth annotation
        mean_snr = np.mean(snrs)
        ax2.axhline(mean_snr, color="gray", ls="--", lw=0.5)
        ax2.text(112, mean_snr + 0.5, f"Mean: {mean_snr:.0f} dB",
                 fontsize=8, va="bottom", ha="right")

    fig.tight_layout(w_pad=1.5)
    save_fig(fig, "fig12_snr_dynamic_range")


def fig_feature_illustration(refs, samples):
    """Annotated illustration of feature extraction — improved readability."""
    print("Fig: Feature extraction illustration (Appendix)...")
    fig, axes = plt.subplots(1, 3, figsize=(DOUBLE_COL_W * 1.4, DOUBLE_COL_H * 1.0))
    ANNOT_SIZE = 11  # 2× larger annotations
    bbox_white = dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85)

    ref = refs[20]
    sam = samples[(20, 1)]
    t_r, s_r = ref.time_ps, ref.signal
    t_s, s_s = sam.time_ps, sam.signal
    tf_r, sf_r, _ = interp_signal(t_r, s_r)
    t0 = tf_r[np.argmax(sf_r)]

    # ── (a) Time-domain — wider range ──
    ax = axes[0]
    t_plot = t_s - t0
    mask_t = (t_plot >= -1.2) & (t_plot <= 1.8)
    ax.plot(t_plot[mask_t], s_s[mask_t], "b-", lw=1.0, label="Sample")
    mask_r = ((t_r - t0) >= -1.2) & ((t_r - t0) <= 1.8)
    ax.plot(t_r[mask_r] - t0, s_r[mask_r], "k--", lw=0.7, alpha=0.5, label="Reference")

    t_m = t_plot[mask_t]
    s_m = s_s[mask_t]
    pos_i = np.argmax(s_m)
    neg_i = np.argmin(s_m)
    ax.annotate("peak_pos_amp", xy=(t_m[pos_i], s_m[pos_i]),
                xytext=(0.4, s_m[pos_i] * 0.7), fontsize=ANNOT_SIZE,
                arrowprops=dict(arrowstyle="->", lw=0.6, color="red"),
                color="red", bbox=bbox_white)
    ax.annotate("peak_neg_amp", xy=(t_m[neg_i], s_m[neg_i]),
                xytext=(0.5, s_m[neg_i] * 0.6), fontsize=ANNOT_SIZE,
                arrowprops=dict(arrowstyle="->", lw=0.6, color="red"),
                color="red", bbox=bbox_white)
    ax.annotate("", xy=(t_m[pos_i], s_m[pos_i] * 0.3),
                xytext=(0, s_m[pos_i] * 0.3),
                arrowprops=dict(arrowstyle="<->", lw=0.7, color="green"))
    ax.text(t_m[pos_i] / 2, s_m[pos_i] * 0.22, "dt_pos", fontsize=ANNOT_SIZE,
            ha="center", color="green", bbox=bbox_white)

    ax.set_xlabel("Time (ps)")
    ax.set_ylabel("Amplitude (a.u.)")
    ax.set_title("(a) Time-domain features", fontweight="bold")
    ax.legend(fontsize=8, loc="lower right")

    # ── (b) Envelope ──
    ax = axes[1]
    from scipy.signal import hilbert as hilbert_fn
    env = np.abs(hilbert_fn(s_s))
    ax.plot(t_plot[mask_t], s_m, "b-", lw=0.5, alpha=0.3)
    ax.plot(t_plot[mask_t], env[mask_t], "r-", lw=1.0, label="Envelope")

    env_m = env[mask_t]
    env_peak = np.max(env_m)
    hm = env_peak / 2
    above = env_m > hm
    if np.any(above):
        first = np.argmax(above)
        last = len(above) - 1 - np.argmax(above[::-1])
        ax.annotate("", xy=(t_m[first], hm), xytext=(t_m[last], hm),
                    arrowprops=dict(arrowstyle="<->", lw=0.8, color="purple"))
        ax.text((t_m[first] + t_m[last]) / 2, hm * 1.15, "env_fwhm",
                fontsize=ANNOT_SIZE, ha="center", color="purple", bbox=bbox_white)
    ax.axhline(hm, color="gray", ls=":", lw=0.4)
    ax.annotate("env_peak", xy=(t_m[np.argmax(env_m)], env_peak),
                xytext=(0.6, env_peak * 0.85), fontsize=ANNOT_SIZE,
                arrowprops=dict(arrowstyle="->", lw=0.6, color="red"),
                color="red", bbox=bbox_white)

    ax.set_xlabel("Time (ps)")
    ax.set_title("(b) Envelope features", fontweight="bold")
    ax.legend(fontsize=8, loc="lower right")

    # ── (c) Frequency-domain — white background for text ──
    ax = axes[2]
    dt = np.mean(np.diff(t_s)) * 1e-12
    n_pts = len(s_s)
    freq = np.fft.rfftfreq(n_pts, dt)
    freq_thz = freq / 1e12
    spectrum = np.fft.rfft(s_s * np.hanning(n_pts))
    amp = np.abs(spectrum)

    f_mask = (freq_thz >= 0.1) & (freq_thz <= 2.5)
    ax.plot(freq_thz[f_mask], amp[f_mask], "b-", lw=0.8)

    bands = [(0.3, 0.8, "low", "#1f77b4", 0.92),
             (0.8, 1.5, "mid", "#ff7f0e", 0.82),
             (1.5, 2.5, "high", "#2ca02c", 0.72)]
    y_max = np.max(amp[f_mask])
    for f_lo, f_hi, label, color, y_frac in bands:
        bm = (freq_thz >= f_lo) & (freq_thz <= f_hi)
        ax.fill_between(freq_thz[bm], 0, amp[bm], alpha=0.12, color=color)
        ax.text((f_lo + f_hi) / 2, y_max * y_frac, f"spec_{label}",
                fontsize=ANNOT_SIZE, ha="center", color=color, fontweight="bold",
                bbox=bbox_white, zorder=10)

    valid = (freq_thz >= 0.3) & (freq_thz <= 2.5) & (amp > 0)
    centroid = np.sum(freq_thz[valid] * amp[valid]) / np.sum(amp[valid])
    ax.axvline(centroid, color="red", ls="--", lw=0.6)
    ax.text(centroid + 0.12, y_max * 0.60, "spec_centroid",
            fontsize=ANNOT_SIZE, color="red", bbox=bbox_white, zorder=10)

    ax.set_xlabel("Frequency (THz)")
    ax.set_ylabel("Spectral amplitude")
    ax.set_title("(c) Frequency-domain features", fontweight="bold")
    ax.set_xlim(0.1, 2.5)

    fig.tight_layout(w_pad=1.2)
    save_fig(fig, "fig_feature_illustration")


def fig_drift_validation(data_dir):
    """Compare original and return reference signals to quantify instrument drift."""
    print("Fig: Drift validation (return refs)...")
    return_temps = [60, 70, 80, 90, 100, 110]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(DOUBLE_COL_W, DOUBLE_COL_H))

    drift_results = []
    for temp in return_temps:
        orig_path = data_dir / f"Ref_{temp}.txt"
        ret_path = data_dir / f"Ref_{temp}_return.txt"
        if not orig_path.exists() or not ret_path.exists():
            continue

        # Load both
        orig_data = np.loadtxt(str(orig_path), skiprows=6)
        ret_data = np.loadtxt(str(ret_path), skiprows=6)
        t_orig, s_orig = orig_data[:, 0], orig_data[:, 1]
        t_ret, s_ret = ret_data[:, 0], ret_data[:, 1]

        # Time-domain: peak amplitude difference
        min_len = min(len(s_orig), len(s_ret))
        delta = s_ret[:min_len] - s_orig[:min_len]
        peak_orig = np.max(np.abs(s_orig))
        drift_pct = np.max(np.abs(delta)) / peak_orig * 100

        # Plot difference
        ax1.plot(t_orig[:min_len], delta, color=get_temp_color(temp), lw=0.5,
                 label=f"{temp} \u00b0C")

        # Frequency domain: spectral difference
        dt = np.mean(np.diff(t_orig)) * 1e-12
        n_pts = min_len
        freq_hz = np.fft.rfftfreq(n_pts, dt)
        freq_thz = freq_hz / 1e12
        spec_orig = np.abs(np.fft.rfft(s_orig[:min_len] * np.hanning(min_len)))
        spec_ret = np.abs(np.fft.rfft(s_ret[:min_len] * np.hanning(min_len)))
        mask = (freq_thz >= 0.3) & (freq_thz <= 2.0)
        spec_diff_pct = np.mean(np.abs(spec_ret[mask] - spec_orig[mask]) / (spec_orig[mask] + 1e-30)) * 100

        drift_results.append({
            "Temperature (C)": temp,
            "Max drift (%)": f"{drift_pct:.2f}",
            "Spectral diff (%)": f"{spec_diff_pct:.2f}",
        })
        ax2.bar(temp, drift_pct, width=7, color=get_temp_color(temp),
                edgecolor="black", linewidth=0.4)

    ax1.set_xlabel("Time (ps)")
    ax1.set_ylabel("Signal drift (a.u.)")
    ax1.set_title("Ref \u2212 Ref_return")
    ax1.legend(fontsize=7, ncol=2)
    ax1.set_xlim(-5, 10)

    ax2.set_xlabel(r"Temperature ($\degree$C)")
    ax2.set_ylabel("Max drift (% of peak)")
    ax2.set_title("Drift magnitude")

    fig.tight_layout(w_pad=1.5)
    save_fig(fig, "fig_drift_validation")

    print("  Drift validation results:")
    for r in drift_results:
        print(f"    {r['Temperature (C)']} \u00b0C: max={r['Max drift (%)']}, "
              f"spectral={r['Spectral diff (%)']}")
    pd.DataFrame(drift_results).to_csv(CSV_DIR / "drift_validation.csv", index=False)
    return drift_results


def anova_temperature_test(results_mr, avgs_mr, best_freqs, temps_list):
    """One-way ANOVA for n across temperatures — full frequency scan + best freqs."""
    print("\nANOVA: n vs Temperature (full frequency scan)...")
    print("=" * 70)

    # ── Full frequency scan ──
    freq_hz = avgs_mr[temps_list[0]].freq_hz
    freq_thz = freq_hz / 1e12
    scan_mask = (freq_thz >= 0.3) & (freq_thz <= 2.0)
    scan_indices = np.where(scan_mask)[0]

    scan_freqs, scan_F, scan_p, scan_eta = [], [], [], []
    for idx in scan_indices:
        groups = []
        for temp in temps_list:
            vals = [results_mr[(temp, r)].n[idx] for r in range(1, 6)
                    if (temp, r) in results_mr]
            if vals:
                groups.append(vals)
        if len(groups) < 2:
            continue
        all_vals_flat = [v for g in groups for v in g]
        if not np.all(np.isfinite(all_vals_flat)):
            continue
        F_stat, p_val = f_oneway(*groups)
        grand_mean = np.mean(all_vals_flat)
        ss_b = sum(len(g) * (np.mean(g) - grand_mean)**2 for g in groups)
        ss_t = sum((v - grand_mean)**2 for v in all_vals_flat)
        eta = ss_b / ss_t if ss_t > 0 else 0
        scan_freqs.append(freq_thz[idx])
        scan_F.append(F_stat)
        scan_p.append(p_val)
        scan_eta.append(eta)

    scan_freqs = np.array(scan_freqs)
    scan_F = np.array(scan_F)
    scan_p = np.array(scan_p)
    scan_eta = np.array(scan_eta)

    n_sig = np.sum(scan_p < 0.05)
    n_total = len(scan_p)
    print(f"  Scanned {n_total} frequencies (0.3–2.0 THz)")
    print(f"  Significant (p<0.05): {n_sig}/{n_total} ({n_sig/n_total*100:.1f}%)")

    # Identify contiguous significant bands
    sig_mask = scan_p < 0.05
    bands = []
    in_band = False
    for i, s in enumerate(sig_mask):
        if s and not in_band:
            band_start = scan_freqs[i]
            in_band = True
        elif not s and in_band:
            bands.append((band_start, scan_freqs[i - 1]))
            in_band = False
    if in_band:
        bands.append((band_start, scan_freqs[-1]))
    if bands:
        print("  Significant bands:")
        for b in bands:
            print(f"    {b[0]:.3f}–{b[1]:.3f} THz")

    # ── Fig.13: ANOVA frequency scan ──
    print("Fig.13: ANOVA frequency scan...")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(SINGLE_COL_W * 1.3, SINGLE_COL_H * 1.6),
                                    sharex=True)
    ax1.semilogy(scan_freqs, scan_p, "k-", lw=0.7)
    ax1.axhline(0.05, color="red", ls="--", lw=0.6, label="$p$ = 0.05")
    ax1.axhline(0.01, color="orange", ls=":", lw=0.5, label="$p$ = 0.01")
    ax1.axhline(0.001, color="green", ls=":", lw=0.5, label="$p$ = 0.001")
    # Shade significant regions
    ax1.fill_between(scan_freqs, 0, 1, where=sig_mask,
                     alpha=0.15, color="blue", transform=ax1.get_xaxis_transform())
    for bf in best_freqs:
        ax1.axvline(bf["freq_thz"], color="gray", ls=":", lw=0.4, alpha=0.5)
    ax1.set_ylabel("$p$-value (ANOVA)")
    ax1.set_ylim(1e-5, 1.0)
    ax1.legend(fontsize=7, loc="upper left")
    ax1.invert_yaxis()

    ax2.plot(scan_freqs, scan_eta, "k-", lw=0.7)
    ax2.fill_between(scan_freqs, 0, scan_eta, where=sig_mask,
                     alpha=0.3, color="steelblue", label="$p$ < 0.05")
    ax2.fill_between(scan_freqs, 0, scan_eta, where=~sig_mask,
                     alpha=0.15, color="gray", label="$p$ ≥ 0.05")
    for bf in best_freqs:
        ax2.axvline(bf["freq_thz"], color="gray", ls=":", lw=0.4, alpha=0.5)
    ax2.set_xlabel("Frequency (THz)")
    ax2.set_ylabel(r"Effect size, $\eta^2$")
    ax2.set_xlim(0.3, 2.0)
    ax2.set_ylim(0, 1.0)
    ax2.axhline(0.14, color="red", ls="--", lw=0.4, alpha=0.5)
    ax2.text(0.32, 0.16, "large effect", fontsize=10, color="red", alpha=0.8,
             bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.7))
    ax2.legend(fontsize=7, loc="upper right")

    fig.tight_layout(h_pad=0.5)
    save_fig(fig, "fig13_anova_freq_scan")

    # ── Summary table: best freqs ──
    anova_rows = []
    print(f"\n  {'Freq (THz)':>10}  {'F':>7}  {'p':>10}  {'η²':>6}  {'Sig':>4}")
    print("  " + "-" * 45)
    for bf in best_freqs:
        f_idx = bf["idx"]
        f_t = bf["freq_thz"]
        groups = []
        for temp in temps_list:
            vals = [results_mr[(temp, r)].n[f_idx] for r in range(1, 6)
                    if (temp, r) in results_mr]
            if vals:
                groups.append(vals)
        F_stat, p_val = f_oneway(*groups)
        all_v = [v for g in groups for v in g]
        gm = np.mean(all_v)
        ss_b = sum(len(g) * (np.mean(g) - gm)**2 for g in groups)
        ss_t = sum((v - gm)**2 for v in all_v)
        eta_sq = ss_b / ss_t if ss_t > 0 else 0
        sig = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else "ns"
        anova_rows.append({
            "Frequency (THz)": f"{f_t:.3f}", "F-statistic": f"{F_stat:.2f}",
            "p-value": f"{p_val:.2e}", "Significance": sig,
            "eta_squared": f"{eta_sq:.4f}", "n_groups": len(groups),
            "n_total": len(all_v),
        })
        print(f"  {f_t:>10.3f}  {F_stat:>7.2f}  {p_val:>10.2e}  {eta_sq:>6.4f}  {sig:>4}")

    # ── Pairwise t-test (adjacent temps) at primary freq ──
    bf0 = best_freqs[0]
    f_idx0 = bf0["idx"]
    print(f"\n  Pairwise t-test (adjacent temps) @ {bf0['freq_thz']:.3f} THz:")
    pairwise_rows = []
    for i in range(len(temps_list) - 1):
        t1, t2 = temps_list[i], temps_list[i + 1]
        g1 = [results_mr[(t1, r)].n[f_idx0] for r in range(1, 6)
              if (t1, r) in results_mr]
        g2 = [results_mr[(t2, r)].n[f_idx0] for r in range(1, 6)
              if (t2, r) in results_mr]
        if len(g1) >= 2 and len(g2) >= 2:
            t_stat, p_pw = ttest_ind(g1, g2)
            sig_pw = "***" if p_pw < 0.001 else "**" if p_pw < 0.01 else "*" if p_pw < 0.05 else "ns"
            delta_n = np.mean(g2) - np.mean(g1)
            pairwise_rows.append({
                "T1 (C)": t1, "T2 (C)": t2, "delta_n": f"{delta_n:+.4f}",
                "t-statistic": f"{t_stat:.3f}", "p-value": f"{p_pw:.3e}",
                "Significance": sig_pw,
            })
            print(f"    {t1}→{t2} °C: Δn={delta_n:+.4f}, t={t_stat:.3f}, "
                  f"p={p_pw:.3e} {sig_pw}")

    # ── Pairwise: 20°C vs each temperature (wide gap) ──
    print(f"\n  Pairwise t-test (20°C vs each) @ {bf0['freq_thz']:.3f} THz:")
    wide_rows = []
    g_20 = [results_mr[(20, r)].n[f_idx0] for r in range(1, 6) if (20, r) in results_mr]
    for temp in temps_list[1:]:
        g_t = [results_mr[(temp, r)].n[f_idx0] for r in range(1, 6)
               if (temp, r) in results_mr]
        if len(g_20) >= 2 and len(g_t) >= 2:
            t_stat, p_pw = ttest_ind(g_20, g_t)
            sig_pw = "***" if p_pw < 0.001 else "**" if p_pw < 0.01 else "*" if p_pw < 0.05 else "ns"
            delta_n = np.mean(g_t) - np.mean(g_20)
            wide_rows.append({
                "T_ref (C)": 20, "T_comp (C)": temp, "delta_n": f"{delta_n:+.4f}",
                "t-statistic": f"{t_stat:.3f}", "p-value": f"{p_pw:.3e}",
                "Significance": sig_pw,
            })
            print(f"    20→{temp} °C: Δn={delta_n:+.4f}, t={t_stat:.3f}, "
                  f"p={p_pw:.3e} {sig_pw}")

    # ── Export all ──
    # Full scan
    scan_df = pd.DataFrame({
        "Frequency (THz)": scan_freqs, "F-statistic": scan_F,
        "p-value": scan_p, "eta_squared": scan_eta,
        "Significant": ["*" if p < 0.05 else "" for p in scan_p],
    })
    scan_df.to_csv(CSV_DIR / "table05_anova_freq_scan.csv", index=False)
    pd.DataFrame(anova_rows).to_csv(CSV_DIR / "table05b_anova_best_freqs.csv", index=False)
    if pairwise_rows:
        pd.DataFrame(pairwise_rows).to_csv(CSV_DIR / "table06_pairwise_ttest.csv", index=False)
    if wide_rows:
        pd.DataFrame(wide_rows).to_csv(CSV_DIR / "table06b_pairwise_vs_20c.csv", index=False)

    return anova_rows, pairwise_rows


def analyze_sample_groups(results_mr, avgs_mr, best_freq, temps_list):
    """Analyze S1-S3 vs S4-S5 systematic offset."""
    f_idx = best_freq["idx"]
    f_t = best_freq["freq_thz"]
    print(f"\nSample Group Analysis (S1-S3 vs S4-S5) @ {f_t:.2f} THz...")
    print("=" * 70)

    # Collect all n values for each group
    group_a_all, group_b_all = [], []  # A=S1-S3, B=S4-S5
    group_a_by_temp, group_b_by_temp = {}, {}
    for temp in temps_list:
        a_vals, b_vals = [], []
        for rep in range(1, 6):
            key = (temp, rep)
            if key not in results_mr:
                continue
            n_val = results_mr[key].n[f_idx]
            if rep <= 3:
                a_vals.append(n_val)
                group_a_all.append(n_val)
            else:
                b_vals.append(n_val)
                group_b_all.append(n_val)
        group_a_by_temp[temp] = a_vals
        group_b_by_temp[temp] = b_vals

    mean_a, mean_b = np.mean(group_a_all), np.mean(group_b_all)
    std_a, std_b = np.std(group_a_all), np.std(group_b_all)
    offset = mean_a - mean_b

    print(f"  S1-S3: n = {mean_a:.4f} ± {std_a:.4f} (N={len(group_a_all)})")
    print(f"  S4-S5: n = {mean_b:.4f} ± {std_b:.4f} (N={len(group_b_all)})")
    print(f"  Offset: Δn = {offset:+.4f}")

    # Statistical test
    t_stat, p_val = ttest_ind(group_a_all, group_b_all)
    u_stat, p_mw = mannwhitneyu(group_a_all, group_b_all, alternative="two-sided")
    sig = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else "ns"
    print(f"  t-test: t={t_stat:.3f}, p={p_val:.2e} {sig}")
    print(f"  Mann-Whitney U: U={u_stat:.0f}, p={p_mw:.2e}")

    # Per-temperature offset
    print(f"\n  {'Temp':>6}  {'S1-S3':>10}  {'S4-S5':>10}  {'Δn':>8}  {'t':>7}  {'p':>10}")
    print("  " + "-" * 55)
    per_temp_rows = []
    for temp in temps_list:
        a, b = group_a_by_temp.get(temp, []), group_b_by_temp.get(temp, [])
        if len(a) >= 2 and len(b) >= 2:
            t_s, p_s = ttest_ind(a, b)
            sig_s = "***" if p_s < 0.001 else "**" if p_s < 0.01 else "*" if p_s < 0.05 else "ns"
            dn = np.mean(a) - np.mean(b)
            per_temp_rows.append({
                "Temperature (C)": temp,
                "n_S1S3": f"{np.mean(a):.4f} ± {np.std(a):.4f}",
                "n_S4S5": f"{np.mean(b):.4f} ± {np.std(b):.4f}",
                "delta_n": f"{dn:+.4f}", "t-statistic": f"{t_s:.3f}",
                "p-value": f"{p_s:.3e}", "Significance": sig_s,
            })
            print(f"  {temp:>6}  {np.mean(a):>10.4f}  {np.mean(b):>10.4f}  "
                  f"{dn:>+8.4f}  {t_s:>7.3f}  {p_s:>10.3e} {sig_s}")

    # Slope comparison: does the TREND differ?
    a_means = [np.mean(group_a_by_temp[t]) for t in temps_list if group_a_by_temp.get(t)]
    b_means = [np.mean(group_b_by_temp[t]) for t in temps_list if group_b_by_temp.get(t)]
    sl_a = linregress(temps_list, a_means)
    sl_b = linregress(temps_list, b_means)
    print(f"\n  Slope S1-S3: {sl_a.slope:.4e}/°C (R²={sl_a.rvalue**2:.3f})")
    print(f"  Slope S4-S5: {sl_b.slope:.4e}/°C (R²={sl_b.rvalue**2:.3f})")
    print(f"  → 기울기 차이: {abs(sl_a.slope - sl_b.slope):.4e}/°C")
    if abs(sl_a.slope - sl_b.slope) / max(abs(sl_a.slope), abs(sl_b.slope), 1e-15) < 0.3:
        print("  → 두 그룹의 온도 의존성(기울기)은 유사 — 절편 차이(offset)가 주 원인")
    else:
        print("  → 두 그룹의 온도 의존성(기울기)이 다름 — 구조적 차이 가능")

    # Possible cause: estimate thickness difference
    # Δn ≈ (n-1) * Δd/d for thin film
    n_eff = np.mean(group_a_all + group_b_all)
    d_nom = THICKNESS_MM * 1e3  # μm
    delta_d = offset / (n_eff - 1) * d_nom
    print(f"\n  두께 차이 추정 (n_eff={n_eff:.3f}):")
    print(f"    Δd ≈ {delta_d:+.1f} μm (S1-S3이 S4-S5보다 두꺼움)")
    print(f"    즉, S4/S5의 유효 두께가 ~{d_nom - abs(delta_d):.1f} μm일 가능성")

    # Export
    pd.DataFrame(per_temp_rows).to_csv(CSV_DIR / "table07_sample_groups.csv", index=False)

    # Fig.14: Group comparison
    print("Fig.14: Sample group comparison...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(DOUBLE_COL_W, DOUBLE_COL_H))

    # Left: per-group n(T)
    a_m = [np.mean(group_a_by_temp[t]) for t in temps_list]
    a_s = [np.std(group_a_by_temp[t]) for t in temps_list]
    b_m = [np.mean(group_b_by_temp[t]) for t in temps_list]
    b_s = [np.std(group_b_by_temp[t]) for t in temps_list]

    ax1.errorbar(temps_list, a_m, yerr=a_s, fmt="o-", color="#1f77b4",
                 markersize=4, lw=0.9, capsize=2.5, capthick=0.4, label="S1–S3")
    ax1.errorbar(temps_list, b_m, yerr=b_s, fmt="s-", color="#d62728",
                 markersize=4, lw=0.9, capsize=2.5, capthick=0.4, label="S4–S5")
    # Trend lines
    x_fit = np.linspace(15, 115, 100)
    ax1.plot(x_fit, sl_a.slope * x_fit + sl_a.intercept, "--", color="#1f77b4",
             lw=0.5, alpha=0.6)
    ax1.plot(x_fit, sl_b.slope * x_fit + sl_b.intercept, "--", color="#d62728",
             lw=0.5, alpha=0.6)
    ax1.set_xlabel(r"Temperature ($\degree$C)")
    ax1.set_ylabel(f"$n$ @ {f_t:.2f} THz")
    ax1.set_ylim(*N_YLIM)
    ax1.legend(fontsize=8)
    ax1.text(0.03, 0.03, f"Offset: Δn = {offset:+.3f}\n(p = {p_val:.1e})",
             transform=ax1.transAxes, fontsize=8, va="bottom",
             bbox=dict(boxstyle="round", fc="lightyellow", alpha=0.8, pad=0.3))

    # Right: histogram of all n values by group
    ax2.hist(group_a_all, bins=15, alpha=0.6, color="#1f77b4", label="S1–S3",
             edgecolor="white", linewidth=0.3)
    ax2.hist(group_b_all, bins=15, alpha=0.6, color="#d62728", label="S4–S5",
             edgecolor="white", linewidth=0.3)
    ax2.axvline(mean_a, color="#1f77b4", ls="--", lw=0.8)
    ax2.axvline(mean_b, color="#d62728", ls="--", lw=0.8)
    ax2.set_xlabel(f"$n$ @ {f_t:.2f} THz")
    ax2.set_ylabel("Count")
    ax2.legend(fontsize=8)

    fig.tight_layout(w_pad=1.5)
    save_fig(fig, "fig14_sample_groups")

    return {"offset": offset, "p_value": p_val, "delta_d_um": delta_d,
            "slope_a": sl_a.slope, "slope_b": sl_b.slope}


def ema_2phase_vs_3phase(avgs_mr, porosity_data, n_offset, best_freq, temps_list):
    """Compare 2-phase vs 3-phase Bruggeman EMA models."""
    f_idx = best_freq["idx"]
    f_t = best_freq["freq_thz"]
    print(f"\nEMA Model Comparison (2-phase vs 3-phase) @ {f_t:.2f} THz...")
    print("=" * 70)

    # 2-phase (primary) vs 3-phase (comparison)
    print(f"  n_PE_eff (2-phase) = {N_PE_EFF:.4f} "
          f"(= {CRYSTALLINITY:.1%} × {N_PE_CRYST} + {1-CRYSTALLINITY:.1%} × {N_PE_AMORPH})")
    print(f"  n_PE_cryst = {N_PE_CRYST}, n_PE_amorph = {N_PE_AMORPH}")

    # Compare models
    rows = []
    print(f"\n  {'Temp':>6}  {'n_corr':>8}  {'f3ph(%)':>8}  {'f2ph(%)':>8}  {'Δf(%)':>7}")
    print("  " + "-" * 45)
    for temp in temps_list:
        n_meas = avgs_mr[temp].n[f_idx]
        n_corr = n_meas - n_offset

        # 3-phase (current)
        f3 = porosity_data.get(temp, {}).get("mean", np.nan)
        # 2-phase
        # Need offset for 2-phase model too (anchor to 44% at 20°C)
        n_2ph_spec = bruggeman_2phase(F_AIR_SPEC)
        n_offset_2ph = avgs_mr[20].n[f_idx] - n_2ph_spec
        n_corr_2ph = n_meas - n_offset_2ph
        f2 = invert_porosity(n_corr_2ph)

        delta = (f3 - f2) * 100 if not (np.isnan(f3) or np.isnan(f2)) else np.nan
        rows.append({
            "Temperature (C)": temp,
            "n_corrected": f"{n_corr:.4f}",
            "Porosity_3phase (%)": f"{f3*100:.1f}" if not np.isnan(f3) else "",
            "Porosity_2phase (%)": f"{f2*100:.1f}" if not np.isnan(f2) else "",
            "delta_f (%)": f"{delta:.1f}" if not np.isnan(delta) else "",
        })
        print(f"  {temp:>6}  {n_corr:>8.4f}  {f3*100:>8.1f}  {f2*100:>8.1f}  {delta:>+7.1f}")

    # Theoretical comparison: f_air sweep
    f_sweep = np.linspace(0.01, 0.90, 200)
    n_3ph = [bruggeman_3phase(f) for f in f_sweep]
    n_2ph = [bruggeman_2phase(f) for f in f_sweep]

    # Fig.15: EMA model comparison
    print("Fig.15: EMA 2-phase vs 3-phase comparison...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(DOUBLE_COL_W, DOUBLE_COL_H))

    # Left: n_eff(f_air) for both models
    ax1.plot(f_sweep * 100, n_3ph, "b-", lw=1.0, label="3-phase (cryst + amorph + air)")
    ax1.plot(f_sweep * 100, n_2ph, "r--", lw=1.0, label=f"2-phase ($n_{{PE}}$={N_PE_EFF:.3f} + air)")
    ax1.axhspan(min(n_corr, n_corr - 0.08), max(n_corr, n_corr + 0.02),
                alpha=0.1, color="green", label="Measured range")
    ax1.set_xlabel(r"Porosity (%)")
    ax1.set_ylabel(r"$n_{eff}$")
    ax1.set_xlim(0, 80)
    ax1.set_ylim(0.95, 1.6)
    ax1.legend(fontsize=7)
    ax1.axvline(F_AIR_SPEC * 100, color="gray", ls=":", lw=0.4)
    ax1.text(F_AIR_SPEC * 100 + 1, 1.55, "Spec 44%", fontsize=7, color="gray")

    # Right: f_air(T) for both models
    f3_vals = [porosity_data.get(t, {}).get("mean", np.nan) * 100 for t in temps_list]
    n_offset_2ph = avgs_mr[20].n[f_idx] - bruggeman_2phase(F_AIR_SPEC)
    f2_vals = [invert_porosity(avgs_mr[t].n[f_idx] - n_offset_2ph) * 100 for t in temps_list]

    ax2.plot(temps_list, f3_vals, "bo-", markersize=4, lw=0.9, label="3-phase")
    ax2.plot(temps_list, f2_vals, "rs--", markersize=4, lw=0.9, label="2-phase")
    ax2.set_xlabel(r"Temperature ($\degree$C)")
    ax2.set_ylabel(r"Porosity (%)")
    ax2.legend(fontsize=8)
    ax2.set_ylim(30, 75)

    # Max difference annotation
    diffs = [abs(f3_vals[i] - f2_vals[i]) for i in range(len(temps_list))
             if not (np.isnan(f3_vals[i]) or np.isnan(f2_vals[i]))]
    max_diff = max(diffs) if diffs else 0
    ax2.text(0.97, 0.03, f"Max Δf = {max_diff:.1f}%p",
             transform=ax2.transAxes, fontsize=8, ha="right", va="bottom",
             bbox=dict(boxstyle="round", fc="lightyellow", alpha=0.8, pad=0.3))

    fig.tight_layout(w_pad=1.5)
    save_fig(fig, "fig15_ema_model_comparison")

    pd.DataFrame(rows).to_csv(CSV_DIR / "table08_ema_comparison.csv", index=False)
    print(f"\n  n_PE_eff (2-phase) = {N_PE_EFF:.4f}")
    print(f"  Max |ΔPorosity| = {max_diff:.1f}%p")
    print(f"  → 2상/3상 차이가 {'작음 (<2%p): 2상 모델 사용 가능' if max_diff < 2 else '큼: 3상 모델 권장'}")

    return rows


def apply_fdr_correction(pairwise_rows):
    """Apply Benjamini-Hochberg FDR correction to pairwise p-values."""
    print("\nFDR correction (Benjamini-Hochberg)...")
    if not pairwise_rows:
        return pairwise_rows
    p_vals = np.array([float(r["p-value"]) for r in pairwise_rows])
    n = len(p_vals)
    ranked = np.argsort(p_vals)
    p_adj = np.zeros(n)
    for i in range(n - 1, -1, -1):
        rank = i + 1
        idx = ranked[i]
        if i == n - 1:
            p_adj[idx] = p_vals[idx] * n / rank
        else:
            p_adj[idx] = min(p_vals[idx] * n / rank, p_adj[ranked[i + 1]])
    p_adj = np.clip(p_adj, 0, 1)

    print(f"  {'Comparison':>15}  {'p_raw':>10}  {'p_FDR':>10}  {'Sig':>4}")
    print("  " + "-" * 45)
    for i, r in enumerate(pairwise_rows):
        sig_fdr = "***" if p_adj[i] < 0.001 else "**" if p_adj[i] < 0.01 else "*" if p_adj[i] < 0.05 else "ns"
        r["p_FDR"] = f"{p_adj[i]:.3e}"
        r["Sig_FDR"] = sig_fdr
        label = f"{r.get('T_ref (C)', r.get('T1 (C)', ''))}→{r.get('T_comp (C)', r.get('T2 (C)', ''))}°C"
        print(f"  {label:>15}  {r['p-value']:>10}  {p_adj[i]:>10.3e}  {sig_fdr:>4}")
    return pairwise_rows


def bootstrap_ci(results_mr, avgs_mr, best_freq, temps_list, n_boot=1000):
    """Bootstrap confidence intervals for n(T) and f_air(T)."""
    f_idx = best_freq["idx"]
    f_t = best_freq["freq_thz"]
    print(f"\nBootstrap CI (B={n_boot}) @ {f_t:.2f} THz...")
    rng = np.random.default_rng(42)

    rows = []
    for temp in temps_list:
        vals = [results_mr[(temp, r)].n[f_idx] for r in range(1, 6)
                if (temp, r) in results_mr]
        n_rep = len(vals)
        if n_rep < 2:
            continue
        vals = np.array(vals)
        boot_means = np.array([rng.choice(vals, size=n_rep, replace=True).mean()
                               for _ in range(n_boot)])
        ci_lo, ci_hi = np.percentile(boot_means, [2.5, 97.5])
        rows.append({
            "Temperature (C)": temp,
            "n_mean": f"{np.mean(vals):.4f}",
            "n_std": f"{np.std(vals):.4f}",
            "CI_2.5%": f"{ci_lo:.4f}",
            "CI_97.5%": f"{ci_hi:.4f}",
            "CI_width": f"{ci_hi - ci_lo:.4f}",
        })

    print(f"  {'Temp':>6}  {'n_mean':>8}  {'σ':>8}  {'95% CI':>20}  {'width':>8}")
    print("  " + "-" * 55)
    for r in rows:
        print(f"  {r['Temperature (C)']:>6}  {r['n_mean']:>8}  {r['n_std']:>8}  "
              f"[{r['CI_2.5%']}, {r['CI_97.5%']}]  {r['CI_width']:>8}")

    pd.DataFrame(rows).to_csv(CSV_DIR / "table09_bootstrap_ci.csv", index=False)
    return rows


def propagate_n_offset_uncertainty(avgs_mr, porosity_data, n_offset, best_freq, temps_list):
    """Propagate n_offset uncertainty to corrected n and f_air."""
    f_idx = best_freq["idx"]
    f_t = best_freq["freq_thz"]
    print(f"\nn_offset uncertainty propagation @ {f_t:.2f} THz...")

    # σ(n_offset) from σ(n@20°C) — offset is anchored to 20°C measurement
    n_20_std = avgs_mr[20].n_std[f_idx] if avgs_mr[20].n_std is not None else 0.02
    sigma_offset = n_20_std  # 1st-order: σ(offset) ≈ σ(n@20°C)
    print(f"  σ(n_offset) = σ(n@20°C) = {sigma_offset:.4f}")

    rows = []
    for temp in temps_list:
        n_meas = avgs_mr[temp].n[f_idx]
        n_meas_std = avgs_mr[temp].n_std[f_idx] if avgs_mr[temp].n_std is not None else 0
        n_corr = n_meas - n_offset
        # σ(n_corr) = sqrt(σ(n_meas)² + σ(n_offset)²)
        sigma_corr = np.sqrt(n_meas_std**2 + sigma_offset**2)

        f_air = porosity_data.get(temp, {}).get("mean", np.nan)
        f_air_std = porosity_data.get(temp, {}).get("std", np.nan)
        # Propagate to f_air: df/dn × σ(n_corr)
        # f_air = Bruggeman^{-1}(n_corr), use numerical derivative
        dn = 0.001
        f_plus = invert_porosity(n_corr + dn)
        f_minus = invert_porosity(n_corr - dn)
        if not (np.isnan(f_plus) or np.isnan(f_minus)):
            df_dn = (f_plus - f_minus) / (2 * dn)
            sigma_f_prop = abs(df_dn) * sigma_corr
            sigma_f_total = np.sqrt(f_air_std**2 + sigma_f_prop**2) if not np.isnan(f_air_std) else sigma_f_prop
        else:
            sigma_f_prop = np.nan
            sigma_f_total = np.nan

        rows.append({
            "Temperature (C)": temp,
            "n_corr": f"{n_corr:.4f}", "sigma_n_corr": f"{sigma_corr:.4f}",
            "porosity_pct": f"{f_air*100:.1f}" if not np.isnan(f_air) else "",
            "sigma_f_sample_pct": f"{f_air_std*100:.1f}" if not np.isnan(f_air_std) else "",
            "sigma_f_prop_pct": f"{sigma_f_prop*100:.1f}" if not np.isnan(sigma_f_prop) else "",
            "sigma_f_total_pct": f"{sigma_f_total*100:.1f}" if not np.isnan(sigma_f_total) else "",
        })

    print(f"\n  {'Temp':>6}  {'n_corr':>8}  {'σ(n)':>8}  {'poros%':>8}  {'σ_samp%':>8}  {'σ_prop%':>8}  {'σ_tot%':>8}")
    print("  " + "-" * 65)
    for r in rows:
        print(f"  {r['Temperature (C)']:>6}  {r['n_corr']:>8}  {r['sigma_n_corr']:>8}  "
              f"{r['porosity_pct']:>8}  {r['sigma_f_sample_pct']:>8}  {r['sigma_f_prop_pct']:>8}  {r['sigma_f_total_pct']:>8}")

    pd.DataFrame(rows).to_csv(CSV_DIR / "table10_uncertainty_propagation.csv", index=False)
    return rows


def compare_models_aic(temps_list, mean_n):
    """Compare piecewise linear vs single linear vs sigmoid models using AIC/BIC."""
    print("\nModel comparison (AIC/BIC)...")
    T = np.array(temps_list, dtype=float)
    y = np.array(mean_n, dtype=float)
    n = len(T)

    def aic(rss, k):
        return n * np.log(rss / n) + 2 * k

    def bic(rss, k):
        return n * np.log(rss / n) + k * np.log(n)

    # Model 1: Single linear
    sl = linregress(T, y)
    rss_lin = np.sum((y - sl.slope * T - sl.intercept)**2)
    k_lin = 2
    aic_lin, bic_lin = aic(rss_lin, k_lin), bic(rss_lin, k_lin)

    # Model 2: Quadratic
    coeffs2 = np.polyfit(T, y, 2)
    rss_quad = np.sum((y - np.polyval(coeffs2, T))**2)
    k_quad = 3
    aic_quad, bic_quad = aic(rss_quad, k_quad), bic(rss_quad, k_quad)

    # Model 3: Piecewise linear (current)
    two_reg = fit_two_regime(T, y)
    r1, r2 = two_reg["regime1"], two_reg["regime2"]
    T_br = two_reg["T_break_opt"]
    pred_pw = np.where(T <= T_br,
                       r1.slope * T + r1.intercept,
                       r2.slope * T + r2.intercept)
    rss_pw = np.sum((y - pred_pw)**2)
    k_pw = 5  # 2 slopes + 2 intercepts + breakpoint
    aic_pw, bic_pw = aic(rss_pw, k_pw), bic(rss_pw, k_pw)

    # Model 4: Sigmoid (logistic)
    def sigmoid(T, a, b, c, d):
        return a + (b - a) / (1 + np.exp(-(T - c) / d))
    try:
        popt_sig, _ = curve_fit(sigmoid, T, y, p0=[y[-1], y[0], 50, 10],
                                maxfev=5000)
        rss_sig = np.sum((y - sigmoid(T, *popt_sig))**2)
        k_sig = 4
        aic_sig, bic_sig = aic(rss_sig, k_sig), bic(rss_sig, k_sig)
    except Exception:
        rss_sig, aic_sig, bic_sig = np.inf, np.inf, np.inf
        popt_sig = None

    models = [
        {"Model": "Linear", "k": k_lin, "RSS": rss_lin, "AIC": aic_lin, "BIC": bic_lin},
        {"Model": "Quadratic", "k": k_quad, "RSS": rss_quad, "AIC": aic_quad, "BIC": bic_quad},
        {"Model": "Piecewise", "k": k_pw, "RSS": rss_pw, "AIC": aic_pw, "BIC": bic_pw},
        {"Model": "Sigmoid", "k": k_sig if popt_sig is not None else 4,
         "RSS": rss_sig, "AIC": aic_sig, "BIC": bic_sig},
    ]

    best_aic = min(models, key=lambda m: m["AIC"])
    print(f"\n  {'Model':>12}  {'k':>3}  {'RSS':>10}  {'AIC':>8}  {'BIC':>8}  {'ΔAIC':>6}")
    print("  " + "-" * 55)
    for m in models:
        daic = m["AIC"] - best_aic["AIC"]
        star = " ★" if daic == 0 else ""
        print(f"  {m['Model']:>12}  {m['k']:>3}  {m['RSS']:>10.6f}  "
              f"{m['AIC']:>8.2f}  {m['BIC']:>8.2f}  {daic:>+6.2f}{star}")

    print(f"\n  Best model (AIC): {best_aic['Model']}")
    if best_aic["Model"] != "Piecewise":
        print(f"  ⚠ Current piecewise model is NOT best by AIC (ΔAIC={aic_pw - best_aic['AIC']:+.2f})")
    else:
        print(f"  ✓ Current piecewise model is best by AIC")

    pd.DataFrame(models).to_csv(CSV_DIR / "table11_model_comparison.csv", index=False)
    return models


def detect_outliers(results_mr, temps_list, best_freq):
    """Detect outlier samples based on deviation from mean at each temperature."""
    f_idx = best_freq["idx"]
    f_t = best_freq["freq_thz"]
    print(f"\nOutlier Detection @ {f_t:.2f} THz...")
    print("=" * 70)

    sample_stats = {}
    for rep in range(1, 6):
        ts, ns = [], []
        for temp in temps_list:
            key = (temp, rep)
            if key in results_mr:
                ts.append(temp)
                ns.append(results_mr[key].n[f_idx])
        if len(ts) >= 5:
            r, p = pearsonr(ts, ns)
            sl = linregress(ts, ns)
            sample_stats[rep] = {
                "R": r, "R2": r**2, "p": p, "slope": sl.slope,
                "n_mean": np.mean(ns), "n_std": np.std(ns),
                "temps": ts, "n_vals": ns,
            }

    # Compute mean n(T) across all samples
    mean_n_per_temp = {}
    for temp in temps_list:
        vals = []
        for rep in range(1, 6):
            key = (temp, rep)
            if key in results_mr:
                vals.append(results_mr[key].n[f_idx])
        if vals:
            mean_n_per_temp[temp] = {"mean": np.mean(vals), "std": np.std(vals)}

    # Per-sample deviation from mean
    print(f"\n{'Sample':>8}  {'<n>':>8}  {'R²':>6}  {'slope/°C':>12}  {'<|dev|>':>8}  {'max|dev|':>9}  {'Flag':>6}")
    print("-" * 65)

    outlier_flags = {}
    for rep in sorted(sample_stats.keys()):
        s = sample_stats[rep]
        # Average absolute deviation from group mean
        deviations = []
        for temp, n_val in zip(s["temps"], s["n_vals"]):
            if temp in mean_n_per_temp:
                dev = n_val - mean_n_per_temp[temp]["mean"]
                deviations.append(dev)

        avg_dev = np.mean(np.abs(deviations))
        max_dev = np.max(np.abs(deviations))
        mean_dev = np.mean(deviations)  # signed: consistently high or low?

        # Flag criteria: avg deviation > 2σ of group std
        group_avg_std = np.mean([mean_n_per_temp[t]["std"] for t in temps_list if t in mean_n_per_temp])
        is_outlier = avg_dev > 1.5 * group_avg_std
        flag = "⚠" if is_outlier else "OK"

        outlier_flags[rep] = {
            "is_outlier": is_outlier,
            "avg_dev": avg_dev,
            "max_dev": max_dev,
            "mean_dev": mean_dev,
            "stats": s,
        }

        sig = "***" if s["p"] < 0.001 else "**" if s["p"] < 0.01 else "*" if s["p"] < 0.05 else ""
        print(f"  S{rep:>5d}  {s['n_mean']:>8.4f}  {s['R2']:>6.3f}  {s['slope']:>+12.4e}  "
              f"{avg_dev:>8.4f}  {max_dev:>9.4f}  {flag:>6} {sig}")

    # Summary
    flagged = [rep for rep, f in outlier_flags.items() if f["is_outlier"]]
    print(f"\n  Group avg σ(n): {group_avg_std:.4f}")
    if flagged:
        for rep in flagged:
            f = outlier_flags[rep]
            direction = "높음" if f["mean_dev"] > 0 else "낮음"
            print(f"  ⚠ S{rep}: 평균 편차 {f['avg_dev']:.4f} (그룹 평균 대비 일관되게 {direction})")
    else:
        print("  이상 샘플 없음 (모든 샘플 1.5σ 이내)")

    return outlier_flags


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════
def main():
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    CSV_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Load data ──
    print("=" * 60)
    print("Loading data...")
    print("=" * 60)
    refs, samples = load_measurement_set_with_refs(DATA_DIR)
    temps_list = sorted(refs.keys())
    print(f"  Refs: {temps_list}, Samples: {len(samples)}")

    # ── 2. Feature extraction ──
    print("\nExtracting features (5 domains)...")
    all_data = extract_all_temperatures(refs, samples)

    # ── 3. Optical properties — Matched Reference ──
    print("\nOptical properties (Matched Ref)...")
    config = ExtractionConfig(
        thickness_mm=THICKNESS_MM, freq_min_thz=0.2, freq_max_thz=2.5,
        window_type="rectangular", zero_pad_factor=2, n_initial_guess=1.5,
        kappa_initial_guess=0.005, thin_film=True, apply_air_correction=False,
    )
    results_mr = process_temperature_series_matched_ref(
        refs, samples, config,
        progress_callback=lambda i, n: print(f"  {i}/{n}", end="\r"),
    )
    print()

    # ── 3b. S4/S5 offset correction (shift to S1-S3 baseline) ──
    print("\nS4/S5 offset correction (→ S1-S3 baseline)...")
    # Compute global offset per frequency bin: mean(S1-S3) - mean(S4-S5)
    n_all_s123 = []
    n_all_s45 = []
    for key, prop in results_mr.items():
        temp, rep = key
        if rep <= 3:
            n_all_s123.append(prop.n)
        else:
            n_all_s45.append(prop.n)
    mean_n_s123 = np.mean(n_all_s123, axis=0)
    mean_n_s45 = np.mean(n_all_s45, axis=0)
    sample_offset = mean_n_s123 - mean_n_s45  # per-frequency offset

    # Apply offset to S4/S5
    corrected_count = 0
    for key in list(results_mr.keys()):
        temp, rep = key
        if rep >= 4:
            results_mr[key].n[:] = results_mr[key].n + sample_offset
            corrected_count += 1
    print(f"  Global offset @ 0.45 THz: {sample_offset[0]:.4f}")
    print(f"  Corrected {corrected_count} samples (S4, S5)")

    avgs_mr = compute_temperature_averages(results_mr)

    # ── 4. Best frequency selection ──
    print("\nSelecting best frequencies (highest R² for n vs T)...")
    best_freqs = select_best_frequencies(avgs_mr, temps_list)
    best_freq = best_freqs[0]  # primary frequency for EMA/fitting
    f_idx = best_freq["idx"]

    print(f"\n  {'Rank':>4}  {'Freq(THz)':>10}  {'R²':>8}  {'p':>10}")
    print("  " + "-" * 38)
    for i, bf in enumerate(best_freqs):
        sig = "***" if bf["p"] < 0.001 else "**" if bf["p"] < 0.01 else "*" if bf["p"] < 0.05 else ""
        print(f"  {i+1:>4d}  {bf['freq_thz']:>10.3f}  {bf['R2']:>8.4f}  {bf['p']:>10.2e} {sig}")

    # ── 5. EMA porosity inversion (spec-anchored) ──
    print(f"\nEMA porosity inversion (2-phase) @ {best_freq['freq_thz']:.3f} THz "
          f"(anchored to spec: porosity={F_AIR_SPEC*100:.0f}%)...")
    print(f"  Separator: {SEPARATOR_SPEC['product']} ({SEPARATOR_SPEC['process']} process)")

    n_20c = avgs_mr[20].n[f_idx]
    n_offset = compute_n_offset(n_20c, F_AIR_SPEC)
    n_single_expected = bruggeman_3phase(F_AIR_SPEC)
    print(f"  n_measured(20°C) = {n_20c:.4f}")
    print(f"  n_EMA(f=44%)     = {n_single_expected:.4f}")
    print(f"  n_offset (2장)   = {n_offset:+.4f}")

    porosity_data = {}
    for temp in temps_list:
        rep_porosities = []
        for rep in range(1, 6):
            key = (temp, rep)
            if key in results_mr:
                n_rep = results_mr[key].n[f_idx]
                f_air = invert_porosity_anchored(n_rep, n_offset)
                if not np.isnan(f_air):
                    rep_porosities.append(f_air)
        if rep_porosities:
            porosity_data[temp] = {
                "mean": np.mean(rep_porosities),
                "std": np.std(rep_porosities),
                "reps": rep_porosities,
            }

    f_label = f"n@{best_freq['freq_thz']:.2f}THz"
    print(f"\n{'Temp':>6}  {f_label:>12}  {'n_corr':>10}  {'porosity(%)':>10}")
    print("-" * 46)
    for temp in temps_list:
        n_val = avgs_mr[temp].n[f_idx]
        n_corr = n_val - n_offset
        f = porosity_data.get(temp, {}).get("mean", 0) * 100
        print(f"{temp:>6d}  {n_val:>12.4f}  {n_corr:>10.4f}  {f:>10.1f}")

    # ── 6. Two-regime fitting ──
    print("\nTwo-regime fitting...")
    mean_n = [avgs_mr[t].n[f_idx] for t in temps_list]
    two_regime = fit_two_regime(temps_list, mean_n)
    print(f"  T_onset = {two_regime['T_transition']:.1f} °C")
    print(f"  Regime 1 slope: {two_regime['regime1'].slope:.4e}/°C")
    print(f"  Regime 2 slope: {two_regime['regime2'].slope:.4e}/°C")

    # ── 6. Thermal expansion model fitting ──
    print("\nThermal expansion model fitting...")
    p_temps = sorted(porosity_data.keys())
    p_means = np.array([porosity_data[t]["mean"] for t in p_temps])
    thermal_fit = None
    try:
        popt, _ = curve_fit(thermal_expansion_model, p_temps, p_means,
                            p0=[p_means[0], 1e-3], bounds=([0, 0], [1, 1]))
        thermal_fit = popt
        print(f"  porosity_0 = {popt[0]*100:.1f}%, beta = {popt[1]:.4e}/°C")
    except Exception as e:
        print(f"  Fitting failed: {e}")

    # ── 7. Correlation analysis ──
    print("\nCorrelation analysis...")
    corr_results = correlate_features(all_data, temps_list)

    print(f"\n{'#':>3}  {'Feature':>20}  {'Domain':>10}  {'R²':>6}  {'p':>10}")
    for i, r in enumerate(corr_results):
        sig = "***" if r["p"] < 0.001 else "**" if r["p"] < 0.01 else "*" if r["p"] < 0.05 else ""
        print(f"{i+1:3d}  {r['name']:>20}  {r['domain']:>10}  {r['R2']:6.3f}  {r['p']:10.2e} {sig}")

    # ── 8. Export CSV tables ──
    print("\nExporting CSV tables...")

    # Table 2: Optical summary
    rows2 = []
    for temp in temps_list:
        p = avgs_mr[temp]
        d = all_data.get(temp, {})
        row = {"Temperature (C)": temp}
        row["dt_avg (fs)"] = f"{d.get('dt_avg',{}).get('mean',0):.1f} ± {d.get('dt_avg',{}).get('std',0):.1f}"
        for bf in best_freqs:
            ft = bf["freq_thz"]
            bi = bf["idx"]
            n_s = p.n_std[bi] if p.n_std is not None else 0
            row[f"n@{ft:.2f}THz"] = f"{p.n[bi]:.4f} ± {n_s:.4f}"
        bi0 = best_freq["idx"]
        row[f"alpha@{best_freq['freq_thz']:.2f}THz (cm-1)"] = f"{max(p.alpha[bi0], 0.0):.1f}"
        row[f"eps'@{best_freq['freq_thz']:.2f}THz"] = f"{p.n[bi0]**2 - p.kappa[bi0]**2:.4f}"
        row["Porosity (%)"] = f"{porosity_data.get(temp,{}).get('mean',0)*100:.1f}"
        rows2.append(row)
    pd.DataFrame(rows2).to_csv(CSV_DIR / "table02_optical_summary.csv", index=False)

    # Table 3: Per-sample n at best frequency
    rows3 = []
    for temp in temps_list:
        row = {"Temperature (C)": temp}
        vals = []
        for rep in range(1, 6):
            key = (temp, rep)
            if key in results_mr:
                v = results_mr[key].n[f_idx]
                row[f"S{rep}"] = f"{v:.4f}"
                vals.append(v)
            else:
                row[f"S{rep}"] = ""
        row["Mean"] = f"{np.mean(vals):.4f}" if vals else ""
        row["sigma"] = f"{np.std(vals):.4f}" if vals else ""
        rows3.append(row)
    pd.DataFrame(rows3).to_csv(CSV_DIR / "table03_per_sample_n.csv", index=False)

    # Table 4: Correlation analysis
    rows4 = []
    for i, r in enumerate(corr_results):
        sig = "***" if r["p"] < 0.001 else "**" if r["p"] < 0.01 else "*" if r["p"] < 0.05 else ""
        rows4.append({
            "Rank": i + 1, "Feature": r["name"], "Domain": r["domain"],
            "R": f"{r['R']:+.3f}", "R2": f"{r['R2']:.3f}",
            "p-value": f"{r['p']:.2e}", "Slope (/C)": f"{r['slope']:.4e}",
            "Significance": sig,
        })
    pd.DataFrame(rows4).to_csv(CSV_DIR / "table04_correlation_analysis.csv", index=False)

    # EMA porosity results
    rows_ema = []
    ft_label = f"{best_freq['freq_thz']:.2f}THz"
    for temp in temps_list:
        pd_item = porosity_data.get(temp, {})
        n_meas = avgs_mr[temp].n[f_idx]
        rows_ema.append({
            "Temperature (C)": temp,
            f"n@{ft_label}_measured": n_meas,
            f"n@{ft_label}_corrected": n_meas - n_offset,
            "n_offset": n_offset,
            "porosity_mean_pct": pd_item.get("mean", np.nan) * 100,
            "porosity_std_pct": pd_item.get("std", np.nan) * 100,
            "freq_thz": best_freq["freq_thz"],
            "anchored_to": f"{F_AIR_SPEC*100:.0f}% (spec)",
        })
    pd.DataFrame(rows_ema).to_csv(CSV_DIR / "ema_porosity_results.csv", index=False)

    # ── 10. Generate all figures ──
    print(f"\n{'='*60}\nGenerating Figures\n{'='*60}")
    fig01_time_domain_zoom(refs, samples)
    fig02_peak_detail(refs, samples)
    fig03_n_vs_temp_ema(results_mr, avgs_mr, porosity_data, two_regime, thermal_fit, best_freq)
    fig04_optical_spectra(avgs_mr, best_freqs)
    fig05_time_features(all_data, temps_list)
    fig06_porosity(porosity_data, thermal_fit, two_regime)
    fig07_dielectric(avgs_mr, results_mr, best_freq)
    fig08_correlation_summary(corr_results, all_data, temps_list)
    fig09_per_sample_n_3freq(results_mr, avgs_mr, best_freqs, temps_list)
    fig10_per_sample_overview(results_mr, porosity_data, n_offset, best_freq, temps_list)
    fig11_phase_spectrum(refs, samples)
    fig12_snr_dynamic_range(refs, samples)
    fig_feature_illustration(refs, samples)
    drift_results = fig_drift_validation(DATA_DIR)

    # ── 11. ANOVA statistical test (full frequency scan) ──
    anova_results, pairwise_results = anova_temperature_test(
        results_mr, avgs_mr, best_freqs, temps_list)

    # ── 12. Sample group analysis (S1-S3 vs S4-S5) ──
    group_analysis = analyze_sample_groups(results_mr, avgs_mr, best_freq, temps_list)

    # ── 13. EMA 2-phase vs 3-phase comparison ──
    ema_comparison = ema_2phase_vs_3phase(
        avgs_mr, porosity_data, n_offset, best_freq, temps_list)

    # ── 14. FDR correction on pairwise results ──
    if pairwise_results:
        pairwise_results = apply_fdr_correction(pairwise_results)
        pd.DataFrame(pairwise_results).to_csv(
            CSV_DIR / "table06_pairwise_ttest.csv", index=False)

    # ── 15. Bootstrap CI ──
    boot_ci = bootstrap_ci(results_mr, avgs_mr, best_freq, temps_list)

    # ── 16. n_offset uncertainty propagation ──
    uncertainty = propagate_n_offset_uncertainty(
        avgs_mr, porosity_data, n_offset, best_freq, temps_list)

    # ── 17. AIC/BIC model comparison ──
    model_comparison = compare_models_aic(temps_list, mean_n)

    # ── 18. Outlier detection ──
    outlier_flags = detect_outliers(results_mr, temps_list, best_freq)

    # ── Summary ──
    print(f"\n{'='*60}")
    print("PAPER ANALYSIS SUMMARY")
    print(f"{'='*60}")
    print(f"  Separator: {SEPARATOR_SPEC['product']} ({SEPARATOR_SPEC['process']} process)")
    print(f"  Best frequencies:")
    for i, bf in enumerate(best_freqs):
        print(f"    {i+1}. {bf['freq_thz']:.3f} THz (R²={bf['R2']:.4f})")
    print(f"  Primary freq: {best_freq['freq_thz']:.3f} THz")
    print(f"  n_offset (2-sheet): {n_offset:+.4f}")
    print(f"  n@{best_freq['freq_thz']:.2f}THz: {mean_n[0]:.4f} (20°C) → {mean_n[-2]:.4f} (100°C)")
    print(f"  T_onset: {two_regime['T_transition']:.1f} °C")
    print(f"  Porosity(20°C): {porosity_data[20]['mean']*100:.1f}% (anchored to spec)")
    print(f"  Porosity(110°C): {porosity_data[110]['mean']*100:.1f}%")
    if thermal_fit is not None:
        print(f"  Thermal expansion beta: {thermal_fit[1]:.4e}/°C")
    print(f"  DSC crystallinity: {CRYSTALLINITY*100:.1f}%")
    print(f"  DSC Tm: {DSC_PE20['Tm_cycle1']:.1f} °C")
    print(f"\n  Figures: {FIG_DIR}/")
    print(f"  Tables:  {CSV_DIR}/")

    print(f"\n  References:")
    for key, ref in REFERENCES.items():
        print(f"    [{key}] {ref['authors']} ({ref['year']}), {ref['journal']}. "
              f"doi:{ref['doi']}")
    print("\nDone.")


if __name__ == "__main__":
    main()
