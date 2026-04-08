"""Spatially Variant Moving Average Filter (SVMAF) for THz-TDS.

Based on TeraLyzer/Pupeza et al.: frequency-dependent adaptive window
that preserves features within confidence intervals while smoothing noise.
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .types import SvmafConfig


def _compute_max_window_at_point(
    values: NDArray[np.float64],
    confidence: NDArray[np.float64],
    idx: int,
    max_half_width: int,
) -> int:
    """Find the largest symmetric window centered at idx whose average stays within confidence.

    Returns the half-width (number of points on each side).
    """
    n = len(values)
    center_val = values[idx]
    center_ci = confidence[idx]

    for hw in range(1, max_half_width + 1):
        lo = max(0, idx - hw)
        hi = min(n, idx + hw + 1)
        avg = np.mean(values[lo:hi])

        # Check if the averaged value stays within the confidence interval
        if abs(avg - center_val) > center_ci:
            return max(1, hw - 1)

    return max_half_width


def svmaf_filter(
    values: NDArray[np.float64],
    confidence: NDArray[np.float64],
    config: SvmafConfig | None = None,
) -> NDArray[np.float64]:
    """Apply Spatially Variant Moving Average Filter.

    At each frequency point, finds the largest symmetric moving average window
    such that the filtered value remains within the confidence interval of
    the original value. Near sharp features (e.g., absorption peaks), the
    window shrinks automatically; in flat regions, it widens for smoothing.

    Args:
        values: Array of optical property values (n, kappa, or alpha).
        confidence: Confidence interval half-width at each frequency point.
            Filtered values must satisfy |filtered - original| <= confidence.
        config: SVMAF configuration. Uses defaults if None.

    Returns:
        Filtered values array (same shape as input).
    """
    if config is None:
        config = SvmafConfig()

    n = len(values)
    if n == 0:
        return values.copy()

    max_half_width = config.max_window_size // 2
    filtered = np.zeros_like(values)

    for i in range(n):
        hw = _compute_max_window_at_point(values, confidence, i, max_half_width)
        lo = max(0, i - hw)
        hi = min(n, i + hw + 1)
        filtered[i] = np.mean(values[lo:hi])

    return filtered


def compute_confidence_from_std(
    std: NDArray[np.float64],
    sigma: float = 2.0,
) -> NDArray[np.float64]:
    """Convert standard deviation to confidence interval half-width.

    Args:
        std: Standard deviation array from replicate measurements.
        sigma: Number of standard deviations for confidence (default: 2.0 = ~95%).

    Returns:
        Confidence interval half-width array.
    """
    return std * sigma


def svmaf_filter_properties(
    values: NDArray[np.float64],
    std: NDArray[np.float64] | None = None,
    config: SvmafConfig | None = None,
) -> NDArray[np.float64]:
    """Convenience function: filter optical property with automatic confidence.

    If std is not available, uses a fraction of the value range as fallback.

    Args:
        values: Optical property values to filter.
        std: Standard deviation from replicates (optional).
        config: SVMAF configuration.

    Returns:
        Filtered values.
    """
    if config is None:
        config = SvmafConfig()

    if std is not None and np.any(std > 0):
        confidence = compute_confidence_from_std(std, config.confidence_sigma)
    else:
        # Fallback: use 2% of value range as confidence
        val_range = np.ptp(values)
        if val_range > 0:
            confidence = np.full_like(values, 0.02 * val_range)
        else:
            return values.copy()

    return svmaf_filter(values, confidence, config)
