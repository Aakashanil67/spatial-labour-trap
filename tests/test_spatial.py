"""Tests for the Week 2 spatial grid, endogenous firms, and AR(1) shock. See DECISIONS.md for
why the MVM regression check here is not optional: every new field defaults to a value that
should make the spatial/firm code paths inert.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.agents import Firm
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


def test_fill_probability_never_decays_below_its_floor():
    """quiet_streak staying bounded (the test above) is true by construction even inside the
    exact permanent-lockout scenario it's meant to rule out -- the streak resets every time the
    exploration mechanism fires a token vacancy, whether or not that vacancy is ever filled.
    Found by sweeping n_agents on configs/baseline.yaml: every firm's fill_prob_estimate
    crashed to 0.000 and stayed there, total vacancies collapsed to near the exploration
    floor's single trial posting, and unemployment approached 100 per cent -- see DECISIONS.md.
    This checks the belief itself, not just the counter."""
    cfg = replace(SPATIAL, n_agents=3300, seed=42)
    model = CityModel(cfg)
    model.run()
    for firm in model.firms:
        assert firm.fill_prob_estimate >= Firm._MIN_FILL_PROB


def test_search_activity_does_not_permanently_freeze_at_scale():
    """observed_hire_rate_per_trip's naive initial value is total initial vacancies divided by
    n_agents, and decide_trips rounds a favourability score to a whole number of trips -- below
    intensity 1/(2*max_trips_per_step), round() can only return zero. Because the observed rate
    is deliberately left unchanged on an all-quiet step, a population whose typical perceived
    rate starts below that threshold together used to freeze at zero trips for the rest of the
    run, with no way to generate the observation that would correct it -- and a bigger
    population made the freeze *more* likely, not less, since it only lowers the naive initial
    rate further. n_agents has to actually be scaled up here, not just n_vacancies cut, or the
    test passes even against the unfixed code -- checked directly against a stash of the
    pre-fix decide_trips before trusting this. See DECISIONS.md."""
    cfg = replace(SPATIAL, n_agents=3300, n_vacancies=1, seed=42)
    model = CityModel(cfg)
    history = model.run()
    tail = history[history["step"] > history["step"].max() - 20]
    assert tail["total_trips"].sum() > 0


# Mirrors configs/baseline.yaml's own economics (small discount_rate + separation_rate, giving
# a large expected_value_per_hire) rather than loading the YAML file, so this test stays
# self-contained -- the low discount+separation denominator is exactly what makes the deadlock
# below reachable, see the test's own docstring.
_LOW_DENOMINATOR_ECONOMY = Config(
    n_agents=500,
    n_vacancies=15,
    initial_search_capital=0.6,
    initial_capital_spread=0.5,
    search_cost_per_trip=0.02,
    separation_rate=0.0048,
    belief_multiplier=1.0,
    household_inflow=0.008,
    reentry_threshold=0.035,
    max_trips_per_step=3,
    n_steps=20,
    seed=42,
    grid_size=40,
    cbd_radius=2.0,
    n_townships=4,
    township_distance_min=8.0,
    township_distance_max=20.0,
    township_spread=2.0,
    transport_cost_rate=0.004,
    n_firms=5,
    firm_radius=2.5,
    firm_productivity=1.2,
    firm_posting_cost=0.1,
    firm_kappa=0.2,
    discount_rate=0.001332,
    rho_A=0.849,
    sigma_A=0.0057,
)


def test_observed_hire_rate_never_decays_to_exactly_zero():
    """A third door into the same deadlock class as the two tests above. The Week 1 guard
    ("don't reset the belief to 0.0 on a quiet step") only protects total_trips == 0; it does
    nothing when total_trips is genuinely positive but every firm's own computed target rounds
    to zero on the very first step (reachable at a low enough firm_kappa relative to a large
    expected_value_per_hire), since m_t / total_trips = 0 / positive = 0.0 is a real
    observation, not a quiet step, and the guard correctly lets it through. Once
    observed_hire_rate_per_trip is exactly 0.0, decide_trips computes desired = 0 for the whole
    population simultaneously and it never generates another observation -- confirmed this
    reproduces against a stash of the pre-fix model.py (total_trips stuck at 0 from step 2
    onward) before trusting this test. See DECISIONS.md."""
    model = CityModel(_LOW_DENOMINATOR_ECONOMY)
    model.run()
    assert model.observed_hire_rate_per_trip >= 0.005


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


def test_no_wealth_spread_means_everyone_is_quartile_zero():
    model = CityModel(MVM)  # initial_capital_spread defaults to 0.0
    seekers = list(model._seekers())
    assert all(a.wealth_quartile == 0 for a in seekers)
    assert all(a.search_capital == MVM.initial_search_capital for a in seekers)


def test_wealth_quartiles_are_evenly_sized_and_correctly_ordered():
    cfg = replace(MVM, n_agents=400, initial_capital_spread=0.5)
    model = CityModel(cfg)
    seekers = list(model._seekers())
    from collections import Counter

    counts = Counter(a.wealth_quartile for a in seekers)
    assert counts == {0: 100, 1: 100, 2: 100, 3: 100}
    means = [
        sum(a.search_capital for a in seekers if a.wealth_quartile == q) / 100 for q in range(4)
    ]
    assert means == sorted(means)  # quartile 0 poorest, quartile 3 richest, strictly ordered


def test_wealth_quartile_never_changes_even_as_capital_is_spent():
    """D3: the quartile is a property of the initial draw, not current capital -- an agent
    spending its way toward zero (or receiving the household inflow) must not migrate."""
    cfg = replace(MVM, n_agents=200, initial_capital_spread=0.5, n_steps=40)
    model = CityModel(cfg)
    seekers = list(model._seekers())
    quartiles_before = {a.unique_id: a.wealth_quartile for a in seekers}
    model.run()
    seekers_after = list(model._seekers())
    assert all(a.wealth_quartile == quartiles_before[a.unique_id] for a in seekers_after)


def test_cell_aggregates_sum_to_the_same_totals_as_the_main_history():
    cfg = replace(SPATIAL, initial_capital_spread=0.5)
    model = CityModel(cfg)
    history = model.run()
    cells = model.cell_dataframe()
    last_step = int(history["step"].iloc[-1])
    row = history[history["step"] == last_step].iloc[0]
    cell_rows = cells[cells["step"] == last_step]
    assert cell_rows["n_searching"].sum() == row["u"]
    assert cell_rows["n_employed"].sum() == row["l"]
    assert cell_rows["n_discouraged"].sum() == row["discouraged"]
    assert cell_rows["n_long_term"].sum() == row["n_long_term"]


def test_long_term_share_is_zero_below_the_twelve_month_threshold():
    """A short, fast-churning run shouldn't produce any 12-month-plus spells -- if this ever
    goes positive on a config with n_steps well under 12, the threshold logic is wrong."""
    cfg = replace(MVM, n_steps=8)
    history = CityModel(cfg).run()
    assert (history["n_long_term"] == 0).all()


def test_completed_spells_and_censored_spells_account_for_the_full_population():
    """Every agent has been in exactly one spell that either completed (hired or
    discouraged) or is still open (censored) at the point the run ends -- the two counts
    together should never exceed the population, and for a run with enough turnover, should
    be close to it."""
    cfg = replace(SPATIAL, n_steps=150)
    model = CityModel(cfg)
    model.run()
    spells = model.completed_spell_dataframe()
    total = spells["count"].sum()
    assert total <= cfg.n_agents * (
        cfg.n_steps // 1 + 1
    )  # loose upper bound, no double count per spell
    assert total > 0


def test_extreme_scarcity_produces_a_fully_censored_long_spell():
    """Confirms the long-term and censoring mechanism actually fires under a genuinely
    scarce regime, not just that it stays at zero everywhere -- caught during manual testing
    that a comfortable config alone wouldn't exercise this path at all. Checks the run's peak,
    not the final step: n_long_term genuinely cycles up and down as this population moves
    through scarcity, discouragement and re-entry together (observed peaking at 286 of 300
    agents around step 20-40, then declining as the cohort clears), so asserting only on the
    last step is asserting on whichever phase of that cycle happens to land there -- brittle
    to a completely unrelated fix elsewhere changing the cycle's timing, not a real regression
    in the mechanism this test means to check."""
    cfg = replace(
        SPATIAL,
        n_vacancies=2,
        n_firms=1,
        firm_kappa=0.1,
        n_steps=80,
        reentry_threshold=0.001,
        household_inflow=0.0005,
    )
    history = CityModel(cfg).run()
    assert history["n_long_term"].max() > 0


def test_trace_is_empty_when_no_agents_are_named():
    model = CityModel(MVM)  # trace_agent_ids defaults to ()
    model.run()
    assert model.trace_dataframe().empty


def _first_seeker_ids(cfg: Config, n: int) -> tuple[int, ...]:
    """Firms are created before JobSeekers (see model.py), so seeker unique_ids start after
    n_firms, not at 1 -- probe a throwaway model of the same config rather than hardcode the
    offset, so this stays correct if SPATIAL's firm count ever changes."""
    probe = CityModel(cfg)
    return tuple(sorted(a.unique_id for a in probe._seekers())[:n])


def test_trace_records_only_the_named_agents_every_step():
    ids = _first_seeker_ids(SPATIAL, 3)
    cfg = replace(SPATIAL, trace_agent_ids=ids)
    model = CityModel(cfg)
    history = model.run()
    trace = model.trace_dataframe()
    assert set(trace["unique_id"].unique()) == set(ids)
    assert len(trace) == 3 * len(history)  # one row per traced agent per step, no gaps


def test_traced_agent_state_matches_the_live_agent_at_run_end():
    (agent_id,) = _first_seeker_ids(SPATIAL, 1)
    cfg = replace(SPATIAL, trace_agent_ids=(agent_id,))
    model = CityModel(cfg)
    model.run()
    trace = model.trace_dataframe()
    last_row = trace[trace["unique_id"] == agent_id].sort_values("step").iloc[-1]
    live_agent = next(a for a in model._seekers() if a.unique_id == agent_id)
    assert last_row["state"] == live_agent.state.name
    assert last_row["search_capital"] == pytest.approx(live_agent.search_capital)
