"""Tests for src/calibrate.py. The real test is test_recovers_a_known_parameter_vector (marked
slow) -- simulating "empirical" moments from a known parameter vector and confirming the MSM
engine finds its way back to something close, the same "recover a known answer" standard as
dmp.py's Chen recovery and matching.py's synthetic-data tests. Everything else here is fast
unit coverage for the pieces that don't need a real optimisation run to check.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from src.calibrate import (
    DEFAULT_BOUNDS,
    MOMENT_KEYS,
    PARAM_NAMES,
    EmpiricalMoments,
    calibrate,
    load_empirical_moments,
    msm_loss,
    simulate_moments,
)
from src.config import Config

SMALL = Config(
    n_agents=100,
    n_vacancies=10,
    initial_search_capital=0.6,
    search_cost_per_trip=0.02,
    separation_rate=0.01,
    belief_multiplier=1.0,
    household_inflow=0.01,
    reentry_threshold=0.04,
    max_trips_per_step=3,
    n_steps=60,
    seed=1,
    grid_size=20,
    # 2.0, matching baseline.yaml -- the geometric-identification bound (2 * cbd_radius, see
    # calibrate.py's _validate_firm_radius_bound) must comfortably clear the recovery test's
    # own tight_bounds firm_radius upper of 3.0 below.
    cbd_radius=2.0,
    n_townships=3,
    township_distance_min=4.0,
    township_distance_max=10.0,
    township_spread=1.0,
    transport_cost_rate=0.003,
    n_firms=4,
    firm_radius=2.0,
    firm_productivity=1.2,
    firm_posting_cost=0.05,
    firm_kappa=0.8,
    burn_in_steps=20,
)


def _write_moments_csv(path, values: dict[str, float], ses: dict[str, float], provisional=None):
    provisional = provisional or dict.fromkeys(MOMENT_KEYS, False)
    df = pd.DataFrame(
        {
            "key": list(MOMENT_KEYS),
            "value": [values[k] for k in MOMENT_KEYS],
            "standard_error": [ses[k] for k in MOMENT_KEYS],
            "period": ["2026-Q1"] * len(MOMENT_KEYS),
            "source": ["test fixture"] * len(MOMENT_KEYS),
            "provisional": [provisional[k] for k in MOMENT_KEYS],
        }
    )
    df.to_csv(path, index=False)
    return path


def test_load_empirical_moments_raises_if_any_moment_still_provisional(tmp_path):
    path = tmp_path / "moments.csv"
    values = dict.fromkeys(MOMENT_KEYS, 0.1)
    ses = dict.fromkeys(MOMENT_KEYS, 0.01)
    provisional = dict.fromkeys(MOMENT_KEYS, False)
    provisional["discouraged_share"] = True
    _write_moments_csv(path, values, ses, provisional)
    with pytest.raises(ValueError, match="provisional"):
        load_empirical_moments(str(path))


def test_load_empirical_moments_raises_if_a_moment_is_missing(tmp_path):
    path = tmp_path / "moments.csv"
    keys = [k for k in MOMENT_KEYS if k != "long_term_share"]
    df = pd.DataFrame(
        {
            "key": keys,
            "value": [0.1] * len(keys),
            "standard_error": [0.01] * len(keys),
            "period": ["2026-Q1"] * len(keys),
            "source": ["test"] * len(keys),
            "provisional": [False] * len(keys),
        }
    )
    df.to_csv(path, index=False)
    with pytest.raises(ValueError, match="missing"):
        load_empirical_moments(str(path))


def test_load_empirical_moments_reads_real_moments_csv():
    empirical = load_empirical_moments("data/moments.csv")
    assert set(empirical.values) == set(MOMENT_KEYS)
    assert set(empirical.standard_errors) == set(MOMENT_KEYS)
    assert not any(np.isnan(v) for v in empirical.values.values())


def test_msm_loss_is_deterministic_at_a_fixed_parameter_vector():
    """D12's actual test: two evaluations of the loss at the same parameter vector, same
    common-random-number seeds, return an identical float -- not just a close one."""
    empirical = EmpiricalMoments(
        values=dict.fromkeys(MOMENT_KEYS, 0.1), standard_errors=dict.fromkeys(MOMENT_KEYS, 0.05)
    )
    x = np.array([0.02, 0.6, 2.0, 0.8])
    loss_1 = msm_loss(x, SMALL, empirical, seeds=(1, 2, 3))
    loss_2 = msm_loss(x, SMALL, empirical, seeds=(1, 2, 3))
    assert loss_1 == loss_2


def test_simulate_moments_returns_all_four_keys_with_finite_variance():
    params = dict(zip(PARAM_NAMES, [0.02, 0.6, 2.0, 0.8], strict=True))
    result = simulate_moments(SMALL, params, seeds=(1, 2, 3))
    assert set(result) == set(MOMENT_KEYS)
    for mean, variance in result.values():
        assert np.isfinite(mean)
        assert variance >= 0


def test_calibrate_rejects_a_firm_radius_bound_beyond_the_geometric_identification_limit():
    """With belief_multiplier=1, search tickets and firms are both drawn within a disk of
    radius cbd_radius, so no ticket-firm pair can ever exceed 2*cbd_radius apart -- a
    firm_radius upper bound past that diameter makes every firm reachable regardless of its
    exact value, and the calibration loss goes flat. See DECISIONS.md, "The search-position
    draw oversampled the CBD centre, and it explains the flat firm_radius calibration region."
    """
    too_wide = dict(DEFAULT_BOUNDS, firm_radius=(1.0, 2 * SMALL.cbd_radius + 0.5))
    empirical = EmpiricalMoments(
        values=dict.fromkeys(MOMENT_KEYS, 0.1), standard_errors=dict.fromkeys(MOMENT_KEYS, 0.05)
    )
    with pytest.raises(ValueError, match="geometric"):
        calibrate(SMALL, bounds=too_wide, n_lhs_points=2, empirical=empirical)


def test_calibrate_accepts_a_firm_radius_bound_at_exactly_the_geometric_limit():
    at_limit = dict(DEFAULT_BOUNDS, firm_radius=(1.0, 2 * SMALL.cbd_radius))
    empirical = EmpiricalMoments(
        values=dict.fromkeys(MOMENT_KEYS, 0.1), standard_errors=dict.fromkeys(MOMENT_KEYS, 0.05)
    )
    calibrate(SMALL, bounds=at_limit, n_lhs_points=2, empirical=empirical)  # must not raise


def test_calibrate_skips_the_geometric_check_when_belief_multiplier_is_not_one():
    """The geometric argument assumes the unbiased D2 disk (belief_multiplier=1); a biased
    search radius scales the ticket-side disk too, so the bound doesn't apply the same way and
    the check must not fire."""
    biased = replace(SMALL, belief_multiplier=1.5)
    too_wide = dict(DEFAULT_BOUNDS, firm_radius=(1.0, 2 * SMALL.cbd_radius + 0.5))
    empirical = EmpiricalMoments(
        values=dict.fromkeys(MOMENT_KEYS, 0.1), standard_errors=dict.fromkeys(MOMENT_KEYS, 0.05)
    )
    calibrate(biased, bounds=too_wide, n_lhs_points=2, empirical=empirical)  # must not raise


def test_calibration_result_flags_a_parameter_landing_within_one_percent_of_its_bound():
    """A numerical estimate at or within 1% of a bound is boundary-adjacent and weakly
    identified, not a genuine interior optimum -- see Task 8's no-false-success gate."""
    empirical = EmpiricalMoments(
        values=dict.fromkeys(MOMENT_KEYS, 0.1), standard_errors=dict.fromkeys(MOMENT_KEYS, 0.05)
    )
    # A tiny box pinned right at firm_kappa's upper edge forces Nelder-Mead to land there.
    pinned_bounds = dict(DEFAULT_BOUNDS, firm_kappa=(1.99, 2.0))
    result = calibrate(SMALL, bounds=pinned_bounds, n_lhs_points=2, empirical=empirical)
    assert "firm_kappa" in result.boundary_adjacent_params


