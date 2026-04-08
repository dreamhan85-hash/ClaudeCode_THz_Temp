"""Tests for SVMAF filtering module."""
from __future__ import annotations

import numpy as np
import pytest

from thztds.filtering import (
    svmaf_filter,
    compute_confidence_from_std,
    svmaf_filter_properties,
)
from thztds.types import SvmafConfig


class TestSvmafFilter:
    def test_output_shape_matches_input(self):
        values = np.array([1.0, 1.1, 1.05, 1.08, 1.02, 1.06, 1.03])
        confidence = np.full_like(values, 0.1)
        result = svmaf_filter(values, confidence)
        assert result.shape == values.shape

    def test_flat_signal_unchanged(self):
        """A perfectly flat signal should remain flat after filtering."""
        values = np.ones(50) * 1.5
        confidence = np.full(50, 0.1)
        result = svmaf_filter(values, confidence)
        np.testing.assert_allclose(result, values, atol=1e-10)

    def test_filtered_within_confidence(self):
        """Filtered values must stay within confidence interval of originals."""
        rng = np.random.default_rng(42)
        values = 1.5 + 0.02 * rng.normal(size=100)
        confidence = np.full(100, 0.05)
        result = svmaf_filter(values, confidence)
        assert np.all(np.abs(result - values) <= confidence + 1e-10)

    def test_smoothing_reduces_variation(self):
        """Filtering should reduce total variation of noisy signal."""
        rng = np.random.default_rng(42)
        values = 1.5 + 0.03 * rng.normal(size=100)
        confidence = np.full(100, 0.05)
        result = svmaf_filter(values, confidence)

        tv_orig = np.sum(np.abs(np.diff(values)))
        tv_filt = np.sum(np.abs(np.diff(result)))
        assert tv_filt <= tv_orig

    def test_sharp_feature_preserved(self):
        """A sharp absorption peak should be preserved (narrow window near peak)."""
        values = np.ones(100) * 1.5
        # Add a sharp peak
        values[48:52] = 2.0
        confidence = np.full(100, 0.1)
        result = svmaf_filter(values, confidence)

        # Peak region should still be elevated relative to baseline
        assert np.mean(result[48:52]) > np.mean(result[0:10]) + 0.3

    def test_empty_array(self):
        values = np.array([])
        confidence = np.array([])
        result = svmaf_filter(values, confidence)
        assert len(result) == 0

    def test_single_point(self):
        values = np.array([1.5])
        confidence = np.array([0.1])
        result = svmaf_filter(values, confidence)
        assert result[0] == 1.5

    def test_custom_config(self):
        """Custom max_window_size should affect smoothing."""
        rng = np.random.default_rng(42)
        values = 1.5 + 0.02 * rng.normal(size=100)
        confidence = np.full(100, 0.05)

        narrow = svmaf_filter(values, confidence, SvmafConfig(max_window_size=3))
        wide = svmaf_filter(values, confidence, SvmafConfig(max_window_size=31))

        tv_narrow = np.sum(np.abs(np.diff(narrow)))
        tv_wide = np.sum(np.abs(np.diff(wide)))
        # Wider window should smooth more
        assert tv_wide <= tv_narrow


class TestComputeConfidenceFromStd:
    def test_default_2sigma(self):
        std = np.array([0.01, 0.02, 0.03])
        ci = compute_confidence_from_std(std)
        np.testing.assert_allclose(ci, std * 2.0)

    def test_custom_sigma(self):
        std = np.array([0.01, 0.02])
        ci = compute_confidence_from_std(std, sigma=3.0)
        np.testing.assert_allclose(ci, std * 3.0)


class TestSvmafFilterProperties:
    def test_with_std(self):
        rng = np.random.default_rng(42)
        values = 1.5 + 0.02 * rng.normal(size=50)
        std = np.full(50, 0.01)
        result = svmaf_filter_properties(values, std=std)
        assert result.shape == values.shape

    def test_without_std_fallback(self):
        """Should work with fallback confidence when std is None."""
        rng = np.random.default_rng(42)
        values = 1.5 + 0.03 * rng.normal(size=50)
        result = svmaf_filter_properties(values, std=None)
        assert result.shape == values.shape

    def test_sanity_physics_filtered_mean_close(self):
        """Physics sanity: mean of filtered values should be close to original mean."""
        rng = np.random.default_rng(42)
        values = 1.26 + 0.02 * rng.normal(size=200)
        std = np.full(200, 0.015)
        result = svmaf_filter_properties(values, std=std)
        assert abs(np.mean(result) - np.mean(values)) < 0.01
