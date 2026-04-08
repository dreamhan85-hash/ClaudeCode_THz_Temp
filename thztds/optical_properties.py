"""High-level orchestration: end-to-end extraction pipeline."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from .types import (
    THzTimeDomainData,
    THzFrequencyDomainData,
    OpticalProperties,
    ExtractionConfig,
    NoiseAnalysis,
    SvmafConfig,
    ThicknessOptConfig,
    ThicknessResult,
)
from .signal import apply_window, compute_fft
from .optimization import extract_optical_properties
from .noise import detect_noise_floor
from .phase_correction import correct_phase_offset
from .filtering import svmaf_filter_properties
from .thickness import optimize_thickness
from .error_estimation import compute_confidence_intervals, compute_alpha_max


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


def process_temperature_series_matched_ref(
    references: dict[int, THzTimeDomainData],
    samples: dict[tuple[int, int], THzTimeDomainData],
    config: ExtractionConfig,
    progress_callback: Callable | None = None,
) -> dict[tuple[int, int], OpticalProperties]:
    """Batch process using per-temperature matched references.

    Each sample at temperature T is divided by Ref_T.
    No air temperature correction needed (same-temperature measurement).

    Args:
        references: dict mapping temperature -> reference THzTimeDomainData
        samples: dict mapping (temperature, replicate) -> THzTimeDomainData
        config: Extraction configuration (apply_air_correction ignored).
    """
    results: dict[tuple[int, int], OpticalProperties] = {}
    total = len(samples)

    # Pre-compute reference FFTs
    ref_cache: dict[int, tuple[THzTimeDomainData, THzFrequencyDomainData]] = {}
    for temp, ref_td in references.items():
        ref_windowed = apply_window(ref_td, config.window_type)
        ref_freq = compute_fft(ref_windowed, config.zero_pad_factor)
        ref_cache[temp] = (ref_td, ref_freq)

    # Override air correction (same temp ref/sample → no correction needed)
    cfg_no_air = ExtractionConfig(
        thickness_mm=config.thickness_mm,
        freq_min_thz=config.freq_min_thz,
        freq_max_thz=config.freq_max_thz,
        n_fp_echoes=config.n_fp_echoes,
        window_type=config.window_type,
        zero_pad_factor=config.zero_pad_factor,
        n_initial_guess=config.n_initial_guess,
        kappa_initial_guess=config.kappa_initial_guess,
        thin_film=config.thin_film,
        ref_temperature_c=config.ref_temperature_c,
        chamber_length_cm=config.chamber_length_cm,
        total_path_cm=config.total_path_cm,
        apply_air_correction=False,
    )

    for i, ((temp, rep), sample_data) in enumerate(sorted(samples.items())):
        if temp not in ref_cache:
            continue

        ref_td, ref_freq = ref_cache[temp]
        sample_windowed = apply_window(sample_data, config.window_type)
        sample_freq = compute_fft(sample_windowed, cfg_no_air.zero_pad_factor)

        props = extract_optical_properties(
            ref_td, sample_data, ref_freq, sample_freq, cfg_no_air
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
