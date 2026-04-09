"""Spatially Variant Moving Average Filter (SVMAF) for THz-TDS data."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .types import OpticalProperties, SvmafConfig


def svmaf_filter(
    data: NDArray[np.float64],
    confidence: NDArray[np.float64],
    config: SvmafConfig = SvmafConfig(),
) -> NDArray[np.float64]:
    """Apply Spatially Variant Moving Average Filter.

    The window size at each point is inversely proportional to the
    local confidence. High-confidence points get minimal smoothing;
    low-confidence points get stronger smoothing.

    Args:
        data: 1D array to filter.
        confidence: Confidence weights (e.g., SNR or 1/std). Must be
            same length as data. Higher = more confident = less smoothing.
        config: SVMAF parameters.

    Returns:
        Filtered 1D array.
    """
    n = len(data)
    if n == 0:
        return data.copy()

    filtered = np.empty(n)

    # Normalize confidence to [0, 1]
    c_max = np.max(confidence)
    if c_max > 0:
        c_norm = confidence / c_max
    else:
        c_norm = np.ones(n)

    max_w = config.max_window_size

    for i in range(n):
        # Window half-width: inversely proportional to confidence
        # High confidence → small window; low confidence → large window
        half_w = int(max_w * (1.0 - c_norm[i]) / 2.0)
        half_w = max(half_w, 0)

        lo = max(0, i - half_w)
        hi = min(n, i + half_w + 1)

        # Weighted average using confidence as weights
        segment = data[lo:hi]
        weights = confidence[lo:hi]
        w_sum = np.sum(weights)

        if w_sum > 0:
            filtered[i] = np.sum(segment * weights) / w_sum
        else:
            filtered[i] = data[i]

    return filtered


def svmaf_filter_properties(
    props: OpticalProperties,
    config: SvmafConfig = SvmafConfig(),
) -> OpticalProperties:
    """Apply SVMAF to all optical properties (n, kappa, alpha).

    Uses the inverse of local standard deviation (if available) or
    uniform confidence as the confidence metric.

    Args:
        props: Optical properties to filter.
        config: SVMAF configuration.

    Returns:
        New OpticalProperties with filtered n, kappa, alpha.
    """
    # Build confidence from std if available, otherwise uniform
    if props.n_std is not None and np.any(props.n_std > 0):
        confidence_n = 1.0 / np.maximum(props.n_std, 1e-12)
    else:
        confidence_n = np.ones_like(props.n)

    if props.kappa_std is not None and np.any(props.kappa_std > 0):
        confidence_k = 1.0 / np.maximum(props.kappa_std, 1e-12)
    else:
        confidence_k = np.ones_like(props.kappa)

    if props.alpha_std is not None and np.any(props.alpha_std > 0):
        confidence_a = 1.0 / np.maximum(props.alpha_std, 1e-12)
    else:
        confidence_a = np.ones_like(props.alpha)

    return OpticalProperties(
        freq_hz=props.freq_hz.copy(),
        n=svmaf_filter(props.n, confidence_n, config),
        kappa=svmaf_filter(props.kappa, confidence_k, config),
        alpha=svmaf_filter(props.alpha, confidence_a, config),
        thickness_mm=props.thickness_mm,
        temperature_c=props.temperature_c,
        replicate=props.replicate,
        n_std=props.n_std.copy() if props.n_std is not None else None,
        kappa_std=props.kappa_std.copy() if props.kappa_std is not None else None,
        alpha_std=props.alpha_std.copy() if props.alpha_std is not None else None,
    )
