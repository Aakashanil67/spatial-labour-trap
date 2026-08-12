"""Tests for src/moments.py. See DECISIONS.md, "The distance_gradient_slope moment was sourced
to a table that doesn't exist" -- these tests exist specifically to catch the class of error
that produced that bug: a moment silently computed against the wrong empirical object.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.config import Config
from src.model import CityModel
from src.moments import compute_moments, discouraged_share_narrow

MVM = Config(
    n_agents=200,
    n_vacancies=15,
    initial_search_capital=1.0,
    search_cost_per_trip=0.02,
    separation_rate=0.02,
    belief_multiplier=1.0,
    household_inflow=0.02,
    reentry_threshold=0.05,
    max_trips_per_step=4,
    n_steps=60,
    seed=7,
    burn_in_steps=20,
)

SPATIAL = replace(
    MVM,
    n_agents=300,
    n_vacancies=15,
    n_steps=100,
    burn_in_steps=30,
    grid_size=40,
    cbd_radius=2.0,
    n_townships=4,
    township_distance_min=8.0,
    township_distance_max=20.0,
    township_spread=2.0,
    transport_cost_rate=0.003,
    n_firms=5,
    firm_radius=2.5,
    firm_productivity=1.2,
    firm_posting_cost=0.08,
    firm_kappa=1.0,
    initial_capital_spread=0.5,
)


def test_distance_gradient_slope_is_nan_without_spatial_variation():
    """The MVM has every agent at distance 0 -- a percentile rank over a constant is
    undefined, and the moment must say so (nan) rather than silently return 0 or some other
    number that looks like a real answer."""
    model = CityModel(MVM)
    history = model.run()
    moments = compute_moments(model, history)
    assert moments["distance_gradient_slope"] != moments["distance_gradient_slope"]  # nan


def test_distance_gradient_slope_is_a_real_number_when_spatial():
    model = CityModel(SPATIAL)
    history = model.run()
    moments = compute_moments(model, history)
    slope = moments["distance_gradient_slope"]
    assert slope == slope  # not nan
    assert -100 <= slope <= 100  # sane bound: percentage points per 10 percentile points


def test_all_four_moments_are_present_and_finite_or_nan_only_for_distance():
    model = CityModel(SPATIAL)
    history = model.run()
    moments = compute_moments(model, history)
    assert set(moments) == {
        "distance_gradient_slope",
        "discouraged_share",
        "transport_budget_share",
        "long_term_share",
    }
    for key, value in moments.items():
        if key == "distance_gradient_slope":
            continue
        assert 0.0 <= value <= 1.0 or value == 0.0, f"{key} out of a sane [0, 1] range: {value}"


def test_burn_in_actually_excludes_the_cold_start_transient():
    """A moment computed with burn_in_steps=0 on a run that starts at 100% unemployment must
    differ from the same run's moment computed after burn-in, or burn-in isn't doing anything."""
    model = CityModel(replace(SPATIAL, burn_in_steps=0))
    history = model.run()
    no_burn_in = compute_moments(model, history)

    model2 = CityModel(SPATIAL)  # burn_in_steps=30
    history2 = model2.run()
    with_burn_in = compute_moments(model2, history2)

    assert no_burn_in["discouraged_share"] != with_burn_in["discouraged_share"]


def test_burn_in_consuming_the_whole_run_raises_rather_than_returning_nonsense():
    model = CityModel(replace(SPATIAL, burn_in_steps=SPATIAL.n_steps))
    history = model.run()
    with pytest.raises(ValueError, match="burn_in_steps"):
        compute_moments(model, history)


def test_discouraged_share_union_is_at_least_the_narrow_share():
    """The union (hard-discouraged + belief-inactive) can never be smaller than the narrow,
    hard-state-only share -- it's a superset by construction."""
    model = CityModel(SPATIAL)
    history = model.run()
    moments = compute_moments(model, history)
    window = history[history["step"] > SPATIAL.burn_in_steps]
    narrow = discouraged_share_narrow(window, SPATIAL.n_agents)
    assert moments["discouraged_share"] >= narrow


def test_moments_are_deterministic_under_a_fixed_seed():
    a = CityModel(SPATIAL)
    ha = a.run()
    b = CityModel(SPATIAL)
    hb = b.run()
    assert compute_moments(a, ha) == compute_moments(b, hb)
