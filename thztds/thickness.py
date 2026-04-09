"""Thickness optimization for THz-TDS samples."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .constants import C0, PI
from .types import (
    THzTimeDomainData,
    ExtractionConfig,
    ThicknessOptConfig,
    ThicknessResult,
)
from .signal import apply_window, compute_fft
from .optimization import extract_optical_properties


def _total_variation(arr: NDArray[np.float64]) -> float:
    """Compute total variation of a 1D array: sum(|diff|)."""
    return float(np.sum(np.abs(np.diff(arr))))


def optimize_thickness(
    ref_data: THzTimeDomainData,
    sample_data: THzTimeDomainData,
    config: ExtractionConfig,
    opt_config: ThicknessOptConfig = ThicknessOptConfig(),
) -> ThicknessResult:
    """Find optimal sample thickness by scanning over a range.

    Supports two merit functions:
    - "total_variation": Minimize total variation of n(f).
      A correct thickness yields a flat n(f); wrong thickness
      introduces oscillations.
    - "quasi_space": Find the thickness that minimizes oscillation
      energy in the quasi-space (IFFT of n(f)).

    Args:
        ref_data: Reference time-domain data.
        sample_data: Sample time-domain data.
        config: Base extraction config (thickness_mm is overridden per scan).
        opt_config: Thickness scan parameters.

    Returns:
        ThicknessResult with optimal thickness and merit curve.
    """
    center_mm = config.thickness_mm
    center_um = center_mm * 1000.0

    # Override center if opt_config specifies one
    if opt_config.center_um > 0:
        center_um = opt_config.center_um

    half_range = opt_config.interval_um
    step = opt_config.step_um

    thicknesses_um = np.arange(
        center_um - half_range,
        center_um + half_range + step * 0.5,
        step,
    )

    # Pre-compute FFTs (these don't depend on thickness)
    ref_windowed = apply_window(ref_data, config.window_type)
    sample_windowed = apply_window(sample_data, config.window_type)
    ref_freq = compute_fft(ref_windowed, config.zero_pad_factor)
    sample_freq = compute_fft(sample_windowed, config.zero_pad_factor)

    merit_values = np.empty(len(thicknesses_um))

    for i, d_um in enumerate(thicknesses_um):
        # Create config with this trial thickness
        trial_config = ExtractionConfig(
            thickness_mm=d_um / 1000.0,
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
            ref_data, sample_data, ref_freq, sample_freq, trial_config
        )

        if opt_config.method == "total_variation":
            merit_values[i] = _total_variation(props.n)
        else:
            # quasi_space: IFFT of n(f) and measure oscillation energy
            n_centered = props.n - np.mean(props.n)
            quasi = np.fft.ifft(n_centered)
            # Merit = energy excluding DC component
            merit_values[i] = float(np.sum(np.abs(quasi[1:]) ** 2))

    # Optimal thickness = minimum merit
    best_idx = int(np.argmin(merit_values))
    optimal_um = float(thicknesses_um[best_idx])

    return ThicknessResult(
        optimal_thickness_um=optimal_um,
        all_thicknesses_um=thicknesses_um,
        merit_values=merit_values,
        method=opt_config.method,
    )
