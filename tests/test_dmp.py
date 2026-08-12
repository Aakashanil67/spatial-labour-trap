"""Tests for src/dmp.py. The first test is the real one: feeding Chen (2025)'s own Table 1
parameters into this system and recovering his own reported theta target independently
confirms the six-equation transcription is right, not just that the solver runs.
"""

from __future__ import annotations

import pytest

from src.dmp import DMPParams, solve_steady_state

CHEN_TABLE_1 = DMPParams(
    a=0.471,
    alpha=0.667,
    eta=0.6,
    phi=0.6,
    r=0.004,
    lambda_sep=0.0144,
    c_post=0.273,
    b=0.5,
    productivity=1.0,
)

MONTHLY = DMPParams(
    a=0.3,
    alpha=0.667,
    eta=0.6,
    phi=0.6,
    r=0.001332,
    lambda_sep=0.0048,
    c_post=0.1,
    b=0.5,
    productivity=1.2,
)


def test_chen_table_1_recovers_chens_own_theta_target():
    """Chen calibrated a=0.471 specifically so his system would produce theta=0.78 (Miyamoto
    2011's target). Recovering theta ~= 0.78 independently, from a from-scratch transcription
    of his equations, is the actual validation that the system was transcribed correctly --
    not something either party can fake by having tuned a itself."""
    sol = solve_steady_state(CHEN_TABLE_1)
    assert sol.converged
    assert sol.max_residual < 1e-6
    assert sol.theta == pytest.approx(0.78, abs=0.01)


def test_solution_respects_its_own_bounds():
    sol = solve_steady_state(CHEN_TABLE_1)
    assert 0 < sol.l < 1
    assert 0 < sol.u < 1
    assert sol.v >= 0
    assert 0 < sol.q <= 1
    assert sol.theta >= 0
    assert sol.l + sol.u == pytest.approx(1.0, abs=1e-6)


def test_converges_at_this_thesis_own_monthly_parameters():
    sol = solve_steady_state(MONTHLY)
    assert sol.converged
    assert sol.max_residual < 1e-6


def test_robust_to_a_poor_initial_guess():
    default = solve_steady_state(MONTHLY)
    bad_start = solve_steady_state(MONTHLY, initial_guess=(0.5, 0.5, 2.0, 0.3, 0.9, 3.0))
    assert bad_start.converged
    assert bad_start.l == pytest.approx(default.l, abs=1e-4)
    assert bad_start.theta == pytest.approx(default.theta, abs=1e-4)


def test_deterministic():
    a = solve_steady_state(MONTHLY)
    b = solve_steady_state(MONTHLY)
    assert (a.l, a.u, a.v, a.w, a.q, a.theta) == (b.l, b.u, b.v, b.w, b.q, b.theta)


def test_higher_matching_efficiency_raises_the_job_finding_rate():
    """Economic sanity check, not just a numerical one: a higher a should make the market
    easier to match in, raising theta (tighter market, since firms find it more attractive
    to post) and the vacancy-filling probability's counterpart, the job-finding rate a *
    theta**(1-phi)."""
    low_a = solve_steady_state(DMPParams(**{**MONTHLY.__dict__, "a": 0.2}))
    high_a = solve_steady_state(DMPParams(**{**MONTHLY.__dict__, "a": 0.5}))
    assert low_a.converged and high_a.converged
    # job-finding rate f = a * theta ** (1 - phi); not a DMPSolution field, computed directly.
    f_low = 0.2 * low_a.theta ** (1 - MONTHLY.phi)
    f_high = 0.5 * high_a.theta ** (1 - MONTHLY.phi)
    assert f_high > f_low
