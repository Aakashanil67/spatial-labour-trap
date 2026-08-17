"""Tests for src/moments.py. See DECISIONS.md, "The distance_gradient_slope moment was sourced
to a table that doesn't exist" -- these tests exist specifically to catch the class of error
that produced that bug: a moment silently computed against the wrong empirical object.
"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from src.agents import WAGE
from src.config import Config
from src.model import CityModel
from src.moments import (
    DAYS_PER_MONTH,
    compute_moments,
    discouraged_share_narrow,
    transport_budget_share,
)

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
        if key == "transport_budget_share":
            # A cost-of-one-search-trip / daily-wage ratio, not a share of a fixed pool --
            # it can legitimately exceed 1 when a single trip costs more than a day's wage,
            # unlike the other two moments, which are genuine population shares.
            assert value != value or value >= 0.0, f"{key} is negative and not nan: {value}"
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


# transport_budget_share, hand-calculated -- see DECISIONS.md, "transport_budget_share and its
# NHTS target were measuring two different things". Every fixture below uses a per-trip cost of
# exactly R0.05 (in wage-numeraire units) so the expected ratio is the same constant,
# 0.05 * DAYS_PER_MONTH, regardless of how spend is distributed across periods -- the point of
# the fix is that the ratio depends only on total spend and total trips, not on how many
# zero-trip periods sit in between.
_PER_TRIP_COST = 0.05
_EXPECTED_RATIO = _PER_TRIP_COST * DAYS_PER_MONTH


def test_transport_budget_share_one_trip_one_period():
    window = pd.DataFrame({"total_trips": [1], "transport_spend": [_PER_TRIP_COST]})
    assert transport_budget_share(window) == pytest.approx(_EXPECTED_RATIO)


def test_transport_budget_share_several_trips_one_period():
    window = pd.DataFrame({"total_trips": [10], "transport_spend": [10 * _PER_TRIP_COST]})
    assert transport_budget_share(window) == pytest.approx(_EXPECTED_RATIO)


def test_transport_budget_share_is_nan_when_no_trips_ever_happen():
    """A window where nobody ever took a search trip has no search-day cost to condition on --
    the moment must say so (nan), not silently report a false 0.0 that would look like a real,
    very-cheap-search-cost fit."""
    window = pd.DataFrame({"total_trips": [0, 0, 0], "transport_spend": [0.0, 0.0, 0.0]})
    share = transport_budget_share(window)
    assert share != share  # nan


def test_transport_budget_share_mixed_periods_ignores_zero_trip_periods():
    """Zero-trip periods contribute no trips and no spend to the totals, so mixing them in with
    active periods must not move the ratio -- the moment is conditional on a trip happening, not
    averaged over calendar periods regardless of activity."""
    window = pd.DataFrame(
        {
            "total_trips": [0, 5, 0, 3, 0],
            "transport_spend": [0.0, 5 * _PER_TRIP_COST, 0.0, 3 * _PER_TRIP_COST, 0.0],
        }
    )
    assert transport_budget_share(window) == pytest.approx(_EXPECTED_RATIO)


def test_transport_budget_share_uses_the_daily_wage_not_the_monthly_wage():
    """A sanity check on the unit conversion itself: one trip costing exactly one full monthly
    WAGE must come back as DAYS_PER_MONTH, since a monthly cost is DAYS_PER_MONTH daily wages."""
    window = pd.DataFrame({"total_trips": [1], "transport_spend": [WAGE]})
    assert transport_budget_share(window) == pytest.approx(DAYS_PER_MONTH)
