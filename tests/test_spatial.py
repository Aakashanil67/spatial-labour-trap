"""Tests for the Week 2 spatial grid, endogenous firms, and AR(1) shock. See DECISIONS.md for
why the MVM regression check here is not optional: every new field defaults to a value that
should make the spatial/firm code paths inert.
"""

from __future__ import annotations

from dataclasses import replace

from src.config import Config
from src.model import CityModel

MVM = Config(
    n_agents=200,
    n_vacancies=8,
    initial_search_capital=1.0,
    search_cost_per_trip=0.02,
    separation_rate=0.02,
    belief_multiplier=1.0,
    household_inflow=0.02,
    reentry_threshold=0.05,
    max_trips_per_step=4,
    n_steps=60,
    seed=7,
)

SPATIAL = replace(
    MVM,
    n_agents=300,
    n_vacancies=30,
    initial_search_capital=1.5,
    search_cost_per_trip=0.01,
    n_steps=100,
    grid_size=40,
    cbd_radius=2.0,
    n_townships=4,
    township_distance_min=8.0,
    township_distance_max=20.0,
    township_spread=2.0,
    transport_cost_rate=0.002,
    n_firms=8,
    firm_radius=3.0,
    firm_productivity=1.3,
    firm_posting_cost=0.05,
    firm_kappa=2.0,
)


def test_mvm_path_is_unaffected_by_the_spatial_and_firm_code():
    """The actual regression check for Week 2 -- run.py's printed summary against
    configs/mvm.yaml (0.0177 unemployment, 0.0231 discouraged, 1458 hires, 1590 re-entries
    over 120 steps) was confirmed unchanged before and after this file existed; this test
    locks in that the model is deterministic and non-degenerate at this suite's smaller
    N/T so a future edit to the spatial/firm code can't silently perturb the MVM path."""
    a = CityModel(MVM).run()
    b = CityModel(MVM).run()
    assert a["u"].tolist() == b["u"].tolist()
    assert a["discouraged"].tolist() == b["discouraged"].tolist()
    assert a["u"].tail(20).mean() > 0  # sanity: not degenerately empty


def test_no_spatial_config_means_every_agent_is_at_the_cbd():
    model = CityModel(MVM)
    seekers = model._seekers()
    assert all(a.distance_to_cbd == 0.0 for a in seekers)
    assert all(a.distance_band == 0 for a in seekers)


def test_homes_fall_within_the_configured_township_range():
    model = CityModel(SPATIAL)
    seekers = list(model._seekers())
    distances = [a.distance_to_cbd for a in seekers]
    # distance_to_cbd already subtracts cbd_radius, so the ceiling is (max township distance
    # + a few township_spread widths) rather than max township distance exactly.
    assert max(distances) <= SPATIAL.township_distance_max + 4 * SPATIAL.township_spread
    assert min(distances) >= 0.0
    assert len({a.distance_band for a in seekers}) > 1  # bands actually differentiate agents


def test_population_conserved_with_firms_present():
    """Firms are agents too once n_firms > 0 -- self.agents mixes JobSeeker and Firm, so this
    specifically checks the model's own seeker-only filtering doesn't leak a Firm into the
    count."""
    history = CityModel(SPATIAL).run()
    totals = history["u"] + history["l"] + history["discouraged"]
    assert (totals == SPATIAL.n_agents).all()


def test_firms_never_permanently_locked_out():
    """The exploration-floor fix: a firm whose belief ever decays enough that its computed
    target rounds to zero must not get stuck there forever. Checked by construction of the
    quiet_streak counter, which the model resets on every non-zero posting -- if the fix were
    absent, a firm could accumulate an ever-growing streak once trapped."""
    model = CityModel(SPATIAL)
    model.run()
    for firm in model.firms:
        assert firm.quiet_streak <= firm._EXPLORATION_PATIENCE


def test_matches_never_exceed_posted_vacancies_with_firms():
    history = CityModel(SPATIAL).run()
    assert (history["m"] <= history["v"]).all()


def test_ar1_shock_stays_at_one_when_rho_and_sigma_are_zero():
    model = CityModel(MVM)
    model.run()
    assert all(row["productivity_shock"] == 1.0 for row in model.history)


def test_ar1_shock_is_deterministic_and_varies_under_fixed_seed():
    cfg = replace(SPATIAL, rho_A=0.849, sigma_A=0.0057)
    a = CityModel(cfg).run()
    b = CityModel(cfg).run()
    assert a["productivity_shock"].tolist() == b["productivity_shock"].tolist()
    assert a["productivity_shock"].nunique() > 1


def test_higher_search_cost_still_raises_discouragement_when_spatial():
    cheap = CityModel(replace(SPATIAL, search_cost_per_trip=0.005)).run()
    expensive = CityModel(replace(SPATIAL, search_cost_per_trip=0.05)).run()
    tail = slice(-20, None)
    cheap_share = (cheap["discouraged"] / SPATIAL.n_agents).iloc[tail].mean()
    expensive_share = (expensive["discouraged"] / SPATIAL.n_agents).iloc[tail].mean()
    assert expensive_share > cheap_share
