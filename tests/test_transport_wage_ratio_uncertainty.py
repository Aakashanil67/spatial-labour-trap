"""Focused checks for the stratified with-replacement PSU survey bootstrap
(scripts/build_transport_wage_ratio_uncertainty.py), which replaced a delete-1
jackknife withdrawn 2026-09-14 because it is not valid for a statistic containing a
weighted median. Pure unit tests against synthetic PSU/stratum structures -- no live
microdata.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.build_transport_wage_ratio_uncertainty import (
    build_psu_strata,
    cost_only_jackknife_reference,
    survey_bootstrap_ratio,
    weighted_mean,
    weighted_median,
)


class TestWeightedStats:
    def test_weighted_mean_equal_weights_matches_plain_mean(self):
        v = np.array([1.0, 2.0, 3.0, 4.0])
        w = np.ones(4)
        assert weighted_mean(v, w) == 2.5

    def test_weighted_mean_respects_unequal_weights(self):
        v = np.array([0.0, 10.0])
        w = np.array([3.0, 1.0])
        assert weighted_mean(v, w) == 2.5  # (0*3 + 10*1) / 4

    def test_weighted_median_equal_weights_matches_plain_median(self):
        v = np.array([1.0, 3.0, 2.0, 5.0, 4.0])
        w = np.ones(5)
        assert weighted_median(v, w) == 3.0

    def test_weighted_median_shifts_toward_heavier_weight(self):
        v = np.array([1.0, 2.0, 3.0])
        w = np.array([1.0, 1.0, 10.0])
        assert weighted_median(v, w) == 3.0


class TestBuildPsuStrata:
    def test_counts_psus_per_stratum(self):
        geog = pd.DataFrame({"Stratum": [1, 1, 1, 2, 2], "Psuno_seg": [10, 11, 12, 20, 21]})
        result = build_psu_strata(geog)
        assert len(result) == 5
        assert set(result.loc[result.stratum == 1, "n_h"]) == {3}
        assert set(result.loc[result.stratum == 2, "n_h"]) == {2}

    def test_deduplicates_repeated_household_rows(self):
        geog = pd.DataFrame({"Stratum": [1, 1, 1, 1], "Psuno_seg": [10, 10, 10, 11]})
        result = build_psu_strata(geog)
        assert len(result) == 2


def _synthetic_design(n_strata=3, psus_per_stratum=6, per_psu=5, cost_spread=1.0, wage_spread=10.0):
    """A design where cost and wage values vary by PSU (scalar integer ids, matching
    production's Psuno_seg), so both jackknife and bootstrap variance are nonzero and
    checkable."""
    rows_cost, rows_wage = [], []
    for h in range(n_strata):
        for k in range(psus_per_stratum):
            psu_id = h * 100 + k
            cost_val = 10.0 + cost_spread * (h + k)
            wage_val = 1000.0 + wage_spread * (h + k)
            for _ in range(per_psu):
                rows_cost.append(dict(value=cost_val, weight=1.0, psu=psu_id, stratum=h))
                rows_wage.append(dict(value=wage_val, weight=1.0, psu=psu_id, stratum=h))
    cost_df = pd.DataFrame(rows_cost)
    wage_df = pd.DataFrame(rows_wage)
    psu_strata = pd.DataFrame(
        {"stratum": h, "psu": h * 100 + k, "n_h": psus_per_stratum}
        for h in range(n_strata)
        for k in range(psus_per_stratum)
    )
    return cost_df, wage_df, psu_strata


class TestCostOnlyJackknifeReference:
    def test_zero_when_all_psus_identical(self):
        cost_df, _wage_df, psu_strata = _synthetic_design(cost_spread=0.0)
        se = cost_only_jackknife_reference(cost_df, psu_strata, daily_wage_fixed=200.0)
        assert se == pytest.approx(0.0, abs=1e-10)

    def test_positive_when_psus_vary(self):
        cost_df, _wage_df, psu_strata = _synthetic_design(cost_spread=5.0)
        se = cost_only_jackknife_reference(cost_df, psu_strata, daily_wage_fixed=200.0)
        assert se > 0.0

    def test_scales_with_daily_wage_denominator(self):
        # halving the (fixed) daily wage should exactly double the SE, since the
        # ratio is linear in 1/daily_wage for a fixed cost distribution
        cost_df, _wage_df, psu_strata = _synthetic_design(cost_spread=5.0)
        se_200 = cost_only_jackknife_reference(cost_df, psu_strata, daily_wage_fixed=200.0)
        se_100 = cost_only_jackknife_reference(cost_df, psu_strata, daily_wage_fixed=100.0)
        assert se_100 == pytest.approx(se_200 * 2)


class TestSurveyBootstrapRatio:
    def test_point_estimate_is_seed_independent(self):
        cost_df, wage_df, psu_strata = _synthetic_design()
        r1 = survey_bootstrap_ratio(cost_df, wage_df, psu_strata, n_boot=200, seed=1)
        r2 = survey_bootstrap_ratio(cost_df, wage_df, psu_strata, n_boot=200, seed=2)
        # the point estimate comes from the FULL sample, computed once, before any
        # resampling -- it must not depend on the bootstrap seed
        assert r1["point_estimate"] == r2["point_estimate"]
        assert r1["weighted_mean_cost_rand"] == r2["weighted_mean_cost_rand"]
        assert r1["weighted_median_monthly_wage_rand"] == r2["weighted_median_monthly_wage_rand"]

    def test_reproducible_with_same_seed(self):
        cost_df, wage_df, psu_strata = _synthetic_design()
        r1 = survey_bootstrap_ratio(cost_df, wage_df, psu_strata, n_boot=200, seed=7)
        r2 = survey_bootstrap_ratio(cost_df, wage_df, psu_strata, n_boot=200, seed=7)
        assert r1 == r2

    def test_zero_se_when_all_psus_identical(self):
        # every PSU has the same cost and wage value -> no resampling can move the
        # weighted mean or weighted median at all -> bootstrap SE must be exactly 0
        cost_df, wage_df, psu_strata = _synthetic_design(cost_spread=0.0, wage_spread=0.0)
        result = survey_bootstrap_ratio(cost_df, wage_df, psu_strata, n_boot=200, seed=1)
        assert result["bootstrap_se"] == 0.0
        assert result["n_distinct_replicate_medians"] == 1

    def test_fix_wage_holds_median_exactly_constant(self):
        cost_df, wage_df, psu_strata = _synthetic_design()
        result = survey_bootstrap_ratio(
            cost_df, wage_df, psu_strata, n_boot=200, seed=1, fix_wage=True
        )
        assert result["n_distinct_replicate_medians"] == 1

    def test_more_psu_variability_increases_se(self):
        low_cost, low_wage, psu_strata = _synthetic_design(cost_spread=1.0, wage_spread=1.0)
        high_cost, high_wage, _ = _synthetic_design(cost_spread=50.0, wage_spread=50.0)
        low_result = survey_bootstrap_ratio(low_cost, low_wage, psu_strata, n_boot=500, seed=1)
        high_result = survey_bootstrap_ratio(high_cost, high_wage, psu_strata, n_boot=500, seed=1)
        assert high_result["bootstrap_se"] > low_result["bootstrap_se"]

    def test_percentile_ci_contains_point_estimate_typically(self):
        # not a strict mathematical guarantee, but true for a well-behaved bootstrap
        # distribution -- a smoke test that the interval isn't degenerate or inverted
        cost_df, wage_df, psu_strata = _synthetic_design(cost_spread=3.0, wage_spread=20.0)
        result = survey_bootstrap_ratio(cost_df, wage_df, psu_strata, n_boot=500, seed=1)
        lo, mid, hi = (
            result["ci_95_lo_percentile"],
            result["point_estimate"],
            result["ci_95_hi_percentile"],
        )
        assert lo < mid < hi
