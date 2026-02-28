"""High-level orchestration: end-to-end extraction pipeline."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from .types import (
    THzTimeDomainData,
    THzFrequencyDomainData,
    OpticalProperties,
    ExtractionConfig,
)
from .signal import apply_window, compute_fft
from .optimization import extract_optical_properties


def process_single_measurement(
    ref_data: THzTimeDomainData,
    sample_data: THzTimeDomainData,
    config: ExtractionConfig,
    progress_callback: Callable | None = None,
) -> OpticalProperties:
    """End-to-end processing: raw time-domain data -> optical properties."""
    ref_windowed = apply_window(ref_data, config.window_type)
    sample_windowed = apply_window(sample_data, config.window_type)

    ref_freq = compute_fft(ref_windowed, config.zero_pad_factor)
    sample_freq = compute_fft(sample_windowed, config.zero_pad_factor)

    return extract_optical_properties(
        ref_data, sample_data, ref_freq, sample_freq, config, progress_callback
    )


def _average_sample_fft(
    samples: dict[tuple[int, int], THzTimeDomainData],
    target_temp: int,
    window_type: str,
    zero_pad_factor: int,
) -> tuple[THzTimeDomainData, THzFrequencyDomainData]:
    """Average FFTs of all replicates at a given temperature for use as baseline."""
    reps = [(t, r) for (t, r) in samples.keys() if t == target_temp]
    if not reps:
        raise ValueError(f"No samples found at {target_temp}°C for baseline.")

    spectra = []
    td_base = None
    for key in sorted(reps):
        td = samples[key]
        if td_base is None:
            td_base = td
        windowed = apply_window(td, window_type)
        freq = compute_fft(windowed, zero_pad_factor)
        spectra.append(freq.spectrum)

    avg_spectrum = np.mean(spectra, axis=0)
    avg_freq = THzFrequencyDomainData(
        freq_hz=compute_fft(apply_window(td_base, window_type), zero_pad_factor).freq_hz,
        spectrum=avg_spectrum,
    )
    return td_base, avg_freq


def process_temperature_series(
    ref_data: THzTimeDomainData,
    samples: dict[tuple[int, int], THzTimeDomainData],
    config: ExtractionConfig,
    progress_callback: Callable | None = None,
    analysis_method: str = "method2",
) -> dict[tuple[int, int], OpticalProperties]:
    """Batch process all temperature/replicate combinations.

    Args:
        analysis_method:
            "method2" — H = E_sam(T)/E_ref(20°C) with air path correction (absolute)
            "method3" — H = E_sam(T)/E_sam(T_base) differential analysis (relative)
    """
    results: dict[tuple[int, int], OpticalProperties] = {}
    total = len(samples)

    if analysis_method == "method3":
        # Method 3: differential — use averaged 20°C sample as baseline
        base_temp = min(set(t for t, _ in samples.keys()))
        base_td, base_freq = _average_sample_fft(
            samples, base_temp, config.window_type, config.zero_pad_factor
        )

        for i, ((temp, rep), sample_data) in enumerate(sorted(samples.items())):
            sample_windowed = apply_window(sample_data, config.window_type)
            sample_freq = compute_fft(sample_windowed, config.zero_pad_factor)

            # Use base sample as reference instead of air reference
            props = extract_optical_properties(
                base_td, sample_data, base_freq, sample_freq, config
            )
            results[(temp, rep)] = props

            if progress_callback:
                progress_callback(i + 1, total)
    else:
        # Method 2: standard — use air reference with air path correction
        ref_windowed = apply_window(ref_data, config.window_type)
        ref_freq = compute_fft(ref_windowed, config.zero_pad_factor)

        for i, ((temp, rep), sample_data) in enumerate(sorted(samples.items())):
            sample_windowed = apply_window(sample_data, config.window_type)
            sample_freq = compute_fft(sample_windowed, config.zero_pad_factor)

            props = extract_optical_properties(
                ref_data, sample_data, ref_freq, sample_freq, config
            )
            results[(temp, rep)] = props

            if progress_callback:
                progress_callback(i + 1, total)

    return results


def compute_temperature_averages(
    results: dict[tuple[int, int], OpticalProperties],
) -> dict[int, OpticalProperties]:
    """Average the replicates at each temperature.

    Returns dict mapping temperature -> averaged OpticalProperties
    with standard deviations stored in n_std, kappa_std, alpha_std.
    """
    # Group by temperature
    temp_groups: dict[int, list[OpticalProperties]] = {}
    for (temp, _rep), props in results.items():
        temp_groups.setdefault(temp, []).append(props)

    averages: dict[int, OpticalProperties] = {}

    for temp, props_list in sorted(temp_groups.items()):
        # Stack arrays from all replicates
        n_stack = np.array([p.n for p in props_list])
        kappa_stack = np.array([p.kappa for p in props_list])
        alpha_stack = np.array([p.alpha for p in props_list])

        avg_props = OpticalProperties(
            freq_hz=props_list[0].freq_hz.copy(),
            n=np.mean(n_stack, axis=0),
            kappa=np.mean(kappa_stack, axis=0),
            alpha=np.mean(alpha_stack, axis=0),
            thickness_mm=props_list[0].thickness_mm,
            temperature_c=temp,
            n_std=np.std(n_stack, axis=0),
            kappa_std=np.std(kappa_stack, axis=0),
            alpha_std=np.std(alpha_stack, axis=0),
        )
        averages[temp] = avg_props

    return averages
