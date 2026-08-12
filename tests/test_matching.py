"""Tests for src/matching.py. The real tests are the two synthetic-data recovery checks --
feeding data generated from a known Cobb-Douglas matching function with a known degree of
returns to scale and confirming the fit recovers it, and confirming the Wald test correctly
distinguishes constant returns from a genuine departure from it. The same "recover a known
answer, don't just check it runs" standard as dmp.py's Chen Table 1 test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.matching import fit_matching_function


def _synthetic_window(a: float, b_u: float, b_v: float, n: int, seed: int, noise_sd: float = 0.0):
    rng = np.random.default_rng(seed)
    log_u = rng.uniform(2.0, 5.0, size=n)
    log_v = rng.uniform(2.0, 5.0, size=n)
    noise = rng.normal(0.0, noise_sd, size=n) if noise_sd else 0.0
    log_m = np.log(a) + b_u * log_u + b_v * log_v + noise
    return pd.DataFrame({"u": np.exp(log_u), "v": np.exp(log_v), "m": np.exp(log_m)})


def test_recovers_known_constant_returns_parameters_from_noiseless_data():
    window = _synthetic_window(a=0.35, b_u=0.6, b_v=0.4, n=50, seed=1)
    fit = fit_matching_function(window)
    assert fit.b_u == pytest.approx(0.6, abs=1e-6)
    assert fit.b_v == pytest.approx(0.4, abs=1e-6)
    assert fit.a_constrained == pytest.approx(0.35, abs=1e-6)
    assert fit.phi_constrained == pytest.approx(0.6, abs=1e-6)


def test_does_not_reject_constant_returns_when_true_returns_are_constant():
    window = _synthetic_window(a=0.4, b_u=0.55, b_v=0.45, n=200, seed=2, noise_sd=0.01)
    fit = fit_matching_function(window)
    assert fit.returns_to_scale == pytest.approx(1.0, abs=0.05)
    assert not fit.crs_rejected


def test_rejects_constant_returns_when_true_returns_are_not_constant():
    """b_u + b_v = 1.3 here -- genuine increasing returns, not noise. A well-behaved Wald test
    at this sample size and noise level should catch it, not wave it through as CRS."""
    window = _synthetic_window(a=0.4, b_u=0.8, b_v=0.5, n=200, seed=3, noise_sd=0.01)
    fit = fit_matching_function(window)
    assert fit.crs_rejected


def test_raises_with_too_few_usable_observations():
    window = pd.DataFrame({"u": [10, 20], "v": [5, 8], "m": [3, 4]})
    with pytest.raises(ValueError, match="usable"):
        fit_matching_function(window)


def test_drops_periods_with_zero_matches_rather_than_taking_their_log():
    window = _synthetic_window(a=0.3, b_u=0.5, b_v=0.5, n=30, seed=4)
    window = pd.concat(
        [window, pd.DataFrame({"u": [50, 60], "v": [10, 12], "m": [0, 0]})], ignore_index=True
    )
    fit = fit_matching_function(window)
    assert fit.n_obs == 30
