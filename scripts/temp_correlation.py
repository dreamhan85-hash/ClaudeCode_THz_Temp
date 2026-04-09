"""THz waveform temperature correlation analysis — comprehensive version.

Extracts exhaustive features from THz time/frequency domain signals,
correlates with temperature, and performs multi-variate analysis.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import hilbert
from scipy.interpolate import CubicSpline
from scipy.stats import pearsonr, linregress, spearmanr
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from thztds.io import load_measurement_set_with_refs
from thztds.signal import compute_fft
from thztds.transfer_function import compute_measured_transfer_function
from thztds.constants import C0, PI

DATA_DIR = Path(__file__).parent.parent / "MeaData" / "260403_Temp"


def interp_signal(t, s, factor=10):
    raw_idx = np.argmax(np.abs(s))
    raw_t = t[raw_idx]
    mask = (t >= raw_t - 5) & (t <= raw_t + 5)
    t_roi, s_roi = t[mask], s[mask]
    t_fine = np.linspace(t_roi[0], t_roi[-1], len(t_roi) * factor)
    cs = CubicSpline(t_roi, s_roi)
    return t_fine, cs(t_fine), cs


def extract_time_features(td):
    t, s = td.time_ps, td.signal
    t_fine, s_fine, cs = interp_signal(t, s)
    dt = t_fine[1] - t_fine[0]
    feat = {}

    # +peak, -peak
    idx_pos = np.argmax(s_fine)
    idx_neg = np.argmin(s_fine)
    feat["t_pos"] = t_fine[idx_pos]
    feat["amp_pos"] = s_fine[idx_pos]
    feat["t_neg"] = t_fine[idx_neg]
    feat["amp_neg"] = s_fine[idx_neg]
    feat["p2p"] = feat["amp_pos"] - feat["amp_neg"]
    feat["t_neg_minus_pos"] = feat["t_neg"] - feat["t_pos"]

    # Envelope
    env = np.abs(hilbert(s))
    t_env_fine, env_fine, cs_env = interp_signal(t, env)
    idx_env = np.argmax(env_fine)
    feat["t_env_peak"] = t_env_fine[idx_env]
    feat["amp_env_peak"] = env_fine[idx_env]

    # Envelope FWHM
    half_max = env_fine[idx_env] / 2
    above = env_fine > half_max
    if np.any(above):
        first = np.argmax(above)
        last = len(above) - 1 - np.argmax(above[::-1])
        feat["env_fwhm_ps"] = t_env_fine[last] - t_env_fine[first]
    else:
        feat["env_fwhm_ps"] = 0

    # Envelope asymmetry (area before peak vs after peak)
    area_before = np.trapz(env_fine[:idx_env], t_env_fine[:idx_env]) if idx_env > 0 else 0
    area_after = np.trapz(env_fine[idx_env:], t_env_fine[idx_env:]) if idx_env < len(env_fine)-1 else 0
    total_env = area_before + area_after
    feat["env_asymmetry"] = (area_after - area_before) / total_env if total_env > 0 else 0

    # Envelope 10%-90% rise/fall times
    env_max = env_fine[idx_env]
    for pct_lo, pct_hi, name in [(0.1, 0.9, "env_rise"), (0.9, 0.1, "env_fall")]:
        if name == "env_rise":
            seg = env_fine[:idx_env]
            t_seg = t_env_fine[:idx_env]
        else:
            seg = env_fine[idx_env:]
            t_seg = t_env_fine[idx_env:]
        if len(seg) > 2:
            th_lo = min(pct_lo, pct_hi) * env_max
            th_hi = max(pct_lo, pct_hi) * env_max
            above_lo = np.where(seg > th_lo)[0]
            above_hi = np.where(seg > th_hi)[0]
            if len(above_lo) > 0 and len(above_hi) > 0:
                feat[name + "_time_ps"] = abs(t_seg[above_hi[0] if name == "env_rise" else above_hi[-1]] -
                                              t_seg[above_lo[0] if name == "env_rise" else above_lo[-1]])
            else:
                feat[name + "_time_ps"] = 0
        else:
            feat[name + "_time_ps"] = 0

    # Pulse area, energy, RMS
    pulse_mask = (t >= t[np.argmax(np.abs(s))] - 2) & (t <= t[np.argmax(np.abs(s))] + 2)
    s_pulse = s[pulse_mask]
    t_pulse = t[pulse_mask]
    feat["pulse_area"] = np.trapz(np.abs(s_pulse), t_pulse)
    feat["pulse_energy"] = np.trapz(s_pulse**2, t_pulse)
    feat["pulse_rms"] = np.sqrt(np.mean(s_pulse**2))
    feat["pulse_kurtosis"] = float(np.mean(((s_pulse - np.mean(s_pulse)) / (np.std(s_pulse)+1e-30))**4))
    feat["pulse_skewness"] = float(np.mean(((s_pulse - np.mean(s_pulse)) / (np.std(s_pulse)+1e-30))**3))

    # Zero-crossing
    t1 = min(feat["t_pos"], feat["t_neg"])
    t2 = max(feat["t_pos"], feat["t_neg"])
    zc_mask = (t_fine >= t1) & (t_fine <= t2)
    s_zc, t_zc = s_fine[zc_mask], t_fine[zc_mask]
    if len(s_zc) > 1:
        sc = np.where(np.diff(np.sign(s_zc)))[0]
        if len(sc) > 0:
            idx_zc = sc[0]
            if s_zc[idx_zc] != s_zc[idx_zc+1]:
                frac = -s_zc[idx_zc] / (s_zc[idx_zc+1] - s_zc[idx_zc])
                feat["t_zero_cross"] = t_zc[idx_zc] + frac * dt
            else:
                feat["t_zero_cross"] = t_zc[idx_zc]
        else:
            feat["t_zero_cross"] = (t1 + t2) / 2
    else:
        feat["t_zero_cross"] = (t1 + t2) / 2

    # Rise time (10-90% of +peak)
    peak_val = feat["amp_pos"]
    s_before = s_fine[:idx_pos]
    t10_arr = np.where(s_before > 0.1 * peak_val)[0]
    t90_arr = np.where(s_before > 0.9 * peak_val)[0]
    feat["rise_time_ps"] = (t_fine[t90_arr[0]] - t_fine[t10_arr[0]]) if len(t10_arr) > 0 and len(t90_arr) > 0 else 0

    # Max slope of raw signal (steepest point)
    ds = cs(t_fine, 1)
    feat["max_slope"] = float(np.max(ds))
    feat["min_slope"] = float(np.min(ds))
    feat["t_max_slope"] = float(t_fine[np.argmax(ds)])
    feat["t_min_slope"] = float(t_fine[np.argmin(ds)])

    # Second derivative peak (curvature)
    d2s = cs(t_fine, 2)
    feat["max_curvature"] = float(np.max(np.abs(d2s)))

    # Noise floor (RMS of signal far from pulse)
    noise_mask = (t < t[np.argmax(np.abs(s))] - 20)
    if np.sum(noise_mask) > 10:
        feat["noise_rms"] = float(np.sqrt(np.mean(s[noise_mask]**2)))
    else:
        feat["noise_rms"] = 0

    # SNR
    feat["snr"] = feat["p2p"] / (2 * feat["noise_rms"]) if feat["noise_rms"] > 0 else 0

    return feat


def extract_freq_features(ref_td, sam_td):
    ref_freq = compute_fft(ref_td, 2)
    sam_freq = compute_fft(sam_td, 2)
    H = compute_measured_transfer_function(ref_freq, sam_freq)
    freq = ref_freq.freq_hz
    freq_thz = freq / 1e12
    valid = ~np.isnan(H)
    feat = {}

    # H at specific frequencies
    for f_t in [0.3, 0.5, 0.7, 1.0, 1.3, 1.5, 2.0]:
        mask = valid & (freq_thz >= f_t - 0.03) & (freq_thz <= f_t + 0.03)
        if np.any(mask):
            feat[f"H_amp_{f_t}"] = float(np.mean(np.abs(H[mask])))
            feat[f"H_phase_{f_t}"] = float(np.mean(np.unwrap(np.angle(H[mask]))))

    # Broadband
    mask_b = valid & (freq_thz >= 0.3) & (freq_thz <= 2.0)
    if np.any(mask_b):
        amp_r = np.abs(H[mask_b])
        feat["H_amp_mean"] = float(np.mean(amp_r))
        feat["H_amp_min"] = float(np.min(amp_r))
        feat["H_amp_max"] = float(np.max(amp_r))
        feat["H_amp_std"] = float(np.std(amp_r))

        phase = np.unwrap(np.angle(H[mask_b]))
        f_v = freq[mask_b]
        if len(f_v) > 2:
            sl = linregress(f_v, phase)
            feat["phase_slope"] = float(sl.slope)
            feat["group_delay_ps"] = float(-sl.slope / (2 * PI) * 1e12)
            feat["phase_intercept"] = float(sl.intercept)
            # Phase residual (deviation from linear)
            phase_fit = sl.slope * f_v + sl.intercept
            feat["phase_residual_rms"] = float(np.sqrt(np.mean((phase - phase_fit)**2)))

        # Transmission in sub-bands
        for f_lo, f_hi, name in [(0.3, 0.7, "low"), (0.7, 1.3, "mid"), (1.3, 2.0, "high")]:
            sub = valid & (freq_thz >= f_lo) & (freq_thz <= f_hi)
            if np.any(sub):
                feat[f"H_amp_{name}band"] = float(np.mean(np.abs(H[sub])))

        # Absorption integral
        trans = np.abs(H[mask_b])
        absorption = -np.log(np.clip(trans, 1e-10, None))
        feat["absorption_integral"] = float(np.trapz(absorption, freq_thz[mask_b]))

        # Spectral slope of |H|
        sl_amp = linregress(freq_thz[mask_b], np.abs(H[mask_b]))
        feat["H_amp_slope"] = float(sl_amp.slope)

    # Spectral centroids
    for label, data_freq in [("sam", sam_freq), ("ref", ref_freq)]:
        amp = data_freq.amplitude
        mask_s = (freq_thz >= 0.3) & (freq_thz <= 2.0) & (amp > 0)
        if np.any(mask_s):
            feat[f"centroid_{label}_thz"] = float(np.sum(freq_thz[mask_s] * amp[mask_s]) / np.sum(amp[mask_s]))
            # Spectral bandwidth (weighted std)
            c = feat[f"centroid_{label}_thz"]
            feat[f"bandwidth_{label}_thz"] = float(np.sqrt(np.sum(amp[mask_s] * (freq_thz[mask_s] - c)**2) / np.sum(amp[mask_s])))

    # Spectral ratio at different bands
    if "centroid_sam_thz" in feat and "centroid_ref_thz" in feat:
        feat["centroid_shift_thz"] = feat["centroid_sam_thz"] - feat["centroid_ref_thz"]

    return feat


def extract_delta_features(ref_td, sam_td):
    t = ref_td.time_ps
    delta = sam_td.signal - ref_td.signal
    raw_idx = np.argmax(np.abs(ref_td.signal))
    raw_t = t[raw_idx]
    mask = (t >= raw_t - 3) & (t <= raw_t + 3)
    d_roi, t_roi = delta[mask], t[mask]
    feat = {}

    feat["delta_max"] = float(np.max(d_roi))
    feat["delta_min"] = float(np.min(d_roi))
    feat["delta_p2p"] = feat["delta_max"] - feat["delta_min"]
    feat["delta_rms"] = float(np.sqrt(np.mean(d_roi**2)))
    feat["delta_area"] = float(np.trapz(np.abs(d_roi), t_roi))
    feat["delta_energy"] = float(np.trapz(d_roi**2, t_roi))
    feat["t_delta_max"] = float(t_roi[np.argmax(d_roi)])
    feat["t_delta_min"] = float(t_roi[np.argmin(d_roi)])

    # Ratio of positive to negative delta area
    pos_area = np.trapz(np.clip(d_roi, 0, None), t_roi)
    neg_area = np.trapz(np.clip(-d_roi, 0, None), t_roi)
    feat["delta_pos_neg_ratio"] = pos_area / neg_area if neg_area > 0 else 0

    # Delta centroid (time center of mass of |delta|)
    abs_d = np.abs(d_roi)
    if np.sum(abs_d) > 0:
        feat["delta_centroid_ps"] = float(np.sum(t_roi * abs_d) / np.sum(abs_d))

    return feat


def correlate(temps, values, label):
    t_arr = np.array(temps, dtype=float)
    v_arr = np.array(values, dtype=float)
    ok = ~np.isnan(v_arr) & ~np.isinf(v_arr)
    if np.sum(ok) < 5:
        return None
    ta, va = t_arr[ok], v_arr[ok]
    r_p, p_p = pearsonr(ta, va)
    r_s, p_s = spearmanr(ta, va)
    sl = linregress(ta, va)
    print(f"FEATURE: {label}")
    print(f"  Pearson  R={r_p:+.4f} R²={r_p**2:.4f} p={p_p:.2e}")
    print(f"  Spearman R={r_s:+.4f} p={p_s:.2e}")
    print(f"  slope={sl.slope:+.4e}/°C  intercept={sl.intercept:.6f}")
    print(f"  values: {' '.join(f'{v:.6f}' for v in va)}")
    print()
    return {"name": label, "r_p": r_p, "r2": r_p**2, "p_p": p_p,
            "r_s": r_s, "p_s": p_s, "slope": sl.slope}


def main():
    refs, samples = load_measurement_set_with_refs(DATA_DIR, exclude_temps=[20])
    temps_list = sorted(refs.keys())
    print(f"Temperatures: {temps_list}")
    print()

    # Extract all features
    all_features = {}
    for temp in temps_list:
        ref = refs[temp]
        ref_feat = extract_time_features(ref)

        sam_feats = {"time": [], "freq": [], "delta": []}
        for rep in range(1, 6):
            key = (temp, rep)
            if key not in samples:
                continue
            sam = samples[key]
            sam_feats["time"].append(extract_time_features(sam))
            sam_feats["freq"].append(extract_freq_features(ref, sam))
            sam_feats["delta"].append(extract_delta_features(ref, sam))

        avg = {}
        for cat in sam_feats.values():
            if not cat:
                continue
            for k in cat[0]:
                vals = [f[k] for f in cat if k in f]
                avg[k] = np.mean(vals)
                avg[k + "_std"] = np.std(vals)
                avg[k + "_cv"] = np.std(vals) / abs(np.mean(vals)) if abs(np.mean(vals)) > 1e-15 else 0

        for k, v in ref_feat.items():
            avg["ref_" + k] = v

        # Derived
        avg["dt_pos"] = avg.get("t_pos", 0) - ref_feat.get("t_pos", 0)
        avg["dt_neg"] = avg.get("t_neg", 0) - ref_feat.get("t_neg", 0)
        avg["dt_zero_cross"] = avg.get("t_zero_cross", 0) - ref_feat.get("t_zero_cross", 0)
        avg["dt_env"] = avg.get("t_env_peak", 0) - ref_feat.get("t_env_peak", 0)
        avg["dt_max_slope"] = avg.get("t_max_slope", 0) - ref_feat.get("t_max_slope", 0)
        avg["dt_min_slope"] = avg.get("t_min_slope", 0) - ref_feat.get("t_min_slope", 0)
        avg["amp_ratio_pos"] = avg.get("amp_pos", 1) / ref_feat.get("amp_pos", 1)
        avg["amp_ratio_neg"] = avg.get("amp_neg", -1) / ref_feat.get("amp_neg", -1)
        avg["p2p_ratio"] = avg.get("p2p", 1) / ref_feat.get("p2p", 1)
        avg["energy_ratio"] = avg.get("pulse_energy", 1) / ref_feat.get("pulse_energy", 1)
        avg["area_ratio"] = avg.get("pulse_area", 1) / ref_feat.get("pulse_area", 1)
        avg["slope_ratio_max"] = avg.get("max_slope", 1) / ref_feat.get("max_slope", 1)
        avg["slope_ratio_min"] = avg.get("min_slope", -1) / ref_feat.get("min_slope", -1)
        avg["fwhm_ratio"] = avg.get("env_fwhm_ps", 1) / ref_feat.get("env_fwhm_ps", 1)
        avg["snr_ratio"] = avg.get("snr", 1) / ref_feat.get("snr", 1) if ref_feat.get("snr", 0) > 0 else 0

        all_features[temp] = avg

    # ===== Correlate =====
    print("=" * 70)
    print("ALL CORRELATIONS")
    print("=" * 70)
    print()

    feature_keys = sorted(set(k for v in all_features.values() for k in v.keys()))
    skip = ("_std", "_cv")
    results = []
    for fk in feature_keys:
        if any(fk.endswith(s) for s in skip):
            continue
        ts, vs = [], []
        for temp in temps_list:
            if fk in all_features[temp]:
                ts.append(temp)
                vs.append(all_features[temp][fk])
        if len(ts) >= 5:
            res = correlate(ts, vs, fk)
            if res:
                results.append(res)

    # ===== Rankings =====
    results.sort(key=lambda x: abs(x["r_p"]), reverse=True)

    print("=" * 70)
    print("RANKING BY |Pearson R| (top 40)")
    print("=" * 70)
    print(f"\n{'#':>3}  {'Feature':>35}  {'R':>7}  {'R²':>7}  {'Spearman':>9}  {'p':>10}  {'slope/°C':>12}")
    for i, r in enumerate(results[:40]):
        sig = "***" if r["p_p"] < 0.001 else "**" if r["p_p"] < 0.01 else "*" if r["p_p"] < 0.05 else ""
        print(f"{i+1:3d}  {r['name']:>35}  {r['r_p']:+7.4f}  {r['r2']:7.4f}  {r['r_s']:+9.4f}  {r['p_p']:10.2e}  {r['slope']:+12.4e} {sig}")

    # ===== Δt features detail =====
    print()
    print("=" * 70)
    print("DELTA-T FEATURES DETAIL (Sam-Ref time differences)")
    print("=" * 70)
    dt_keys = [k for k in feature_keys if k.startswith("dt_")]
    for fk in dt_keys:
        ts, vs = [], []
        for temp in temps_list:
            if fk in all_features[temp]:
                ts.append(temp)
                vs.append(all_features[temp][fk] * 1000)  # ps → fs
        if len(ts) >= 5:
            t_arr = np.array(ts, dtype=float)
            v_arr = np.array(vs)
            r, p = pearsonr(t_arr, v_arr)
            sl = linregress(t_arr, v_arr)
            print(f"\n  {fk}: R={r:+.4f} R²={r**2:.4f} slope={sl.slope:+.4f} fs/°C")
            for i, temp in enumerate(ts):
                print(f"    {temp}°C: {v_arr[i]:+.4f} fs")

    # ===== Ratio features detail =====
    print()
    print("=" * 70)
    print("RATIO FEATURES DETAIL (Sam/Ref)")
    print("=" * 70)
    ratio_keys = [k for k in feature_keys if "ratio" in k and not k.endswith("_std") and not k.endswith("_cv")]
    for fk in sorted(ratio_keys):
        ts, vs = [], []
        for temp in temps_list:
            if fk in all_features[temp]:
                ts.append(temp)
                vs.append(all_features[temp][fk])
        if len(ts) >= 5:
            t_arr = np.array(ts, dtype=float)
            v_arr = np.array(vs)
            r, p = pearsonr(t_arr, v_arr)
            sl = linregress(t_arr, v_arr)
            print(f"\n  {fk}: R={r:+.4f} R²={r**2:.4f} slope={sl.slope:+.4e}/°C")
            for i, temp in enumerate(ts):
                print(f"    {temp}°C: {v_arr[i]:.6f}")

    # ===== Spectral features detail =====
    print()
    print("=" * 70)
    print("SPECTRAL FEATURES DETAIL")
    print("=" * 70)
    spec_keys = [k for k in feature_keys if k.startswith("H_") or "centroid" in k or "bandwidth" in k
                 or "absorption" in k or "phase_" in k or "group_" in k]
    spec_keys = [k for k in spec_keys if not k.endswith("_std") and not k.endswith("_cv")]
    for fk in sorted(spec_keys):
        ts, vs = [], []
        for temp in temps_list:
            if fk in all_features[temp]:
                ts.append(temp)
                vs.append(all_features[temp][fk])
        if len(ts) >= 5:
            t_arr = np.array(ts, dtype=float)
            v_arr = np.array(vs)
            r, p = pearsonr(t_arr, v_arr)
            print(f"  {fk:>30}: R={r:+.4f} R²={r**2:.4f} p={p:.2e}  range=[{np.min(v_arr):.6f}, {np.max(v_arr):.6f}]")

    # ===== Reproducibility (CV) =====
    print()
    print("=" * 70)
    print("REPRODUCIBILITY: Coefficient of Variation (%) by temperature")
    print("=" * 70)
    cv_keys = ["dt_pos_cv", "dt_neg_cv", "amp_ratio_pos_cv", "amp_ratio_neg_cv",
               "p2p_ratio_cv", "group_delay_ps_cv", "H_amp_1.0_cv", "delta_rms_cv"]
    for fk in cv_keys:
        if not any(fk in all_features[t] for t in temps_list):
            continue
        print(f"\n  {fk}:")
        for temp in temps_list:
            if fk in all_features[temp]:
                print(f"    {temp}°C: {all_features[temp][fk]*100:.2f}%")

    # ===== Summary =====
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    n_total = len(results)
    n_sig = len([r for r in results if r["p_p"] < 0.05])
    n_strong = len([r for r in results if abs(r["r_p"]) > 0.8])
    best = results[0] if results else None
    print(f"  Total features analyzed: {n_total}")
    print(f"  Significant (p<0.05): {n_sig}")
    print(f"  Strong (|R|>0.8): {n_strong}")
    if best:
        print(f"  Best: {best['name']} R²={best['r2']:.4f}")
    print()

    # Categorize findings
    print("  STRONG CORRELATIONS (|R|>0.8, p<0.01):")
    for r in results:
        if abs(r["r_p"]) > 0.8 and r["p_p"] < 0.01:
            direction = "↑" if r["r_p"] > 0 else "↓"
            print(f"    {direction} {r['name']:>35}: R={r['r_p']:+.4f}")

    print()
    print("  SAMPLE-SPECIFIC (Δt, ratio, H) with p<0.05:")
    sample_specific = [r for r in results if r["p_p"] < 0.05 and
                       any(x in r["name"] for x in ["dt_", "ratio", "H_", "delta_", "absorption", "centroid_shift", "group_delay"])]
    if sample_specific:
        for r in sample_specific:
            direction = "↑" if r["r_p"] > 0 else "↓"
            print(f"    {direction} {r['name']:>35}: R={r['r_p']:+.4f} R²={r['r2']:.4f}")
    else:
        print("    None found with p<0.05")


if __name__ == "__main__":
    main()
