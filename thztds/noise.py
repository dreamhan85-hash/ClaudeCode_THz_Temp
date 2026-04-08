"""Noise floor detection and dynamic range analysis for THz-TDS.

Based on TeraLyzer's noise floor detection (Jepsen & Fischer 2005):
- Detects frequency where signal drops to noise floor
- Computes dynamic range DR(f) and valid frequency mask
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .types import THzFrequencyDomainData, NoiseAnalysis
from .constants import PI


def estimate_noise_floor(
    ref_freq: THzFrequencyDomainData,
    tail_fraction: float = 0.1,
) -> float:
    """Estimate noise floor from high-frequency tail of reference spectrum.

    Uses the last `tail_fraction` of the spectrum where signal is expected
    to be dominated by noise.

    Args:
        ref_freq: Reference frequency-domain data.
        tail_fraction: Fraction of spectrum to use for noise estimate (0-1).

    Returns:
        Noise floor amplitude (linear scale).
    """
    amp = ref_freq.amplitude
    n_tail = max(1, int(len(amp) * tail_fraction))
    return float(np.mean(amp[-n_tail:]))


def compute_dynamic_range(
    ref_freq: THzFrequencyDomainData,
    noise_floor: float,
) -> NDArray[np.float64]:
    """Compute frequency-dependent dynamic range in dB.

    DR(f) = 20 * log10(|E_ref(f)| / noise_floor)

    Args:
        ref_freq: Reference frequency-domain data.
        noise_floor: Noise floor amplitude.

    Returns:
        Dynamic range array in dB, same length as ref_freq.freq_hz.
    """
    amp = ref_freq.amplitude
    # Avoid log(0) by clipping
    safe_amp = np.maximum(amp, noise_floor * 1e-10)
    safe_noise = max(noise_floor, 1e-30)
    return 20.0 * np.log10(safe_amp / safe_noise)


def detect_noise_floor(
    ref_freq: THzFrequencyDomainData,
    dr_threshold_db: float = 10.0,
    tail_fraction: float = 0.1,
) -> NoiseAnalysis:
    """Detect noise floor and determine valid frequency range.

    Algorithm:
    1. Estimate noise floor from high-frequency tail of reference spectrum
    2. Compute DR(f) = 20*log10(|E_ref(f)| / noise_floor)
    3. Valid frequencies are where DR(f) > threshold

    Args:
        ref_freq: Reference frequency-domain data.
        dr_threshold_db: Dynamic range threshold in dB (default: 10 dB).
        tail_fraction: Fraction of spectrum for noise estimation.

    Returns:
        NoiseAnalysis with noise floor, dynamic range, and valid mask.
    """
    noise_floor = estimate_noise_floor(ref_freq, tail_fraction)
    dr_db = compute_dynamic_range(ref_freq, noise_floor)

    # Valid frequency mask: DR above threshold
    valid_mask = dr_db > dr_threshold_db

    # Find noise start frequency (first frequency where DR drops below threshold)
    freq_thz = ref_freq.freq_hz / 1e12

    # Search from high frequency downward for the last valid point
    valid_indices = np.where(valid_mask)[0]
    if len(valid_indices) > 0:
        noise_start_thz = float(freq_thz[valid_indices[-1]])
    else:
        noise_start_thz = 0.0

    # Compute SNR spectrum
    safe_noise = max(noise_floor, 1e-30)
    snr = ref_freq.amplitude**2 / safe_noise**2

    return NoiseAnalysis(
        noise_floor=noise_floor,
        noise_start_thz=noise_start_thz,
        dynamic_range_db=dr_db,
        snr_spectrum=snr,
        valid_freq_mask=valid_mask,
    )
