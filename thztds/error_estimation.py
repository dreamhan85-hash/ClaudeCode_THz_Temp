"""Error estimation and confidence intervals for THz-TDS.

Based on TeraLyzer (Jepsen & Fischer 2005, Pupeza et al.):
- Confidence intervals from replicate statistics
- Noise-propagated uncertainty
- alpha_max from dynamic range limit
- Thickness uncertainty propagation
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .types import OpticalProperties, NoiseAnalysis
from .constants import C0


def compute_alpha_max(
    noise_analysis: NoiseAnalysis,
    thickness_m: float,
    freq_hz: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Compute maximum measurable absorption coefficient from dynamic range.

    alpha_max(f) = (2 / d) * ln(DR_linear(f))

    where DR_linear = 10^(DR_dB / 20). Values of alpha above alpha_max
    are unreliable because the signal is at or below the noise floor.

    Args:
        noise_analysis: Noise analysis results.
        thickness_m: Sample thickness in meters.
        freq_hz: Frequency array to evaluate at.

    Returns:
        Maximum absorption coefficient in 1/cm at each frequency.
    """
    if thickness_m <= 0:
        return np.full_like(freq_hz, np.inf)

    # Interpolate DR to the given frequency grid if needed
    dr_db = noise_analysis.dynamic_range_db

    # Convert dB to linear ratio
    dr_linear = 10.0 ** (np.clip(dr_db, 0, None) / 20.0)

    # alpha_max = (2/d) * ln(DR), convert to 1/cm
    alpha_max_per_m = (2.0 / thickness_m) * np.log(np.maximum(dr_linear, 1.0))
    alpha_max_per_cm = alpha_max_per_m / 100.0

    # Match length to freq_hz if needed
    if len(alpha_max_per_cm) != len(freq_hz):
        alpha_max_per_cm = np.interp(
            freq_hz,
            noise_analysis.snr_spectrum[:len(alpha_max_per_cm)],
            alpha_max_per_cm,
            left=alpha_max_per_cm[0] if len(alpha_max_per_cm) > 0 else 0,
            right=0,
        )

    return alpha_max_per_cm


def compute_noise_propagated_uncertainty(
    noise_analysis: NoiseAnalysis,
    freq_hz: NDArray[np.float64],
    thickness_m: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Estimate uncertainty in n and alpha from measurement noise.

    Uses the SNR to estimate how noise propagates into extracted parameters:
        delta_n ≈ c / (2π * f * d * SNR^0.5)
        delta_alpha ≈ 2 / (d * SNR^0.5)

    Args:
        noise_analysis: Noise analysis results.
        freq_hz: Frequency array.
        thickness_m: Sample thickness in meters.

    Returns:
        (delta_n, delta_alpha_per_cm) uncertainty arrays.
    """
    if thickness_m <= 0:
        return np.zeros_like(freq_hz), np.zeros_like(freq_hz)

    # Interpolate SNR to freq grid if needed
    snr = noise_analysis.snr_spectrum
    if len(snr) != len(freq_hz):
        snr = np.interp(freq_hz, np.linspace(freq_hz[0], freq_hz[-1], len(snr)), snr)

    snr_safe = np.maximum(snr, 1.0)
    sqrt_snr = np.sqrt(snr_safe)

    # Frequency-dependent n uncertainty
    omega = 2.0 * np.pi * np.maximum(freq_hz, 1.0)
    delta_n = C0 / (omega * thickness_m * sqrt_snr)

    # Absorption uncertainty (1/cm)
    delta_alpha_per_m = 2.0 / (thickness_m * sqrt_snr)
    delta_alpha_per_cm = delta_alpha_per_m / 100.0

    return delta_n, delta_alpha_per_cm


def compute_thickness_uncertainty(
    n: NDArray[np.float64],
    freq_hz: NDArray[np.float64],
    thickness_m: float,
    thickness_step_m: float,
) -> NDArray[np.float64]:
    """Propagate thickness uncertainty into refractive index uncertainty.

    From n = 1 + delta_t * c / d:
        delta_n_from_d = |n - 1| * delta_d / d

    Args:
        n: Extracted refractive index array.
        freq_hz: Frequency array (unused but kept for API consistency).
        thickness_m: Sample thickness in meters.
        thickness_step_m: Thickness step size (resolution) in meters.

    Returns:
        delta_n from thickness uncertainty.
    """
    if thickness_m <= 0:
        return np.zeros_like(n)

    return np.abs(n - 1.0) * (thickness_step_m / thickness_m)


def compute_confidence_intervals(
    props: OpticalProperties,
    noise_analysis: NoiseAnalysis | None = None,
    thickness_step_um: float = 0.0,
    sigma: float = 2.0,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Compute combined confidence intervals for optical properties.

    Combines uncertainties from:
    1. Replicate statistics (if n_std available)
    2. Noise propagation (if noise_analysis provided)
    3. Thickness uncertainty (if thickness_step > 0)

    Total uncertainty = sqrt(sum of squared individual uncertainties) * sigma

    Args:
        props: Extracted optical properties (may include n_std from replicates).
        noise_analysis: Noise analysis results (optional).
        thickness_step_um: Thickness optimization step in micrometers.
        sigma: Number of sigmas for confidence interval (default: 2 = ~95%).

    Returns:
        (delta_n, delta_kappa, delta_alpha) confidence interval half-widths.
    """
    n_points = len(props.freq_hz)
    thickness_m = props.thickness_mm * 1e-3

    # Component 1: Replicate statistics
    var_n = np.zeros(n_points)
    var_kappa = np.zeros(n_points)
    var_alpha = np.zeros(n_points)

    if props.n_std is not None:
        var_n += props.n_std**2
    if props.kappa_std is not None:
        var_kappa += props.kappa_std**2
    if props.alpha_std is not None:
        var_alpha += props.alpha_std**2

    # Component 2: Noise propagation
    if noise_analysis is not None:
        delta_n_noise, delta_alpha_noise = compute_noise_propagated_uncertainty(
            noise_analysis, props.freq_hz, thickness_m,
        )
        var_n += delta_n_noise**2
        var_alpha += delta_alpha_noise**2
        # Approximate kappa uncertainty from alpha uncertainty
        # alpha = 4*pi*f*kappa/c → delta_kappa = delta_alpha * c / (4*pi*f)
        freq_safe = np.maximum(props.freq_hz, 1.0)
        var_kappa += (delta_alpha_noise * 100.0 * C0 / (4.0 * np.pi * freq_safe))**2

    # Component 3: Thickness uncertainty
    if thickness_step_um > 0:
        delta_n_thick = compute_thickness_uncertainty(
            props.n, props.freq_hz, thickness_m, thickness_step_um * 1e-6,
        )
        var_n += delta_n_thick**2

    # Combine and scale by sigma
    delta_n = sigma * np.sqrt(var_n)
    delta_kappa = sigma * np.sqrt(var_kappa)
    delta_alpha = sigma * np.sqrt(var_alpha)

    return delta_n, delta_kappa, delta_alpha
