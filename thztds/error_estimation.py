"""Error estimation and confidence intervals for THz-TDS results."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .constants import C0, PI
from .types import OpticalProperties, NoiseAnalysis


def compute_confidence_intervals(
    props: OpticalProperties,
    noise: NoiseAnalysis,
    sigma: float = 2.0,
) -> OpticalProperties:
    """Estimate uncertainty in optical properties from noise analysis.

    Uses noise-based error propagation: the uncertainty in the transfer
    function amplitude (delta_H / H ~ 1/SNR) propagates into n and kappa.

    For a thin slab:
        delta_n ~ c / (2*pi*f*d) * delta_phi
        delta_kappa ~ c / (2*pi*f*d) * (delta_H/H)
        delta_alpha ~ 4*pi*f / c * delta_kappa

    Args:
        props: Extracted optical properties.
        noise: Noise analysis results (provides SNR per frequency).
        sigma: Number of standard deviations for confidence interval.

    Returns:
        New OpticalProperties with n_std, kappa_std, alpha_std filled.
    """
    freq_hz = props.freq_hz
    thickness_m = props.thickness_mm * 1e-3

    # SNR at the analysis frequencies
    # Map from noise analysis grid to props grid
    snr = _interpolate_snr(freq_hz, noise)
    snr = np.maximum(snr, 1.0)  # Floor at 1 to avoid division by zero

    # Amplitude uncertainty: delta_H/H ~ 1/SNR
    rel_amplitude_err = 1.0 / snr

    # Phase uncertainty: delta_phi ~ 1/SNR (for high SNR regime)
    delta_phi = 1.0 / snr

    # Propagate to n: delta_n ~ c/(2*pi*f*d) * delta_phi
    omega = 2.0 * PI * freq_hz
    with np.errstate(divide="ignore", invalid="ignore"):
        n_std = sigma * C0 / (omega * thickness_m) * delta_phi
    n_std = np.nan_to_num(n_std, nan=0.0, posinf=0.0)

    # Propagate to kappa: delta_kappa ~ c/(2*pi*f*d) * (delta_H/H)
    with np.errstate(divide="ignore", invalid="ignore"):
        kappa_std = sigma * C0 / (omega * thickness_m) * rel_amplitude_err
    kappa_std = np.nan_to_num(kappa_std, nan=0.0, posinf=0.0)

    # Propagate to alpha: alpha = 4*pi*f*kappa/c → delta_alpha = 4*pi*f/c * delta_kappa
    alpha_std = 4.0 * PI * freq_hz * kappa_std / (C0 * 100.0)  # [1/cm]

    return OpticalProperties(
        freq_hz=props.freq_hz.copy(),
        n=props.n.copy(),
        kappa=props.kappa.copy(),
        alpha=props.alpha.copy(),
        thickness_mm=props.thickness_mm,
        temperature_c=props.temperature_c,
        replicate=props.replicate,
        n_std=n_std,
        kappa_std=kappa_std,
        alpha_std=alpha_std,
    )


def compute_alpha_max(
    noise: NoiseAnalysis,
    thickness_mm: float,
) -> NDArray[np.float64]:
    """Compute noise-limited maximum detectable absorption coefficient.

    The maximum measurable absorption is limited by the dynamic range:
        alpha_max = -ln(1/SNR) / d = ln(SNR) / d

    This represents the absorption at which the transmitted signal
    falls to the noise floor.

    Args:
        noise: Noise analysis with SNR spectrum.
        thickness_mm: Sample thickness in mm.

    Returns:
        alpha_max array in [1/cm] at each frequency.
    """
    thickness_cm = thickness_mm * 0.1
    snr = np.maximum(noise.snr_spectrum, 1.0)

    with np.errstate(divide="ignore", invalid="ignore"):
        alpha_max = np.log(snr) / thickness_cm
    alpha_max = np.nan_to_num(alpha_max, nan=0.0, posinf=0.0, neginf=0.0)

    return alpha_max


def _interpolate_snr(
    target_freq_hz: NDArray[np.float64],
    noise: NoiseAnalysis,
) -> NDArray[np.float64]:
    """Get SNR values at target frequencies.

    If the noise SNR array covers the same grid, return directly.
    Otherwise, use nearest-neighbor lookup.
    """
    if len(noise.snr_spectrum) == len(target_freq_hz):
        return noise.snr_spectrum.copy()

    # Simple approach: assume uniform frequency grid and use indexing
    # This works when both come from the same FFT
    n_noise = len(noise.snr_spectrum)
    n_target = len(target_freq_hz)
    indices = np.linspace(0, n_noise - 1, n_target).astype(int)
    indices = np.clip(indices, 0, n_noise - 1)
    return noise.snr_spectrum[indices]
