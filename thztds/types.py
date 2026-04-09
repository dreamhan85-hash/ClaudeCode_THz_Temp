"""Data structures for THz-TDS analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from numpy.typing import NDArray


@dataclass
class THzTimeDomainData:
    """Raw time-domain THz pulse."""
    time_ps: NDArray[np.float64]
    signal: NDArray[np.float64]
    metadata: dict = field(default_factory=dict)


@dataclass
class THzFrequencyDomainData:
    """Frequency-domain representation after FFT."""
    freq_hz: NDArray[np.float64]
    spectrum: NDArray[np.complex128]

    @property
    def freq_thz(self) -> NDArray[np.float64]:
        return self.freq_hz / 1e12

    @property
    def amplitude(self) -> NDArray[np.float64]:
        return np.abs(self.spectrum)

    @property
    def phase(self) -> NDArray[np.float64]:
        return np.unwrap(np.angle(self.spectrum))


@dataclass
class OpticalProperties:
    """Extracted material properties at each frequency."""
    freq_hz: NDArray[np.float64]
    n: NDArray[np.float64]
    kappa: NDArray[np.float64]
    alpha: NDArray[np.float64]  # Absorption coefficient [1/cm]
    thickness_mm: float
    temperature_c: Optional[float] = None
    replicate: Optional[int] = None
    n_std: Optional[NDArray[np.float64]] = None
    kappa_std: Optional[NDArray[np.float64]] = None
    alpha_std: Optional[NDArray[np.float64]] = None

    @property
    def freq_thz(self) -> NDArray[np.float64]:
        return self.freq_hz / 1e12


@dataclass
class NoiseAnalysis:
    """Results from noise floor detection."""
    noise_floor: float
    noise_start_thz: float
    dynamic_range_db: NDArray[np.float64]
    snr_spectrum: NDArray[np.float64]
    valid_freq_mask: NDArray[np.bool_]


@dataclass
class SvmafConfig:
    """Configuration for Spatially Variant Moving Average Filter."""
    max_window_size: int = 15
    confidence_sigma: float = 2.0


@dataclass
class ThicknessOptConfig:
    """Configuration for thickness optimization."""
    center_um: float = 20.0
    interval_um: float = 5.0
    step_um: float = 0.5
    method: str = "quasi_space"  # "quasi_space" or "total_variation"


@dataclass
class ThicknessResult:
    """Results from thickness optimization."""
    optimal_thickness_um: float
    all_thicknesses_um: NDArray[np.float64]
    merit_values: NDArray[np.float64]
    method: str


@dataclass
class ExtractionConfig:
    """Parameters controlling the extraction algorithm."""
    thickness_mm: float = 1.0
    freq_min_thz: float = 0.2
    freq_max_thz: float = 2.5
    n_fp_echoes: int = 0
    window_type: str = "hann"
    zero_pad_factor: int = 2
    n_initial_guess: float = 1.5
    kappa_initial_guess: float = 0.01
    optimize_thickness: bool = False
    thin_film: bool = True  # Use thin-film approximation (no Fresnel, valid for d << λ)
    # Air temperature correction
    ref_temperature_c: float = 20.0
    chamber_length_cm: float = 1.0
    total_path_cm: float = 30.0
    apply_air_correction: bool = True
