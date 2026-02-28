"""Numerical extraction of optical properties using Nelder-Mead optimization."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize

from .constants import C0, PI
from .types import (
    THzFrequencyDomainData,
    OpticalProperties,
    ExtractionConfig,
    THzTimeDomainData,
)
from .signal import compute_time_delay
from .transfer_function import (
    compute_measured_transfer_function,
    compute_theoretical_transfer_function_single,
)


def _objective_single_freq(
    params: NDArray[np.float64],
    freq_hz: float,
    H_meas: complex,
    thickness_m: float,
    n_fp_echoes: int,
    thin_film: bool = False,
) -> float:
    """Cost function at a single frequency: |H_meas - H_theory|^2."""
    n_val, kappa_val = params[0], params[1]

    H_theory = compute_theoretical_transfer_function_single(
        freq_hz, n_val, kappa_val, thickness_m, n_fp_echoes, thin_film=thin_film
    )

    diff = H_meas - H_theory
    return float(np.real(diff * np.conj(diff)))


def extract_at_single_frequency(
    freq_hz: float,
    H_meas: complex,
    thickness_m: float,
    n_fp_echoes: int,
    n_init: float,
    kappa_init: float,
    thin_film: bool = False,
) -> tuple[float, float]:
    """Extract n and kappa at a single frequency using Nelder-Mead."""
    result = minimize(
        _objective_single_freq,
        x0=np.array([n_init, kappa_init]),
        args=(freq_hz, H_meas, thickness_m, n_fp_echoes, thin_film),
        method="Nelder-Mead",
        options={"xatol": 1e-8, "fatol": 1e-12, "maxiter": 1000},
    )

    return result.x[0], result.x[1]


def extract_optical_properties(
    ref_td: THzTimeDomainData,
    sample_td: THzTimeDomainData,
    ref_freq: THzFrequencyDomainData,
    sample_freq: THzFrequencyDomainData,
    config: ExtractionConfig,
    progress_callback=None,
) -> OpticalProperties:
    """Extract optical properties across the analysis frequency range.

    Uses frequency-by-frequency Nelder-Mead optimization with warm-starting
    from adjacent frequency points.
    """
    thickness_m = config.thickness_mm * 1e-3

    # Get sample temperature for air correction
    temp_sample = sample_td.metadata.get("temperature_c")
    temp_ref = config.ref_temperature_c
    chamber_m = config.chamber_length_cm * 0.01

    # Compute measured transfer function with air temperature correction
    H_meas = compute_measured_transfer_function(
        ref_freq,
        sample_freq,
        temp_sample_c=temp_sample if config.apply_air_correction else None,
        temp_ref_c=temp_ref,
        chamber_length_m=chamber_m,
    )

    # Determine frequency range indices
    freq_hz = ref_freq.freq_hz
    freq_thz = freq_hz / 1e12
    f_mask = (freq_thz >= config.freq_min_thz) & (freq_thz <= config.freq_max_thz)
    # Also exclude NaN values in H_meas
    valid_mask = f_mask & ~np.isnan(H_meas)
    f_indices = np.where(valid_mask)[0]

    if len(f_indices) == 0:
        raise ValueError("No valid frequency points in the analysis range.")

    # Initial guess from time delay (negative delay = faster arrival = lower effective n)
    delta_t_ps = compute_time_delay(ref_td, sample_td)
    delta_t_s = delta_t_ps * 1e-12
    if abs(delta_t_s) > 1e-15 and thickness_m > 0:
        # n = 1 + delta_t * c / d (preserving sign: negative delta → n < 1 possible)
        n_init = 1.0 + delta_t_s * C0 / thickness_m
    else:
        n_init = config.n_initial_guess
    kappa_init = config.kappa_initial_guess

    n_result = np.zeros(len(f_indices))
    kappa_result = np.zeros(len(f_indices))

    n_guess, kappa_guess = n_init, kappa_init

    for i, idx in enumerate(f_indices):
        n_val, kappa_val = extract_at_single_frequency(
            freq_hz[idx],
            H_meas[idx],
            thickness_m,
            config.n_fp_echoes,
            n_guess,
            kappa_guess,
            thin_film=config.thin_film,
        )
        n_result[i] = n_val
        kappa_result[i] = kappa_val

        # Warm-start next frequency
        n_guess = n_val
        kappa_guess = kappa_val

        if progress_callback:
            progress_callback(i + 1, len(f_indices))

    # Compute absorption coefficient: alpha = 4*pi*f*kappa / (c0 * 100) [1/cm]
    freq_analysis = freq_hz[f_indices]
    alpha_per_cm = 4.0 * PI * freq_analysis * kappa_result / (C0 * 100.0)

    # Extract metadata
    temp = sample_td.metadata.get("temperature_c")
    rep = sample_td.metadata.get("replicate")

    return OpticalProperties(
        freq_hz=freq_analysis,
        n=n_result,
        kappa=kappa_result,
        alpha=alpha_per_cm,
        thickness_mm=config.thickness_mm,
        temperature_c=temp,
        replicate=rep,
    )
