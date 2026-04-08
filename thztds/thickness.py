"""Thickness optimization via Quasi-Space and Total Variation methods.

Based on TeraLyzer (Scheller et al., Pupeza et al.):
- Quasi-Space: FFT of n(f) → minimize FP oscillation peak
- Total Variation: minimize Σ|n(f_i+1) - n(f_i)|
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .types import (
    THzTimeDomainData,
    THzFrequencyDomainData,
    ExtractionConfig,
    ThicknessOptConfig,
    ThicknessResult,
)
from .signal import apply_window, compute_fft
from .transfer_function import compute_measured_transfer_function
from .optimization import extract_optical_properties


def _extract_n_at_thickness(
    ref_td: THzTimeDomainData,
    sample_td: THzTimeDomainData,
    ref_freq: THzFrequencyDomainData,
    sample_freq: THzFrequencyDomainData,
    config: ExtractionConfig,
    thickness_mm: float,
) -> NDArray[np.float64]:
    """Extract refractive index array at a given thickness."""
    cfg = ExtractionConfig(
        thickness_mm=thickness_mm,
        freq_min_thz=config.freq_min_thz,
        freq_max_thz=config.freq_max_thz,
        n_fp_echoes=config.n_fp_echoes,
        window_type=config.window_type,
        zero_pad_factor=config.zero_pad_factor,
        n_initial_guess=config.n_initial_guess,
        kappa_initial_guess=config.kappa_initial_guess,
        thin_film=config.thin_film,
        ref_temperature_c=config.ref_temperature_c,
        chamber_length_cm=config.chamber_length_cm,
        total_path_cm=config.total_path_cm,
        apply_air_correction=config.apply_air_correction,
    )
    props = extract_optical_properties(
        ref_td, sample_td, ref_freq, sample_freq, cfg
    )
    return props.n


def compute_quasi_space_merit(n_array: NDArray[np.float64]) -> float:
    """Compute Quasi-Space figure of merit for a given n(f) array.

    Takes FFT of n(f) and returns the maximum peak value excluding DC.
    Lower values indicate fewer Fabry-Perot oscillations → better thickness.

    Args:
        n_array: Refractive index vs frequency array.

    Returns:
        QS merit value (lower is better).
    """
    if len(n_array) < 4:
        return float("inf")

    # Remove mean (DC component)
    n_centered = n_array - np.mean(n_array)

    # FFT to quasi-space
    qs = np.abs(np.fft.fft(n_centered))

    # Exclude DC (index 0) and take max of remaining
    # Only look at first half (positive quasi-space)
    half = len(qs) // 2
    if half < 2:
        return float("inf")

    return float(np.max(qs[1:half]))


def compute_total_variation_merit(n_array: NDArray[np.float64]) -> float:
    """Compute Total Variation figure of merit for a given n(f) array.

    TV = Σ|n(f_i+1) - n(f_i)|
    Lower TV means smoother n(f) → fewer FP oscillations → better thickness.

    Args:
        n_array: Refractive index vs frequency array.

    Returns:
        TV merit value (lower is better).
    """
    if len(n_array) < 2:
        return float("inf")
    return float(np.sum(np.abs(np.diff(n_array))))


def optimize_thickness(
    ref_td: THzTimeDomainData,
    sample_td: THzTimeDomainData,
    ref_freq: THzFrequencyDomainData,
    sample_freq: THzFrequencyDomainData,
    config: ExtractionConfig,
    thickness_config: ThicknessOptConfig,
    progress_callback=None,
) -> ThicknessResult:
    """Scan thickness range and find optimal value.

    For each candidate thickness, extracts n(f) and computes the chosen
    merit function (Quasi-Space or Total Variation). The optimal thickness
    is at the minimum merit value.

    Args:
        ref_td: Reference time-domain data.
        sample_td: Sample time-domain data.
        ref_freq: Reference frequency-domain data.
        sample_freq: Sample frequency-domain data.
        config: Base extraction configuration.
        thickness_config: Thickness scan parameters.
        progress_callback: Optional (current, total) callback.

    Returns:
        ThicknessResult with optimal thickness and merit curve.
    """
    # Build thickness array
    center = thickness_config.center_um
    interval = thickness_config.interval_um
    step = thickness_config.step_um

    thicknesses_um = np.arange(
        center - interval,
        center + interval + step * 0.5,
        step,
    )

    # Select merit function
    if thickness_config.method == "total_variation":
        merit_fn = compute_total_variation_merit
    else:
        merit_fn = compute_quasi_space_merit

    merit_values = np.zeros(len(thicknesses_um))

    for i, d_um in enumerate(thicknesses_um):
        d_mm = d_um / 1000.0
        try:
            n_array = _extract_n_at_thickness(
                ref_td, sample_td, ref_freq, sample_freq, config, d_mm
            )
            merit_values[i] = merit_fn(n_array)
        except (ValueError, RuntimeError):
            merit_values[i] = float("inf")

        if progress_callback:
            progress_callback(i + 1, len(thicknesses_um))

    # Find optimal thickness at minimum merit
    best_idx = int(np.argmin(merit_values))
    optimal_um = float(thicknesses_um[best_idx])

    return ThicknessResult(
        optimal_thickness_um=optimal_um,
        all_thicknesses_um=thicknesses_um,
        merit_values=merit_values,
        method=thickness_config.method,
    )
