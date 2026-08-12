"""Recovers the matching function's efficiency `a` from a completed run's (u, v, m) series
(locked commitment 1: `a` is fitted, never imposed). Neighbourhood matching within a fixed
radius, on a fixed grid, with a fixed number of firm nodes, has no particular reason to be
constant-returns-to-scale -- and if the true degree of returns differs between two
configurations being compared (frictional vs frictionless, or across a policy experiment where
vacancies respond endogenously), a difference in the fitted `a` mixes a genuine efficiency
change with pure misspecification error from evaluating the wrong functional form. The
unconstrained fit is reported first; the CRS-constrained `a` is the headline number only once
constant returns has actually been tested, not assumed. See DECISIONS.md, "The matching-function
fit tests constant returns before assuming it."

The Wald test uses Newey-West (HAC) standard errors, not ordinary OLS ones. `u_t`, `v_t` and
`m_t` are a single run's own time series -- they evolve smoothly period to period, not as iid
draws, so treating consecutive periods as independent observations understates the true
standard errors and makes the Wald test overconfident, exactly the "what population the SQ1
interval is over" class of mistake the build plan's own uncertainty-objects note warns about
for this kind of within-run inference (see DECISIONS.md). The lag count follows Newey and
West's own automatic rule, `floor(4*(T/100)**(2/9))`, not a fixed number picked by eye.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm


@dataclass(frozen=True)
class MatchingFit:
    b_u: float  # unemployment elasticity, unconstrained fit
    b_v: float  # vacancy elasticity, unconstrained fit
    returns_to_scale: float  # b_u + b_v
    wald_pvalue: float  # H0: b_u + b_v == 1 (constant returns)
    crs_rejected: bool  # wald_pvalue < alpha
    a_unconstrained: float  # exp(intercept) from the unconstrained fit -- not the headline
    a_constrained: float  # from the CRS-restricted fit -- the headline number, if CRS holds
    phi_constrained: (
        float  # matching elasticity w.r.t. u under CRS -- dmp.py's phi, fitted not assumed
    )
    n_obs: int


def fit_matching_function(window: pd.DataFrame, alpha: float = 0.05) -> MatchingFit:
    """Fits `log m = log a + b_u log u + b_v log v` by OLS on this window's own (u, v, m)
    series, Wald-tests `b_u + b_v = 1`, then separately fits the CRS-constrained form
    `log(m/v) = log a + b_u log(u/v)` (b_v = 1 - b_u substituted in, leaving one regressor).
    Both fits use the same rows; periods with zero unemployment, zero vacancies or zero
    matches are dropped first since their logs are undefined -- not treated as zero matching,
    which would badly bias the elasticity estimates towards the corner."""
    usable = window[(window["u"] > 0) & (window["v"] > 0) & (window["m"] > 0)]
    n_obs = len(usable)
    if n_obs < 3:
        raise ValueError(
            f"only {n_obs} usable (u>0, v>0, m>0) periods in this window -- need at least 3 "
            "to fit two slopes and an intercept."
        )

    log_u = np.log(usable["u"].to_numpy())
    log_v = np.log(usable["v"].to_numpy())
    log_m = np.log(usable["m"].to_numpy())

    maxlags = max(1, int(np.floor(4 * (n_obs / 100) ** (2 / 9))))
    unconstrained = sm.OLS(log_m, sm.add_constant(np.column_stack([log_u, log_v]))).fit(
        cov_type="HAC", cov_kwds={"maxlags": maxlags}
    )
    intercept, b_u, b_v = unconstrained.params
    wald = unconstrained.f_test("x1 + x2 = 1")
    wald_pvalue = float(np.asarray(wald.pvalue).item())

    constrained = sm.OLS(log_m - log_v, sm.add_constant(log_u - log_v)).fit()
    log_a_constrained, phi_constrained = constrained.params

    return MatchingFit(
        b_u=float(b_u),
        b_v=float(b_v),
        returns_to_scale=float(b_u + b_v),
        wald_pvalue=wald_pvalue,
        crs_rejected=wald_pvalue < alpha,
        a_unconstrained=float(np.exp(intercept)),
        a_constrained=float(np.exp(log_a_constrained)),
        phi_constrained=float(phi_constrained),
        n_obs=n_obs,
    )
