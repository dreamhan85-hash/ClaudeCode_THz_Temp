"""Phase offset correction for THz-TDS frequency-domain data."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .types import THzFrequencyDomainData


def correct_phase_offset(
    freq_data: THzFrequencyDomainData,
    ref_freq: THzFrequencyDomainData | None = None,
) -> THzFrequencyDomainData:
    """Remove linear phase offset from frequency-domain data.

    Fits a line to the unwrapped phase in the low-frequency region and
    subtracts the DC offset (phi_0) so that the phase starts near zero.

    If ref_freq is provided, the correction is computed relative to the
    reference phase (sample_phase - ref_phase), correcting only the
    residual offset.

    Args:
        freq_data: Frequency-domain data to correct.
        ref_freq: Optional reference for relative correction.

    Returns:
        New THzFrequencyDomainData with corrected phase.
    """
    phase = np.unwrap(np.angle(freq_data.spectrum))
    freq_hz = freq_data.freq_hz

    if ref_freq is not None:
        ref_phase = np.unwrap(np.angle(ref_freq.spectrum))
        phase_diff = phase - ref_phase
    else:
        phase_diff = phase

    # Use low-frequency region (first 10% of positive frequencies) for fitting
    n_fit = max(10, len(freq_hz) // 10)
    # Skip DC (index 0) if present
    start_idx = 1 if freq_hz[0] == 0 else 0
    end_idx = start_idx + n_fit

    if end_idx > len(freq_hz):
        end_idx = len(freq_hz)

    fit_freq = freq_hz[start_idx:end_idx]
    fit_phase = phase_diff[start_idx:end_idx]

    # Linear fit: phase = slope * freq + phi_0
    if len(fit_freq) >= 2:
        coeffs = np.polyfit(fit_freq, fit_phase, 1)
        phi_0 = coeffs[1]  # DC offset
    else:
        phi_0 = phase_diff[start_idx] if start_idx < len(phase_diff) else 0.0

    # Subtract only the DC offset (keep the linear/group delay component)
    corrected_phase = phase - phi_0

    # Reconstruct spectrum with corrected phase
    amplitude = np.abs(freq_data.spectrum)
    corrected_spectrum = amplitude * np.exp(1j * corrected_phase)

    return THzFrequencyDomainData(
        freq_hz=freq_data.freq_hz.copy(),
        spectrum=corrected_spectrum,
    )
