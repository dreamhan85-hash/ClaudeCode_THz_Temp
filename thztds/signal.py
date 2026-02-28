"""Signal processing: windowing, FFT, and time-domain analysis."""

from __future__ import annotations

import numpy as np
from scipy.signal import windows

from .types import THzTimeDomainData, THzFrequencyDomainData


def apply_window(
    data: THzTimeDomainData, window_type: str = "rectangular"
) -> THzTimeDomainData:
    """Apply a window function to the time-domain signal."""
    n = len(data.signal)

    if window_type == "rectangular" or window_type == "none":
        win = np.ones(n)
    elif window_type == "hann":
        win = windows.hann(n)
    elif window_type == "hamming":
        win = windows.hamming(n)
    elif window_type == "blackman":
        win = windows.blackman(n)
    elif window_type == "tukey":
        win = windows.tukey(n, alpha=0.5)
    else:
        raise ValueError(f"Unknown window type: {window_type}")

    return THzTimeDomainData(
        time_ps=data.time_ps.copy(),
        signal=data.signal * win,
        metadata=data.metadata.copy(),
    )


def compute_fft(
    data: THzTimeDomainData, zero_pad_factor: int = 1
) -> THzFrequencyDomainData:
    """Compute FFT of time-domain THz signal.

    Args:
        zero_pad_factor: 0 = no padding (use original N),
                         1 = pad to next power of 2,
                         2+ = pad to next power of 2 after N*factor.
    """
    n_original = len(data.signal)

    if zero_pad_factor == 0:
        # No padding at all - use exact N
        n_padded = n_original
    else:
        n_padded = int(2 ** np.ceil(np.log2(n_original * zero_pad_factor)))

    # Time step
    dt_ps = (data.time_ps[-1] - data.time_ps[0]) / (n_original - 1)
    dt_s = dt_ps * 1e-12

    # FFT scaled by dt for physical units
    spectrum_full = np.fft.fft(data.signal, n=n_padded) * dt_s

    # Frequency axis
    freq_full = np.fft.fftfreq(n_padded, d=dt_s)

    # Keep only positive frequencies
    pos_mask = freq_full >= 0
    freq_hz = freq_full[pos_mask]
    spectrum = spectrum_full[pos_mask]

    return THzFrequencyDomainData(freq_hz=freq_hz, spectrum=spectrum)


def find_pulse_peak(data: THzTimeDomainData) -> tuple[int, float]:
    """Return (index, time_ps) of the main pulse peak."""
    idx = np.argmax(np.abs(data.signal))
    return int(idx), float(data.time_ps[idx])


def compute_time_delay(
    ref: THzTimeDomainData, sample: THzTimeDomainData
) -> float:
    """Compute time delay (ps) between reference and sample pulse peaks."""
    _, ref_peak_time = find_pulse_peak(ref)
    _, sample_peak_time = find_pulse_peak(sample)
    return sample_peak_time - ref_peak_time
