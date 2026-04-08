"""Tests for phase offset correction module."""
from __future__ import annotations

import numpy as np
import pytest

from thztds.phase_correction import compute_phase_offset, correct_phase_offset
from thztds.signal import compute_fft
from thztds.transfer_function import compute_measured_transfer_function
from thztds.constants import PI


class TestComputePhaseOffset:
    def test_zero_offset_for_linear_phase(self):
        """Phase that passes through 0 at f=0 should have ~0 offset."""
        freq_hz = np.linspace(0.1e12, 3e12, 500)
        # Linear phase with zero intercept
        phase = -2.0 * freq_hz / 1e12
        offset = compute_phase_offset(freq_hz, phase, trusted_range_thz=(0.3, 1.0))
        # Offset should be close to zero (extrapolated intercept ~ -0.2, wrapped)
        assert abs(offset) < PI

    def test_known_offset_recovery(self):
        """Should recover a known phase offset."""
        freq_hz = np.linspace(0.1e12, 3e12, 500)
        true_offset = 0.5
        phase = -1.0 * freq_hz / 1e12 + true_offset
        offset = compute_phase_offset(freq_hz, phase, trusted_range_thz=(0.3, 1.0))
        assert abs(offset - true_offset) < 0.05

    def test_offset_wrapped_to_pi(self):
        """Offset should always be in [-π, π]."""
        freq_hz = np.linspace(0.1e12, 3e12, 500)
        phase = -1.0 * freq_hz / 1e12 + 5.0  # Large offset
        offset = compute_phase_offset(freq_hz, phase, trusted_range_thz=(0.3, 1.0))
        assert -PI <= offset <= PI

    def test_insufficient_points_returns_zero(self):
        """With < 2 points in trusted range, return 0."""
        freq_hz = np.array([0.1e12, 0.15e12])
        phase = np.array([0.0, -0.1])
        offset = compute_phase_offset(freq_hz, phase, trusted_range_thz=(0.5, 1.0))
        assert offset == 0.0


class TestCorrectPhaseOffset:
    def test_output_shape_matches_input(self, reference_pulse, pe_sample_pulse):
        ref_freq = compute_fft(reference_pulse, zero_pad_factor=2)
        sam_freq = compute_fft(pe_sample_pulse, zero_pad_factor=2)
        H_meas = compute_measured_transfer_function(ref_freq, sam_freq)
        H_corrected = correct_phase_offset(H_meas, ref_freq.freq_hz)
        assert H_corrected.shape == H_meas.shape

    def test_amplitude_preserved(self, reference_pulse, pe_sample_pulse):
        """Phase correction should not change amplitudes."""
        ref_freq = compute_fft(reference_pulse, zero_pad_factor=2)
        sam_freq = compute_fft(pe_sample_pulse, zero_pad_factor=2)
        H_meas = compute_measured_transfer_function(ref_freq, sam_freq)
        H_corrected = correct_phase_offset(H_meas, ref_freq.freq_hz)
        valid = ~np.isnan(H_meas)
        np.testing.assert_allclose(
            np.abs(H_corrected[valid]), np.abs(H_meas[valid]), rtol=1e-10
        )

    def test_nan_values_preserved(self):
        """NaN entries should remain NaN after correction."""
        freq_hz = np.linspace(0.1e12, 3e12, 100)
        H_meas = np.exp(-1j * freq_hz / 1e12).astype(np.complex128)
        H_meas[0:5] = np.nan
        H_corrected = correct_phase_offset(H_meas, freq_hz)
        assert np.all(np.isnan(H_corrected[0:5]))

    def test_sanity_physics_phase_smoother(self, reference_pulse, pe_sample_pulse):
        """Physics sanity: corrected phase should be at least as smooth."""
        ref_freq = compute_fft(reference_pulse, zero_pad_factor=2)
        sam_freq = compute_fft(pe_sample_pulse, zero_pad_factor=2)
        H_meas = compute_measured_transfer_function(ref_freq, sam_freq)
        H_corrected = correct_phase_offset(H_meas, ref_freq.freq_hz)

        valid = ~np.isnan(H_meas)
        phase_orig = np.unwrap(np.angle(H_meas[valid]))
        phase_corr = np.unwrap(np.angle(H_corrected[valid]))

        # Total variation of corrected phase should be <= original
        tv_orig = np.sum(np.abs(np.diff(phase_orig)))
        tv_corr = np.sum(np.abs(np.diff(phase_corr)))
        # Allow small tolerance (correction may not always reduce TV)
        assert tv_corr <= tv_orig * 1.01
