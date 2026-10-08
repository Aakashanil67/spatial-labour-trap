import numpy as np
import pytest
from pandas.testing import assert_frame_equal

from honours_simple.model import GROUPS, Params, application_limits, match_round, simulate

EMPTY = np.array([], dtype=int)


def test_match_round_with_no_applicants_or_no_jobs_hires_nobody():
    rng = np.random.default_rng(0)
    for applicants, open_jobs in [(EMPTY, np.arange(5)), (np.arange(5), EMPTY)]:
        hired, filled = match_round(applicants, open_jobs, rng)
        assert len(hired) == 0
        assert len(filled) == 0


def test_match_round_hires_only_applicants_into_open_jobs_and_only_once():
    rng = np.random.default_rng(1)
    for _ in range(500):
        applicants = rng.choice(300, size=rng.integers(1, 60), replace=False)
        open_jobs = rng.choice(150, size=rng.integers(1, 60), replace=False)
        hired, filled = match_round(applicants, open_jobs, rng)
        assert len(hired) == len(filled)
        assert len(hired) >= 1  # with at least one applicant and one job, some job is applied to
        assert len(np.unique(hired)) == len(hired)
        assert len(np.unique(filled)) == len(filled)
        assert np.isin(hired, applicants).all()
        assert np.isin(filled, open_jobs).all()


def test_match_round_winner_is_uniform_among_a_jobs_applicants():
    # One job, four applicants: all four apply to it, so only the tie-break picks the winner.
    # Without the shuffle in match_round, worker 0 would win every time.
    rng = np.random.default_rng(2)
    draws = 4000
    winners = [match_round(np.arange(4), np.array([7]), rng)[0][0] for _ in range(draws)]
    wins = np.bincount(winners, minlength=4)
    sd = np.sqrt(draws * 0.25 * 0.75)
    assert np.abs(wins - draws / 4).max() < 4 * sd, f"wins per worker: {wins.tolist()}"


def test_default_application_limits_are_2_1_0_by_distance():
    limits = application_limits(Params())
    np.testing.assert_array_equal(limits, np.repeat([2, 1, 0], 100))


def test_cheaper_search_gives_limits_3_2_1():
    limits = application_limits(Params(cost_multiplier=0.5))
    np.testing.assert_array_equal(limits, np.repeat([3, 2, 1], 100))


def test_allowance_of_4_gives_limits_3_1_1_and_3_3_2_at_half_cost():
    # the far group can afford one application at normal cost once the allowance exceeds 3.6
    normal = application_limits(Params(allowance=4.0))
    half = application_limits(Params(allowance=4.0, cost_multiplier=0.5))
    np.testing.assert_array_equal(normal, np.repeat([3, 1, 1], 100))
    np.testing.assert_array_equal(half, np.repeat([3, 3, 2], 100))


def test_limit_at_exact_budget_boundary_is_not_rounded_down():
    # 1.5 per application against an allowance of 3.0: exactly two fit.
    limits = application_limits(Params(distances=(1,), cost_per_distance=1.5, allowance=3.0))
    np.testing.assert_array_equal(limits, np.full(100, 2))


@pytest.mark.parametrize("jobs", [150, 300])
@pytest.mark.parametrize("cost_multiplier", [1.0, 0.5])
def test_simulation_accounting(jobs, cost_multiplier):
    p = Params(jobs=jobs, cost_multiplier=cost_multiplier)
    n_workers = 3 * p.workers_per_group
    df = simulate(p, seed=7)
    employed = df["employed"].to_numpy()
    hires = df["hires"].to_numpy()
    separations = df["separations"].to_numpy()

    assert len(df) == p.periods + 1
    assert hires.sum() > 0
    assert (employed <= min(n_workers, jobs)).all()
    # employed counts workers, open_jobs counts jobs: they must tell the same story
    assert (employed == jobs - df["open_jobs_after_sep"].to_numpy() + hires).all()
    assert (np.diff(employed) == hires[1:] - separations[1:]).all()
    # the pools recorded after separations are last period's employed minus this period's leavers
    still_employed = employed[:-1] - separations[1:]
    assert (df["open_jobs_after_sep"].to_numpy()[1:] == jobs - still_employed).all()
    assert (df["unemployed_after_sep"].to_numpy()[1:] == n_workers - still_employed).all()

    limit_by_group = application_limits(p)[:: p.workers_per_group]
    for limit, name in zip(limit_by_group, GROUPS, strict=True):
        assert (df[f"applications_{name}"] <= limit * df[f"unemployed_after_sep_{name}"]).all()
    if cost_multiplier == 1.0:
        assert (df["applications_far"] == 0).all()
        assert (df["hires_round_3"] == 0).all()  # nobody can afford a third application


def test_without_separations_employment_never_falls():
    df = simulate(Params(separation_prob=0.0), seed=3)
    assert (df["separations"] == 0).all()
    assert (np.diff(df["employed"]) >= 0).all()
    assert df["employed"].iloc[-1] > 0


def test_with_certain_separation_new_hires_survive_their_own_period():
    # Plenty of jobs, so almost every applicant is hired in round 1.
    df = simulate(Params(separation_prob=1.0, jobs=10_000, periods=10), seed=4)
    employed = df["employed"].to_numpy()
    separations = df["separations"].to_numpy()
    assert employed[1] > 0
    # everyone employed at the end of t-1 leaves at the start of t, and nobody hired in t does
    np.testing.assert_array_equal(separations[1:], employed[:-1])
    # Only near and middle workers can afford to apply (about 200 of them), and from period 2
    # they are all job-holders who just separated. They must still be able to apply.
    assert (df["hires"].to_numpy()[2:] >= 190).all()


def test_same_seed_gives_identical_run_and_different_seed_does_not():
    p = Params(periods=40)
    first = simulate(p, seed=11)
    assert_frame_equal(first, simulate(p, seed=11))
    assert not first.equals(simulate(p, seed=12))


def test_one_round_matches_urn_ball_expectation():
    # Petrongolo & Pissarides (2001): u applicants each pick one of v jobs at random, so the
    # expected number of jobs that get at least one application is v * (1 - (1 - 1/v) ** u).
    u, v, reps = 20, 10, 10_000
    rng = np.random.default_rng(12345)
    hires = np.array([len(match_round(np.arange(u), np.arange(v), rng)[0]) for _ in range(reps)])
    expected = v * (1 - (1 - 1 / v) ** u)
    se = hires.std(ddof=1) / np.sqrt(reps)
    message = f"mean hires {hires.mean():.4f}, expected {expected:.4f}, MC SE {se:.4f}"
    print(message)
    assert abs(hires.mean() - expected) < 4 * se, message
