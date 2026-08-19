"""Tests for the MVM. Each one has to be able to fail for a real reason -- see kill-slop.

Runs at N=200/T=60 rather than the shipped configs/mvm.yaml's N=500/T=120, so the fast suite
stays fast; the c-sensitivity and re-entry tests are checked separately at a scale small enough
to run in CI (`pytest -m "not slow"`) without needing the `slow` marker.
"""

from __future__ import annotations

from dataclasses import replace

from src.config import Config
from src.model import CityModel

BASE = Config(
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


def run(config: Config):
    return CityModel(config).run()


def test_population_conserved_every_step():
    history = run(BASE)
    totals = history["u"] + history["l"] + history["discouraged"]
    assert (totals == BASE.n_agents).all()


def test_deterministic_under_fixed_seed():
    a = run(BASE)
    b = run(BASE)
    assert a.equals(b)


def test_different_seed_gives_different_trajectory():
    a = run(BASE)
    b = run(replace(BASE, seed=BASE.seed + 1))
    assert not a["u"].equals(b["u"])


def test_higher_search_cost_raises_discouragement():
    cheap = run(replace(BASE, search_cost_per_trip=0.01))
    expensive = run(replace(BASE, search_cost_per_trip=0.10))
    tail = slice(-20, None)
    cheap_share = (cheap["discouraged"] / BASE.n_agents).iloc[tail].mean()
    expensive_share = (expensive["discouraged"] / BASE.n_agents).iloc[tail].mean()
    assert expensive_share > cheap_share


def test_reentry_fires():
    history = run(BASE)
    assert history["n_reentries"].sum() > 0


def test_discouragement_fires():
    """The above two tests are meaningless if nobody ever becomes discouraged in the first
    place -- this pins that down directly."""
    history = run(BASE)
    assert history["n_new_discouraged"].sum() > 0


def test_matches_never_exceed_available_stocks():
    """D11: m_t must never exceed min(u_t, v_t), by construction of the matching lottery."""
    history = run(BASE)
    assert (history["m"] <= history[["u", "v"]].min(axis=1)).all()


def test_stock_identity_holds_exactly():
    """D11: u_{t+1} = u_t - m_t + n_separations_{t+1} - n_new_discouraged_{t+1} + n_reentries_{t+1}.

    Flow counters are indexed to when they're detected (start of the step they apply to), so
    this combines period t's outcome (m_t) with period t+1's own transition counts -- see the
    D11 note in DECISIONS.md for the full derivation."""
    history = run(BASE)
    u = history["u"].to_numpy()
    m = history["m"].to_numpy()
    sep = history["n_separations"].to_numpy()
    new_disc = history["n_new_discouraged"].to_numpy()
    reentries = history["n_reentries"].to_numpy()

    predicted_next_u = u[:-1] - m[:-1] + sep[1:] - new_disc[1:] + reentries[1:]
    assert (predicted_next_u == u[1:]).all()


def test_activation_order_robustness():
    """D1: aggregate outcomes should be statistically indistinguishable between shuffled and
    fixed-order activation, since no per-agent method in this MVM reads a sibling agent's
    just-updated state within a step. This currently passes trivially by construction -- it's
    the regression guard for when Week 2's neighbourhood-radius hiring can introduce genuine
    order-sensitivity, not evidence that no such sensitivity could ever exist."""
    shuffled = run(replace(BASE, shuffled_activation=True))
    fixed = run(replace(BASE, shuffled_activation=False))
    shuffled_mean_u = shuffled["u"].tail(20).mean()
    fixed_mean_u = fixed["u"].tail(20).mean()
    assert abs(shuffled_mean_u - fixed_mean_u) <= 0.25 * BASE.n_agents


def test_jobless_clock_survives_a_discouragement_cycle():
    """The long-term moment's estimand is QLFS's Long_term_unempl, which StatsSA derives from
    time since the respondent last worked -- a pause in active search does not reset it. The
    searching-state spell clock (months_in_state) DOES reset on discouraged -> searching
    re-entry, which is correct for the spell histogram but wrong for this moment: measuring
    the moment off months_in_state undercounted long-term joblessness in exact proportion to
    the model's own discouragement churn. See DECISIONS.md, "long_term_share was measuring the
    wrong clock"."""
    from src.agents import SeekerState

    model = CityModel(BASE)
    agent = next(iter(model._seekers()))
    agent.months_jobless = 14
    agent.months_in_state = 3
    agent.state = SeekerState.SEARCHING
    agent.search_capital = 1.0

    agent.months_in_state = 0
    agent.state = SeekerState.DISCOURAGED  # capital exhaustion: spell clock resets...
    agent.step_discouraged()
    assert agent.months_jobless == 15  # ...the jobless clock must not


def test_jobless_clock_resets_only_on_hire():
    model = CityModel(BASE)
    agent = next(iter(model._seekers()))
    agent.months_jobless = 20
    agent.resolve_hire()
    assert agent.months_jobless == 0


def test_n_long_term_counts_jobless_duration_not_state_spell():
    """An agent 15 months jobless whose current searching spell is only 2 months old IS
    long-term unemployed on QLFS's definition. Before the fix, n_long_term read
    months_in_state and counted this agent as short-term."""
    from src.agents import SeekerState

    cfg = replace(BASE, n_steps=1, separation_rate=0.0, n_vacancies=0)
    model = CityModel(cfg)
    for agent in model._seekers():
        agent.state = SeekerState.EMPLOYED  # park everyone else out of the searching pool
    probe = next(iter(model._seekers()))
    probe.state = SeekerState.SEARCHING
    probe.months_jobless = 15
    probe.months_in_state = 2
    probe.search_capital = 5.0  # comfortably above one trip, so no exhaustion exit
    history = model.run()
    assert history["n_long_term"].iloc[0] == 1
