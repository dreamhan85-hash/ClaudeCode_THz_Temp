"""Tests for noise floor detection module."""
from __future__ import annotations

import numpy as np
import pytest

from thztds.noise import estimate_noise_floor, compute_dynamic_range, detect_noise_floor
from thztds.signal import compute_fft
from thztds.types import THzFrequencyDomainData


class TestEstimateNoiseFloor:
    def test_returns_positive_value(self, noisy_reference_pulse):
        ref_freq = compute_fft(noisy_reference_pulse, zero_pad_factor=2)
        noise = estimate_noise_floor(ref_freq)
        assert noise > 0

    def test_noise_less_than_peak(self, noisy_reference_pulse):
        ref_freq = compute_fft(noisy_reference_pulse, zero_pad_factor=2)
        noise = estimate_noise_floor(ref_freq)
        assert noise < np.max(ref_freq.amplitude)

    def test_clean_signal_lower_noise(self, reference_pulse, noisy_reference_pulse):
        clean_freq = compute_fft(reference_pulse, zero_pad_factor=2)
        noisy_freq = compute_fft(noisy_reference_pulse, zero_pad_factor=2)
        clean_noise = estimate_noise_floor(clean_freq)
        noisy_noise = estimate_noise_floor(noisy_freq)
        assert clean_noise < noisy_noise


class TestComputeDynamicRange:
    def test_dr_shape_matches_freq(self, reference_pulse):
        ref_freq = compute_fft(reference_pulse, zero_pad_factor=2)
        noise = estimate_noise_floor(ref_freq)
        dr = compute_dynamic_range(ref_freq, noise)
        assert dr.shape == ref_freq.freq_hz.shape

    def test_dr_positive_at_signal_band(self, reference_pulse):
        ref_freq = compute_fft(reference_pulse, zero_pad_factor=2)
        noise = estimate_noise_floor(ref_freq)
        dr = compute_dynamic_range(ref_freq, noise)
        # At least some frequencies should have positive DR
        assert np.any(dr > 0)

    def test_dr_zero_at_noise_level(self, reference_pulse):
        ref_freq = compute_fft(reference_pulse, zero_pad_factor=2)
        noise = estimate_noise_floor(ref_freq)
        dr = compute_dynamic_range(ref_freq, noise)
        # DR at noise floor should be ~0 dB
        tail = dr[-10:]
        assert np.all(tail < 10)  # Near noise floor


class TestDetectNoiseFloor:
    def test_returns_noise_analysis(self, reference_pulse):
        ref_freq = compute_fft(reference_pulse, zero_pad_factor=2)
        result = detect_noise_floor(ref_freq)
        assert result.noise_floor > 0
        assert result.noise_start_thz > 0
        assert result.dynamic_range_db.shape == ref_freq.freq_hz.shape
        assert result.valid_freq_mask.shape == ref_freq.freq_hz.shape

    def test_valid_mask_excludes_noise_region(self, noisy_reference_pulse):
        ref_freq = compute_fft(noisy_reference_pulse, zero_pad_factor=2)
        result = detect_noise_floor(ref_freq, dr_threshold_db=10.0)
        # Should have some valid and some invalid frequencies
        assert np.any(result.valid_freq_mask)
        # Not all frequencies should be valid (noise region excluded)
        assert not np.all(result.valid_freq_mask)

    def test_noise_start_within_spectrum(self, reference_pulse):
        ref_freq = compute_fft(reference_pulse, zero_pad_factor=2)
        result = detect_noise_floor(ref_freq)
        max_freq_thz = ref_freq.freq_hz[-1] / 1e12
        assert 0 < result.noise_start_thz <= max_freq_thz

    def test_higher_threshold_narrows_valid_range(self, noisy_reference_pulse):
        ref_freq = compute_fft(noisy_reference_pulse, zero_pad_factor=2)
        result_low = detect_noise_floor(ref_freq, dr_threshold_db=5.0)
        result_high = detect_noise_floor(ref_freq, dr_threshold_db=20.0)
        # Higher threshold should have fewer valid points
        assert np.sum(result_high.valid_freq_mask) <= np.sum(result_low.valid_freq_mask)

    def test_sanity_physics_snr_positive(self, reference_pulse):
        """Physics sanity: SNR should be positive everywhere."""
        ref_freq = compute_fft(reference_pulse, zero_pad_factor=2)
        result = detect_noise_floor(ref_freq)
        assert np.all(result.snr_spectrum >= 0)