@pytest.mark.slow
def test_recovers_a_known_parameter_vector():
    """The real validation: simulate "empirical" moments from a known parameter vector, feed
    them back in as the calibration target, and confirm the LHS+Nelder-Mead engine finds its
    way back to something close to the vector that generated them -- not just that it runs."""
    true_params = {
        "search_cost_per_trip": 0.025,
        "initial_search_capital": 0.7,
        "firm_radius": 2.2,
        "firm_kappa": 0.9,
    }
    recovery_seeds = tuple(range(100, 130))  # 30 seeds -- enough to average out simulation noise
    simulated = simulate_moments(SMALL, true_params, recovery_seeds)
    empirical = EmpiricalMoments(
        values={k: mean for k, (mean, _var) in simulated.items()},
        standard_errors={k: max(var**0.5, 1e-4) for k, (_mean, var) in simulated.items()},
    )

    tight_bounds = {
        "search_cost_per_trip": (0.015, 0.035),
        "initial_search_capital": (0.4, 1.0),
        "firm_radius": (1.5, 3.0),
        "firm_kappa": (0.5, 1.3),
    }
    result = calibrate(
        SMALL,
        bounds=tight_bounds,
        n_lhs_points=15,
        calibration_seeds=tuple(range(1, 11)),
        validation_seeds=tuple(range(200, 210)),
        empirical=empirical,
    )

    for name in PARAM_NAMES:
        low, high = tight_bounds[name]
        span = high - low
        assert abs(result.params[name] - true_params[name]) < 0.35 * span, (
            f"{name}: recovered {result.params[name]:.4f}, true {true_params[name]:.4f}, "
            f"bounds span {span:.4f}"
        )
