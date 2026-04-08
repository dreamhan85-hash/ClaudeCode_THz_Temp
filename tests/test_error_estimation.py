"""Tests for error estimation module."""
from __future__ import annotations

import numpy as np
import pytest

from thztds.error_estimation import (
    compute_alpha_max,
    compute_noise_propagated_uncertainty,
    compute_thickness_uncertainty,
    compute_confidence_intervals,
)
from thztds.types import OpticalProperties, NoiseAnalysis
from thztds.signal import compute_fft
from thztds.noise import detect_noise_floor


def _make_noise_analysis(n_freq: int = 200) -> NoiseAnalysis:
    """Helper to create a synthetic NoiseAnalysis."""
    freq_hz = np.linspace(0.1e12, 3e12, n_freq)
    # Simulate dynamic range: high in center, drops at edges
    dr_db = 40.0 * np.exp(-((freq_hz / 1e12 - 1.0) ** 2) / 2.0)
    snr = 10.0 ** (dr_db / 10.0)
    valid_mask = dr_db > 10.0
    return NoiseAnalysis(
        noise_floor=1e-6,
        noise_start_thz=2.5,
        dynamic_range_db=dr_db,
        snr_spectrum=snr,
        valid_freq_mask=valid_mask,
    )


def _make_optical_properties(n_freq: int = 200) -> OpticalProperties:
    """Helper to create synthetic OpticalProperties."""
    freq_hz = np.linspace(0.3e12, 2e12, n_freq)
    return OpticalProperties(
        freq_hz=freq_hz,
        n=np.ones(n_freq) * 1.26,
        kappa=np.ones(n_freq) * 0.005,
        alpha=np.ones(n_freq) * 5.0,
        thickness_mm=0.02,
        n_std=np.ones(n_freq) * 0.02,
        kappa_std=np.ones(n_freq) * 0.001,
        alpha_std=np.ones(n_freq) * 0.5,
    )


class TestComputeAlphaMax:
    def test_positive_values(self):
        na = _make_noise_analysis()
        freq_hz = np.linspace(0.1e12, 3e12, len(na.dynamic_range_db))
        alpha_max = compute_alpha_max(na, thickness_m=20e-6, freq_hz=freq_hz)
        assert np.all(alpha_max >= 0)

    def test_higher_dr_means_higher_alpha_max(self):
        """Higher dynamic range → can measure higher absorption."""
        n = 100
        freq_hz = np.linspace(0.3e12, 2e12, n)
        na_low = NoiseAnalysis(
            noise_floor=1e-4, noise_start_thz=2.0,
            dynamic_range_db=np.full(n, 20.0),
            snr_spectrum=np.full(n, 100.0),
            valid_freq_mask=np.ones(n, dtype=bool),
        )
        na_high = NoiseAnalysis(
            noise_floor=1e-6, noise_start_thz=2.0,
            dynamic_range_db=np.full(n, 60.0),
            snr_spectrum=np.full(n, 1e6),
            valid_freq_mask=np.ones(n, dtype=bool),
        )
        a_low = compute_alpha_max(na_low, 20e-6, freq_hz)
        a_high = compute_alpha_max(na_high, 20e-6, freq_hz)
        assert np.mean(a_high) > np.mean(a_low)

    def test_zero_thickness_returns_inf(self):
        na = _make_noise_analysis(50)
        freq_hz = np.linspace(0.3e12, 2e12, 50)
        result = compute_alpha_max(na, thickness_m=0.0, freq_hz=freq_hz)
        assert np.all(np.isinf(result))


