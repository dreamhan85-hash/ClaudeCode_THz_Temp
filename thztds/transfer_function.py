"""Transfer function computation for THz-TDS."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .constants import C0, N_AIR, PI
from .types import THzFrequencyDomainData


def n_air_temperature(temp_c: float) -> float:
    """Compute air refractive index at THz frequencies for a given temperature.

    Uses dry air approximation at 1 atm:
        n_air(T) ≈ 1 + 2.88e-4 × (273.15 / T_kelvin)
    """
    t_kelvin = temp_c + 273.15
    return 1.0 + 2.88e-4 * (273.15 / t_kelvin)


def air_temperature_correction(
    freq_hz: NDArray[np.float64],
    temp_sample_c: float,
    temp_ref_c: float,
    chamber_length_m: float,
) -> NDArray[np.complex128]:
    """Compute phase correction factor for air temperature difference in the chamber.

    When the sample is measured at temp_sample_c, the air inside the chamber
    (length = chamber_length_m) is at that temperature instead of temp_ref_c.

    Returns a complex array to multiply H_meas by, to remove the air effect:
        correction = exp(+j * omega/c * [n_air(T_sample) - n_air(T_ref)] * L_chamber)
    """
    dn_air = n_air_temperature(temp_sample_c) - n_air_temperature(temp_ref_c)
    omega = 2.0 * PI * freq_hz
    # Multiply H_meas by this to correct for hot air path
    return np.exp(1j * (omega / C0) * dn_air * chamber_length_m)


def compute_measured_transfer_function(
    ref_freq: THzFrequencyDomainData,
    sample_freq: THzFrequencyDomainData,
    threshold_ratio: float = 1e-3,
    temp_sample_c: float = None,
    temp_ref_c: float = 20.0,
    chamber_length_m: float = 0.01,
) -> NDArray[np.complex128]:
    """Compute H_meas(omega) = FFT(sample) / FFT(ref), with optional air temp correction.

    If temp_sample_c is provided, corrects for the air refractive index change
    in the chamber (chamber_length_m) due to temperature difference from reference.
    """
    ref_amp = np.abs(ref_freq.spectrum)
    threshold = threshold_ratio * np.max(ref_amp)

    H_meas = np.full_like(ref_freq.spectrum, np.nan + 0j)
    valid = ref_amp > threshold
    H_meas[valid] = sample_freq.spectrum[valid] / ref_freq.spectrum[valid]

    # Apply air temperature correction if temperatures are provided
    if temp_sample_c is not None and temp_sample_c != temp_ref_c:
        correction = air_temperature_correction(
            ref_freq.freq_hz, temp_sample_c, temp_ref_c, chamber_length_m
        )
        H_meas[valid] = H_meas[valid] * correction[valid]

    return H_meas


def compute_fresnel_coefficients(n_tilde: complex) -> tuple[complex, complex]:
    """Compute Fresnel reflection and transmission coefficients at normal incidence.

    Convention: n_tilde = n - j*kappa (physics convention, exp(-j*omega*t))

    Returns:
        r: reflection coefficient (n_tilde - n_air) / (n_tilde + n_air)
        t_coeff: transmission amplitude = 1 - r^2
    """
    r = (n_tilde - N_AIR) / (n_tilde + N_AIR)
    t_coeff = 1.0 - r**2
    return r, t_coeff


def compute_theoretical_transfer_function(
    freq_hz: NDArray[np.float64],
    n: float,
    kappa: float,
    thickness_m: float,
    n_fp_echoes: int = 0,
) -> NDArray[np.complex128]:
    """Compute theoretical transfer function H_theory(omega) for a dielectric slab.

    Uses physics convention: n_tilde = n - j*kappa with exp(-j*omega*t) time dependence.

    The transfer function accounts for:
    - Transmission through two air-sample interfaces (Fresnel)
    - Phase accumulation relative to air path of same thickness
    - Optional Fabry-Perot echo summation (M echoes)
    """
    omega = 2.0 * PI * freq_hz
    k0 = omega / C0
    n_tilde = n - 1j * kappa

    r, t_coeff = compute_fresnel_coefficients(n_tilde)

    # Phase propagation relative to air: exp(-j * (n_tilde - 1) * k0 * d)
    propagation = np.exp(-1j * (n_tilde - N_AIR) * k0 * thickness_m)

    # Fabry-Perot summation
    if n_fp_echoes == 0:
        fp_sum = np.ones_like(freq_hz, dtype=np.complex128)
    else:
        fp_factor = r**2 * np.exp(-2j * n_tilde * k0 * thickness_m)
        fp_sum = np.zeros_like(freq_hz, dtype=np.complex128)
        for m in range(n_fp_echoes + 1):
            fp_sum += fp_factor**m

    H_theory = t_coeff * propagation * fp_sum

    return H_theory


def compute_theoretical_transfer_function_single(
    freq_hz: float,
    n: float,
    kappa: float,
    thickness_m: float,
    n_fp_echoes: int = 0,
    thin_film: bool = False,
) -> complex:
    """Compute H_theory at a single frequency (scalar version for optimization).

    If thin_film=True, uses thin-film approximation (no Fresnel reflections).
    Valid when thickness << wavelength, e.g. 20 μm at THz (λ ~ 300 μm).
    This allows n < 1 without model breakdown.
    """
    omega = 2.0 * PI * freq_hz
    k0 = omega / C0
    n_tilde = n - 1j * kappa

    if thin_film:
        # Thin-film approximation: H ≈ exp(-j*(n_tilde - n_air)*k0*d)
        # Ignores Fresnel reflection losses (< 2% for typical n values)
        return np.exp(-1j * (n_tilde - N_AIR) * k0 * thickness_m)

    r = (n_tilde - N_AIR) / (n_tilde + N_AIR)
    t_coeff = 1.0 - r**2

    propagation = np.exp(-1j * (n_tilde - N_AIR) * k0 * thickness_m)

    if n_fp_echoes == 0:
        fp_sum = 1.0
    else:
        fp_factor = r**2 * np.exp(-2j * n_tilde * k0 * thickness_m)
        fp_sum = sum(fp_factor**m for m in range(n_fp_echoes + 1))

    return t_coeff * propagation * fp_sum
