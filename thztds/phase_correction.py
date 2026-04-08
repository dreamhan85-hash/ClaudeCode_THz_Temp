"""Phase offset correction for THz-TDS transfer functions.

Based on TeraLyzer's phase offset removal:
- Linear fit in trusted frequency interval
- Extrapolation to 0 Hz
- Correction within ±2π window
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .constants import PI


def compute_phase_offset(
    freq_hz: NDArray[np.float64],
    phase: NDArray[np.float64],
    trusted_range_thz: tuple[float, float] = (0.3, 1.0),
) -> float:
    """Compute the phase offset at 0 Hz by linear extrapolation.

    Fits a line to the unwrapped phase in the trusted frequency interval,
    then extrapolates to 0 Hz.

    Args:
        freq_hz: Frequency array in Hz.
        phase: Unwrapped phase array (radians).
        trusted_range_thz: (f_low, f_high) in THz for linear fit.

    Returns:
        Phase offset at 0 Hz (radians), wrapped to [-π, π].
    """
    freq_thz = freq_hz / 1e12
    mask = (freq_thz >= trusted_range_thz[0]) & (freq_thz <= trusted_range_thz[1])

    if np.sum(mask) < 2:
        return 0.0

    # Linear fit: phase = a * freq_hz + b
    coeffs = np.polyfit(freq_hz[mask], phase[mask], 1)
    phase_at_0 = coeffs[1]  # y-intercept = phase at 0 Hz

    # Wrap to [-π, π]
    phase_at_0 = (phase_at_0 + PI) % (2 * PI) - PI

    return float(phase_at_0)


def correct_phase_offset(
    H_meas: NDArray[np.complex128],
    freq_hz: NDArray[np.float64],
    trusted_range_thz: tuple[float, float] = (0.3, 1.0),
) -> NDArray[np.complex128]:
    """Correct phase offset of measured transfer function.

    Algorithm:
    1. Extract unwrapped phase from H_meas
    2. Linear fit in trusted frequency interval [f_low, f_high]
    3. Extrapolate to 0 Hz to find phase offset
    4. Subtract offset from all phases
    5. Return corrected H_meas

    Args:
        H_meas: Measured complex transfer function.
        freq_hz: Frequency array in Hz.
        trusted_range_thz: (f_low, f_high) in THz for the linear fit region.

    Returns:
        Phase-corrected transfer function (same shape as H_meas).
    """
    # Work with valid (non-NaN) entries only
    valid = ~np.isnan(H_meas)
    if np.sum(valid) < 2:
        return H_meas.copy()

    phase = np.zeros_like(freq_hz)
    phase[valid] = np.unwrap(np.angle(H_meas[valid]))

    offset = compute_phase_offset(freq_hz, phase, trusted_range_thz)

    # Apply correction: remove the offset
    H_corrected = H_meas.copy()
    H_corrected[valid] = np.abs(H_meas[valid]) * np.exp(
        1j * (phase[valid] - offset)
    )

    return H_corrected
