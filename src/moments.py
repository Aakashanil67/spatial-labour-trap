"""The four simulated moments, computed from a completed run against the same definitions
data/moments.csv uses for the empirical targets. Time-averaged moments exclude the burn-in
window (configs/*.yaml's burn_in_steps); the one cross-sectional moment (distance_gradient_slope)
uses the model's final state, which is a defensible cross-sectional snapshot precisely because
burn-in exists to get the model into a stationary regime before that snapshot is taken.
"""

from __future__ import annotations

import math

import pandas as pd

from src.agents import WAGE, SeekerState
from src.model import CityModel

# South Africa's conventional working-days-per-month figure, used only to convert the monthly
# WAGE numeraire to a daily rate -- the same convention notebook 02 uses to convert NHTS's
# monthly wage figure to a daily one, so both sides of transport_budget_share are on the same
# (daily, per-trip) footing. See DECISIONS.md, "transport_budget_share and its NHTS target were
# measuring two different things".
DAYS_PER_MONTH = 21.7


def compute_moments(model: CityModel, history: pd.DataFrame) -> dict[str, float]:
    cfg = model.config
    window = history[history["step"] > cfg.burn_in_steps]
    if window.empty:
        raise ValueError(
            f"burn_in_steps ({cfg.burn_in_steps}) consumed the entire {cfg.n_steps}-step run; "
            "no steps left to average the moments over."
        )

    return {
        "distance_gradient_slope": distance_gradient_slope(model),
        "discouraged_share": discouraged_share(window, cfg.n_agents),
        "transport_budget_share": transport_budget_share(window),
        "long_term_share": long_term_share(window),
    }


def discouraged_share(window: pd.DataFrame, n_agents: int) -> float:
    """StatsSA's discouraged work-seeker definition is behavioural (believes no jobs are
    available), not financial -- see M10 in DECISIONS.md. The model has two routes into
    "not actively searching despite wanting work": the hard DISCOURAGED state (capital
    exhausted) and belief-driven inactivity (SEARCHING agents choosing zero trips this step).
    The union of both, as a share of the whole population, is the closer match; reported
    alongside the narrower hard-state-only share so the gap between the two is visible rather
    than hidden inside one number."""
    union_share = (window["discouraged"] + window["n_belief_inactive"]) / n_agents
    return float(union_share.mean())


def discouraged_share_narrow(window: pd.DataFrame, n_agents: int) -> float:
    """The model's literal, proposal-defined discouragement -- capital exhaustion only, no
    belief-driven inactivity folded in. Reported as a secondary number, not the calibration
    target; see discouraged_share's docstring."""
    return float((window["discouraged"] / n_agents).mean())


def transport_budget_share(window: pd.DataFrame) -> float:
    """Cost of one effective search-trip excursion, as a share of one day's wage: total
    transport spend across the window divided by (total effective search trips in the window
    times the daily wage). Each model trip is treated as one search-day excursion, matching how
    the NHTS-derived empirical target conditions on a reported travel day -- both sides of the
    comparison are now conditional on a search trip actually happening and expressed in the
    same (daily) time unit, which the previous monthly-total-per-searcher formula was not. See
    DECISIONS.md, "transport_budget_share and its NHTS target were measuring two different
    things", for why this replaced the earlier definition.

    Undefined (nan), not a false zero, when nobody in the window ever took a search trip: the
    estimand is a cost conditional on a search trip happening, and there is no trip to
    condition on."""
    total_trips = window["total_trips"].sum()
    if total_trips == 0:
        return float("nan")
    total_spend = window["transport_spend"].sum()
    daily_wage = WAGE / DAYS_PER_MONTH
    return float(total_spend / (total_trips * daily_wage))


def long_term_share(window: pd.DataFrame) -> float:
    """Share of the currently-searching stock with an in-progress spell >= 12 months --
    mirrors QLFS's own stock-based definition exactly (D3), not a completed-spell statistic."""
    searchers_present = window["u"] > 0
    if not searchers_present.any():
        return 0.0
    share = window.loc[searchers_present, "n_long_term"] / window.loc[searchers_present, "u"]
    return float(share.mean())


def distance_gradient_slope(model: CityModel) -> float:
    """Percentage points of employment share per 10 percentile points of within-city
    travel-time rank to the nearest business district -- matched to what Baez and Kshirsagar
    (2026) Table 5b actually measures, not the km-based gradient originally (and wrongly)
    assumed; see DECISIONS.md, "The distance_gradient_slope moment was sourced to a table that
    doesn't exist." Agents are ranked by percentile of distance_to_cbd within this run's own
    population, mirroring the paper's own within-city ranking, so the two are directly
    comparable regardless of the arbitrary grid_size the model happens to use.

    Cross-sectional (the model's final state), not time-averaged -- see the module docstring.
    Undefined (returns nan) in the degenerate case where every agent shares the same distance
    (the MVM's grid_size=1, or a spatial config with n_townships=0), since a percentile rank
    over a constant is not meaningful and OLS on it is undefined."""
    seekers = list(model._seekers())
    n = len(seekers)
    if n < 2:
        return float("nan")

    distances = [a.distance_to_cbd for a in seekers]
    if max(distances) == min(distances):
        return float("nan")

    order = sorted(range(n), key=lambda i: distances[i])
    percentile_rank = [0.0] * n
    for rank, idx in enumerate(order):
        percentile_rank[idx] = 100.0 * rank / (n - 1)
    employed = [1.0 if a.state is SeekerState.EMPLOYED else 0.0 for a in seekers]

    slope = _ols_slope(percentile_rank, employed)
    return slope * 10 * 100  # per 10 percentile points, in percentage points of employment


def _ols_slope(x: list[float], y: list[float]) -> float:
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y, strict=True))
    var_x = sum((xi - mean_x) ** 2 for xi in x)
    if var_x == 0:
        return math.nan
    return cov / var_x
