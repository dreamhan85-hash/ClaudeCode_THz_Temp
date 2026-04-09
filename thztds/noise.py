"""Noise floor detection and SNR analysis for THz-TDS spectra."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .types import THzFrequencyDomainData, ExtractionConfig, NoiseAnalysis


def detect_noise_floor(
    freq_data: THzFrequencyDomainData,
    config: ExtractionConfig,
) -> NoiseAnalysis:
    """Detect noise floor from frequency-domain spectrum.

    Estimates the noise floor as the median amplitude in the high-frequency
    tail (above freq_max_thz), where signal content is negligible.

    Args:
        freq_data: Frequency-domain THz data.
        config: Extraction config (uses freq_min_thz, freq_max_thz).

    Returns:
        NoiseAnalysis with noise floor, dynamic range, SNR, and valid mask.
    """
    amplitude = np.abs(freq_data.spectrum)
    freq_thz = freq_data.freq_hz / 1e12

    # Estimate noise floor from frequencies above the analysis band
    noise_region = amplitude[freq_thz > config.freq_max_thz]
    if len(noise_region) < 5:
        # Fallback: use the highest 20% of frequency range
        cutoff_idx = int(0.8 * len(amplitude))
        noise_region = amplitude[cutoff_idx:]

    noise_floor = float(np.median(noise_region))
    if noise_floor <= 0:
        noise_floor = float(np.min(amplitude[amplitude > 0]))

    # Dynamic range in dB
    with np.errstate(divide="ignore", invalid="ignore"):
        dynamic_range_db = 20.0 * np.log10(amplitude / noise_floor)
    dynamic_range_db = np.nan_to_num(dynamic_range_db, nan=0.0, neginf=0.0)

    # SNR spectrum (linear)
    with np.errstate(divide="ignore", invalid="ignore"):
        snr_spectrum = amplitude / noise_floor
    snr_spectrum = np.nan_to_num(snr_spectrum, nan=0.0)

    # Valid frequency mask: within analysis range AND SNR > 1 (above noise)
    in_range = (freq_thz >= config.freq_min_thz) & (freq_thz <= config.freq_max_thz)
    valid_freq_mask = in_range & (snr_spectrum > 1.0)

    # Find where noise becomes dominant (first crossing below SNR=1
    # in the analysis range, scanning from low to high frequency)
    noise_start_thz = config.freq_max_thz  # default: end of range
    in_range_indices = np.where(in_range)[0]
    if len(in_range_indices) > 0:
        for idx in in_range_indices:
            if snr_spectrum[idx] <= 1.0:
                noise_start_thz = float(freq_thz[idx])
                break

    return NoiseAnalysis(
        noise_floor=noise_floor,
        noise_start_thz=noise_start_thz,
        dynamic_range_db=dynamic_range_db,
        snr_spectrum=snr_spectrum,
        valid_freq_mask=valid_freq_mask,
    )