class TestNoiseUncertainty:
    def test_output_shapes(self):
        na = _make_noise_analysis(100)
        freq_hz = np.linspace(0.3e12, 2e12, 100)
        dn, da = compute_noise_propagated_uncertainty(na, freq_hz, 20e-6)
        assert dn.shape == freq_hz.shape
        assert da.shape == freq_hz.shape

    def test_sanity_physics_positive_uncertainty(self):
        """Physics sanity: uncertainties should be positive."""
        na = _make_noise_analysis(100)
        freq_hz = np.linspace(0.3e12, 2e12, 100)
        dn, da = compute_noise_propagated_uncertainty(na, freq_hz, 20e-6)
        assert np.all(dn >= 0)
        assert np.all(da >= 0)

    def test_higher_snr_lower_uncertainty(self):
        n = 50
        freq_hz = np.linspace(0.3e12, 2e12, n)
        na_low_snr = NoiseAnalysis(
            noise_floor=1e-4, noise_start_thz=2.0,
            dynamic_range_db=np.full(n, 20.0),
            snr_spectrum=np.full(n, 10.0),
            valid_freq_mask=np.ones(n, dtype=bool),
        )
        na_high_snr = NoiseAnalysis(
            noise_floor=1e-6, noise_start_thz=2.0,
            dynamic_range_db=np.full(n, 60.0),
            snr_spectrum=np.full(n, 1e4),
            valid_freq_mask=np.ones(n, dtype=bool),
        )
        dn_low, _ = compute_noise_propagated_uncertainty(na_low_snr, freq_hz, 20e-6)
        dn_high, _ = compute_noise_propagated_uncertainty(na_high_snr, freq_hz, 20e-6)
        assert np.mean(dn_high) < np.mean(dn_low)

    def test_zero_thickness(self):
        na = _make_noise_analysis(50)
        freq_hz = np.linspace(0.3e12, 2e12, 50)
        dn, da = compute_noise_propagated_uncertainty(na, freq_hz, 0.0)
        assert np.all(dn == 0)
        assert np.all(da == 0)


class TestThicknessUncertainty:
    def test_basic(self):
        n = np.ones(50) * 1.26
        freq_hz = np.linspace(0.3e12, 2e12, 50)
        dn = compute_thickness_uncertainty(n, freq_hz, 20e-6, 0.5e-6)
        assert dn.shape == n.shape
        assert np.all(dn >= 0)
        # delta_n = |n-1| * step/d = 0.26 * 0.5/20 = 0.0065
        np.testing.assert_allclose(dn, 0.26 * 0.5 / 20.0, atol=1e-6)

    def test_n_equals_one_zero_uncertainty(self):
        """If n=1 (air), thickness uncertainty contributes nothing."""
        n = np.ones(20)
        freq_hz = np.linspace(0.3e12, 2e12, 20)
        dn = compute_thickness_uncertainty(n, freq_hz, 20e-6, 1e-6)
        np.testing.assert_allclose(dn, 0.0, atol=1e-15)


class TestComputeConfidenceIntervals:
    def test_with_all_sources(self):
        props = _make_optical_properties(100)
        na = _make_noise_analysis(100)
        dn, dk, da = compute_confidence_intervals(
            props, noise_analysis=na, thickness_step_um=0.5, sigma=2.0
        )
        assert dn.shape == props.freq_hz.shape
        assert dk.shape == props.freq_hz.shape
        assert da.shape == props.freq_hz.shape
        assert np.all(dn >= 0)
        assert np.all(dk >= 0)
        assert np.all(da >= 0)

    def test_replicate_only(self):
        """With only replicate stats, CI should be 2*std."""
        props = _make_optical_properties(50)
        dn, dk, da = compute_confidence_intervals(props, sigma=2.0)
        # Should be ~2*std when no other sources
        np.testing.assert_allclose(dn, 2.0 * props.n_std, atol=1e-10)
        np.testing.assert_allclose(dk, 2.0 * props.kappa_std, atol=1e-10)

    def test_no_uncertainty_sources(self):
        """Without any uncertainty data, CI should be zero."""
        props = OpticalProperties(
            freq_hz=np.linspace(0.3e12, 2e12, 30),
            n=np.ones(30) * 1.5,
            kappa=np.ones(30) * 0.01,
            alpha=np.ones(30) * 5.0,
            thickness_mm=0.5,
        )
        dn, dk, da = compute_confidence_intervals(props)
        np.testing.assert_allclose(dn, 0.0, atol=1e-15)
        np.testing.assert_allclose(dk, 0.0, atol=1e-15)
        np.testing.assert_allclose(da, 0.0, atol=1e-15)

    def test_sanity_physics_higher_sigma_wider_ci(self):
        """Physics sanity: 3-sigma CI wider than 2-sigma."""
        props = _make_optical_properties(50)
        dn_2, _, _ = compute_confidence_intervals(props, sigma=2.0)
        dn_3, _, _ = compute_confidence_intervals(props, sigma=3.0)
        assert np.all(dn_3 >= dn_2)
