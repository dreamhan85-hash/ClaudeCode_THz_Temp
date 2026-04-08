"""Shared test fixtures for THz-TDS analysis.

Provides synthetic THz signal generation with known optical properties
for validating extraction algorithms.
"""
from __future__ import annotations

import numpy as np
import pytest
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from thztds.types import THzTimeDomainData, THzFrequencyDomainData, ExtractionConfig
from thztds.constants import C0, PI
from thztds.signal import compute_fft, apply_window


def generate_synthetic_thz_pulse(
    n_points: int = 3000,
    dt_ps: float = 0.05,
    pulse_center_ps: float = 10.0,
    pulse_width_ps: float = 0.3,
    amplitude: float = 1.0,
    noise_level: float = 0.0,
) -> THzTimeDomainData:
    """Generate a synthetic THz pulse (Gaussian derivative)."""
    time_ps = np.arange(n_points) * dt_ps
    t0 = pulse_center_ps
    sigma = pulse_width_ps

    # Single-cycle THz pulse: negative derivative of Gaussian
    signal = -amplitude * (time_ps - t0) / sigma**2 * np.exp(
        -((time_ps - t0) ** 2) / (2 * sigma**2)
    )

    if noise_level > 0:
        rng = np.random.default_rng(42)
        signal += rng.normal(0, noise_level, n_points)

    return THzTimeDomainData(time_ps=time_ps, signal=signal, metadata={})


def generate_sample_pulse(
    ref_pulse: THzTimeDomainData,
    n_material: float,
    kappa_material: float,
    thickness_m: float,
    zero_pad_factor: int = 2,
) -> THzTimeDomainData:
    """Generate a sample pulse by applying known optical properties to reference.

    Applies H_theory(f) = t_coeff * exp(-j*(n_tilde - 1)*k0*d) to the reference
    spectrum, then inverse FFTs back to time domain.
    """
    # FFT reference
    dt_ps = ref_pulse.time_ps[1] - ref_pulse.time_ps[0]
    dt_s = dt_ps * 1e-12
    n_orig = len(ref_pulse.signal)
    n_padded = int(2 ** np.ceil(np.log2(n_orig * zero_pad_factor)))

    ref_spectrum = np.fft.fft(ref_pulse.signal, n=n_padded)
    freq = np.fft.fftfreq(n_padded, d=dt_s)

    # Build transfer function
    n_tilde = n_material - 1j * kappa_material
    omega = 2.0 * PI * freq
    k0 = omega / C0

    # Fresnel coefficients (normal incidence, air-sample-air)
    r = (n_tilde - 1.0) / (n_tilde + 1.0)
    t_coeff = 1.0 - r**2

    # Propagation relative to air
    propagation = np.exp(-1j * (n_tilde - 1.0) * k0 * thickness_m)

    H_theory = t_coeff * propagation

    # Handle DC (freq=0)
    H_theory[0] = np.abs(t_coeff)

    # Apply transfer function
    sample_spectrum = ref_spectrum * H_theory

    # Inverse FFT and truncate
    sample_signal = np.real(np.fft.ifft(sample_spectrum))[:n_orig]

    return THzTimeDomainData(
        time_ps=ref_pulse.time_ps.copy(),
        signal=sample_signal,
        metadata={"temperature_c": 20, "replicate": 1},
    )


@pytest.fixture
def reference_pulse() -> THzTimeDomainData:
    """Standard reference THz pulse."""
    return generate_synthetic_thz_pulse(
        n_points=3000, dt_ps=0.05, pulse_center_ps=10.0,
        pulse_width_ps=0.3, amplitude=1.0,
    )


@pytest.fixture
def noisy_reference_pulse() -> THzTimeDomainData:
    """Reference pulse with noise for noise floor testing."""
    return generate_synthetic_thz_pulse(
        n_points=3000, dt_ps=0.05, pulse_center_ps=10.0,
        pulse_width_ps=0.3, amplitude=1.0, noise_level=1e-4,
    )


@pytest.fixture
def pe_sample_pulse(reference_pulse) -> THzTimeDomainData:
    """PE20 sample pulse: n~1.26, low kappa, 20 um thick."""
    return generate_sample_pulse(
        reference_pulse,
        n_material=1.26,
        kappa_material=0.005,
        thickness_m=20e-6,
    )


@pytest.fixture
def silicon_sample_pulse(reference_pulse) -> THzTimeDomainData:
    """Silicon sample pulse: n=3.42, kappa~0, 500 um thick."""
    return generate_sample_pulse(
        reference_pulse,
        n_material=3.42,
        kappa_material=0.001,
        thickness_m=500e-6,
    )


@pytest.fixture
def default_config() -> ExtractionConfig:
    """Default extraction configuration for testing."""
    return ExtractionConfig(
        thickness_mm=0.02,
        freq_min_thz=0.3,
        freq_max_thz=2.0,
        n_fp_echoes=0,
        window_type="rectangular",
        zero_pad_factor=2,
        n_initial_guess=1.3,
        kappa_initial_guess=0.01,
        thin_film=True,
        apply_air_correction=False,
    )


@pytest.fixture
def silicon_config() -> ExtractionConfig:
    """Config for silicon sample testing."""
    return ExtractionConfig(
        thickness_mm=0.5,
        freq_min_thz=0.3,
        freq_max_thz=2.0,
        n_fp_echoes=0,
        window_type="rectangular",
        zero_pad_factor=2,
        n_initial_guess=3.4,
        kappa_initial_guess=0.001,
        thin_film=False,
        apply_air_correction=False,
    )
