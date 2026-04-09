"""Generate publication-quality figures for annual report.

Output: 4cm x 4cm (1:1), 600 DPI, readable at small print size.
Generates both Method 2 (absolute) and Method 3 (differential) results.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.ticker as ticker
from scipy.ndimage import median_filter
from scipy.signal import savgol_filter

sys.path.insert(0, str(Path(__file__).parent))

from thztds.io import load_measurement_set
from thztds.signal import find_pulse_peak
from thztds.types import ExtractionConfig
from thztds.optical_properties import (
    process_temperature_series,
    compute_temperature_averages,
)

# ── Figure style ──────────────────────────────────────────────────
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

# ── Temperature color map ─────────────────────────────────────────
TEMPS = list(range(20, 115, 10))

_TEMP_COLORS = [
    "#3B4CC0", "#5A7BC6", "#7AAAD0", "#9DC8D9", "#BDDDDD",
    "#E8C8A0", "#F0A672", "#E87B52", "#D44E3D", "#B40426",
]

def get_temp_color(temp_c: int) -> str:
    return _TEMP_COLORS[TEMPS.index(temp_c)]

_TEMP_CMAP = LinearSegmentedColormap.from_list("temp", _TEMP_COLORS, N=256)


def make_temp_colorbar(ax, fig, label=r"T ($\degree$C)"):
    sm = plt.cm.ScalarMappable(cmap=_TEMP_CMAP, norm=plt.Normalize(20, 110))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.03, aspect=20, shrink=0.9)
    cbar.set_label(label, fontsize=6, labelpad=2)
    cbar.ax.tick_params(labelsize=5, width=0.3, length=1.5)
    cbar.set_ticks([20, 40, 60, 80, 100])
    return cbar


def save_fig(fig, name):
    fig.savefig(OUT_DIR / f"{name}.png")
    fig.savefig(OUT_DIR / f"{name}.pdf")
    plt.close(fig)
    print(f"  -> {name} saved")


def smooth_spectrum(y, kernel=5):
    """Light median filter to suppress isolated spikes."""
    return median_filter(y, size=kernel)


def smooth_alpha(y, kernel=11, sg_window=31, sg_order=2):
    """Two-stage smoothing for noisy absorption spectra.

    1) Median filter to remove sharp spikes.
    2) Savitzky-Golay to smooth remaining oscillations.
    Aggressive settings needed for 20-um thin-film extraction.
    """
    cleaned = median_filter(y, size=kernel)
    if len(cleaned) >= sg_window:
        cleaned = savgol_filter(cleaned, sg_window, sg_order)
    return cleaned


OUT_DIR = Path(__file__).parent / "figures"
DATA_DIR = Path(__file__).parent / "MeaData"

# ── Load & process ────────────────────────────────────────────────
print("Loading measurement data...")
ref_data, samples = load_measurement_set(DATA_DIR)
if ref_data is None:
    raise RuntimeError("Reference file not found!")

config = ExtractionConfig(
    thickness_mm=0.02,
    freq_min_thz=0.2,
    freq_max_thz=2.5,
    n_fp_echoes=0,
    window_type="hann",
    zero_pad_factor=2,
    n_initial_guess=1.3,
    kappa_initial_guess=0.005,
    thin_film=True,
    ref_temperature_c=20.0,
    chamber_length_cm=1.0,
    apply_air_correction=True,
)

print("Processing Method 2 (absolute: sample / air ref)...")
results_m2 = process_temperature_series(
    ref_data, samples, config,
    progress_callback=lambda i, n: print(f"  {i}/{n}", end="\r"),
    analysis_method="method2",
)
print()
avgs_m2 = compute_temperature_averages(results_m2)

print("Processing Method 3 (differential: sample(T) / sample(20C))...")
results_m3 = process_temperature_series(
    ref_data, samples, config,
    progress_callback=lambda i, n: print(f"  {i}/{n}", end="\r"),
    analysis_method="method3",
)
print()
avgs_m3 = compute_temperature_averages(results_m3)

OUT_DIR.mkdir(exist_ok=True)

_, ref_peak_time = find_pulse_peak(ref_data)


# ══════════════════════════════════════════════════════════════════
# Fig 1: Time-domain waveforms — ALL temperatures + inset
# ══════════════════════════════════════════════════════════════════
print("Fig 1: Time-domain with inset...")
fig1, ax1 = plt.subplots(figsize=(FIG_W, FIG_H))
t_shift = ref_peak_time

# Reference (black, thicker)
ax1.plot(ref_data.time_ps - t_shift, ref_data.signal,
         color="black", lw=0.9, zorder=10)

# All 10 temperatures (rep 1)
for temp in TEMPS:
    key = (temp, 1)
    if key in samples:
        td = samples[key]
        ax1.plot(td.time_ps - t_shift, td.signal,
                 color=get_temp_color(temp), lw=0.5)

ax1.set_xlim(-4, 6)
ax1.set_xlabel("Time (ps)")
ax1.set_ylabel("Amplitude (a.u.)")

# Colorbar + small legend for Ref only
cbar1 = make_temp_colorbar(ax1, fig1)
from matplotlib.lines import Line2D
ref_handle = Line2D([0], [0], color="black", lw=1.0)
ax1.legend([ref_handle], ["Ref (air)"], loc="upper right",
           framealpha=0.95, borderpad=0.2, handlelength=1.0)

# Inset: zoom on negative peak region
axins = ax1.inset_axes([0.06, 0.06, 0.42, 0.38])
axins.plot(ref_data.time_ps - t_shift, ref_data.signal,
           color="black", lw=0.7, zorder=10)
for temp in TEMPS:
    key = (temp, 1)
    if key in samples:
        td = samples[key]
        axins.plot(td.time_ps - t_shift, td.signal,
                   color=get_temp_color(temp), lw=0.45)

axins.set_xlim(-0.3, 0.15)
ref_mask = (ref_data.time_ps - t_shift >= -0.3) & (ref_data.time_ps - t_shift <= 0.15)
if np.any(ref_mask):
    y_min = ref_data.signal[ref_mask].min()
    y_max = ref_data.signal[ref_mask].max()
    axins.set_ylim(y_min - 0.15, y_max + 0.15)

axins.tick_params(labelsize=4, width=0.3, length=1.2)
for spine in axins.spines.values():
    spine.set_linewidth(0.4)

ax1.indicate_inset_zoom(axins, edgecolor="0.5", linewidth=0.4)

save_fig(fig1, "fig1_time_domain")


# ══════════════════════════════════════════════════════════════════
# Method 2 (absolute) figures
# ══════════════════════════════════════════════════════════════════

# --- Fig 2 M2: n(f) ---
print("Fig 2 M2: n(f) absolute...")
fig2, ax2 = plt.subplots(figsize=(FIG_W, FIG_H))

for temp in TEMPS:
    if temp not in avgs_m2:
        continue
    p = avgs_m2[temp]
    ax2.plot(p.freq_thz, smooth_spectrum(p.n, 3),
             color=get_temp_color(temp), lw=0.55)

make_temp_colorbar(ax2, fig2)
ax2.set_xlim(0.3, 2.2)
ax2.set_xlabel("Frequency (THz)")
ax2.set_ylabel("Refractive index, $n$")
ax2.xaxis.set_major_locator(ticker.MultipleLocator(0.5))

save_fig(fig2, "fig2_m2_refractive_index")


# --- Fig 3 M2: alpha(f) ---
print("Fig 3 M2: alpha(f) absolute...")
fig3, ax3 = plt.subplots(figsize=(FIG_W, FIG_H))

for temp in TEMPS:
    if temp not in avgs_m2:
        continue
    p = avgs_m2[temp]
    f_mask = (p.freq_thz >= 0.3) & (p.freq_thz <= 2.0)
    ax3.plot(p.freq_thz[f_mask], smooth_alpha(p.alpha[f_mask]),
             color=get_temp_color(temp), lw=0.55)

make_temp_colorbar(ax3, fig3)
ax3.set_xlim(0.3, 2.0)
ax3.set_xlabel("Frequency (THz)")
ax3.set_ylabel(r"$\alpha$ (cm$^{-1}$)")
ax3.xaxis.set_major_locator(ticker.MultipleLocator(0.5))

save_fig(fig3, "fig3_m2_absorption")


# --- Fig 4 M2: n vs Temperature ---
print("Fig 4 M2: n vs Temperature...")
fig4, ax4 = plt.subplots(figsize=(FIG_W, FIG_H))

target_freqs = [0.5, 1.0, 1.5]
markers = ["o", "s", "^"]
colors4 = ["#2166AC", "#4DAC26", "#D6604D"]

for f_target, mk, c4 in zip(target_freqs, markers, colors4):
    temps_plot, n_vals, n_errs = [], [], []
    for temp in sorted(avgs_m2.keys()):
        p = avgs_m2[temp]
        idx = np.argmin(np.abs(p.freq_thz - f_target))
        temps_plot.append(temp)
        n_vals.append(p.n[idx])
        n_errs.append(p.n_std[idx] if p.n_std is not None else 0)

    ax4.errorbar(temps_plot, n_vals, yerr=n_errs,
                 fmt=mk, color=c4, markersize=2.8, lw=0.6,
                 elinewidth=0.4, capsize=1.2, capthick=0.3,
                 label=f"{f_target:.1f} THz")

ax4.set_xlabel(r"Temperature ($\degree$C)")
ax4.set_ylabel("Refractive index, $n$")
ax4.legend(loc="upper right")

save_fig(fig4, "fig4_m2_n_vs_temp")


# ══════════════════════════════════════════════════════════════════
# Method 3 (differential) figures
# ══════════════════════════════════════════════════════════════════

# --- Fig 2 M3: Delta-n(f) ---
print("Fig 2 M3: Delta-n(f) differential...")
fig5, ax5 = plt.subplots(figsize=(FIG_W, FIG_H))

for temp in TEMPS:
    if temp not in avgs_m3:
        continue
    p = avgs_m3[temp]
    delta_n = p.n - 1.0
    ax5.plot(p.freq_thz, smooth_spectrum(delta_n, 3),
             color=get_temp_color(temp), lw=0.55)

make_temp_colorbar(ax5, fig5)
ax5.set_xlim(0.3, 2.2)
ax5.axhline(0, color="0.5", lw=0.3, ls="--", zorder=0)
ax5.set_xlabel("Frequency (THz)")
ax5.set_ylabel(r"$\Delta n$ (rel. to 20$\degree$C)")
ax5.xaxis.set_major_locator(ticker.MultipleLocator(0.5))

save_fig(fig5, "fig2_m3_delta_n")


# --- Fig 3 M3: Delta-alpha(f) ---
print("Fig 3 M3: Delta-alpha(f) differential...")
fig6, ax6 = plt.subplots(figsize=(FIG_W, FIG_H))

for temp in TEMPS:
    if temp not in avgs_m3:
        continue
    p = avgs_m3[temp]
    f_mask = (p.freq_thz >= 0.3) & (p.freq_thz <= 2.0)
    ax6.plot(p.freq_thz[f_mask], smooth_alpha(p.alpha[f_mask]),
             color=get_temp_color(temp), lw=0.55)

make_temp_colorbar(ax6, fig6)
ax6.set_xlim(0.3, 2.0)
ax6.axhline(0, color="0.5", lw=0.3, ls="--", zorder=0)
ax6.set_xlabel("Frequency (THz)")
ax6.set_ylabel(r"$\Delta\alpha$ (cm$^{-1}$)")
ax6.xaxis.set_major_locator(ticker.MultipleLocator(0.5))

save_fig(fig6, "fig3_m3_delta_alpha")


# --- Fig 4 M3: Delta-n vs Temperature ---
print("Fig 4 M3: Delta-n vs Temperature...")
fig7, ax7 = plt.subplots(figsize=(FIG_W, FIG_H))

for f_target, mk, c4 in zip(target_freqs, markers, colors4):
    temps_plot, dn_vals, dn_errs = [], [], []
    for temp in sorted(avgs_m3.keys()):
        p = avgs_m3[temp]
        idx = np.argmin(np.abs(p.freq_thz - f_target))
        temps_plot.append(temp)
        dn_vals.append(p.n[idx] - 1.0)
        dn_errs.append(p.n_std[idx] if p.n_std is not None else 0)

    ax7.errorbar(temps_plot, dn_vals, yerr=dn_errs,
                 fmt=mk, color=c4, markersize=2.8, lw=0.6,
                 elinewidth=0.4, capsize=1.2, capthick=0.3,
                 label=f"{f_target:.1f} THz")

ax7.axhline(0, color="0.5", lw=0.3, ls="--", zorder=0)
ax7.set_xlabel(r"Temperature ($\degree$C)")
ax7.set_ylabel(r"$\Delta n$ (rel. to 20$\degree$C)")
ax7.legend(loc="lower left")

save_fig(fig7, "fig4_m3_delta_n_vs_temp")


print(f"\nAll figures saved to: {OUT_DIR}/")
