"""THz-TDS optical property extraction library."""
__version__ = "0.2.0"

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
from .noise import detect_noise_floor
from .phase_correction import correct_phase_offset
from .filtering import svmaf_filter, svmaf_filter_properties
from .thickness import optimize_thickness
from .error_estimation import compute_confidence_intervals, compute_alpha_max
from .optical_properties import (
    process_single_measurement,
    process_temperature_series,
    compute_temperature_averages,
)
