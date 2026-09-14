"""Focused checks for the stratified PSU-level jackknife
(scripts/build_transport_wage_ratio_uncertainty.py). Pure unit tests against
synthetic PSU/stratum structures -- no live microdata.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.build_transport_wage_ratio_uncertainty import (
    build_psu_strata,
    jackknife_ratio,
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
        geog = pd.DataFrame(
            {
                "Stratum": [1, 1, 1, 2, 2],
                "Psuno_seg": [10, 11, 12, 20, 21],
            }
        )
        result = build_psu_strata(geog)
        assert len(result) == 5
        assert set(result.loc[result.stratum == 1, "n_h"]) == {3}
        assert set(result.loc[result.stratum == 2, "n_h"]) == {2}

    def test_deduplicates_repeated_household_rows(self):
        # a household-level geog frame has one row per PSU per stratum even if many
        # people/records point to the same PSU -- drop_duplicates must collapse them
        geog = pd.DataFrame(
            {
                "Stratum": [1, 1, 1, 1],
                "Psuno_seg": [10, 10, 10, 11],
            }
        )
        result = build_psu_strata(geog)
        assert len(result) == 2


class TestJackknifeRatio:
    def _synthetic_design(self, n_strata=3, psus_per_stratum=4, per_psu=5):
        """A balanced synthetic design where cost and wage values are constant
        within a PSU, so dropping a PSU has a predictable, checkable effect. PSU ids
        are scalar integers (h*100+k), matching production's Psuno_seg -- a tuple id
        would break the vectorised `cost_psu == psu` comparison used in production."""
        rows_cost, rows_wage = [], []
        for h in range(n_strata):
            for k in range(psus_per_stratum):
                psu_id = h * 100 + k
                psu_value_cost = 10.0 + h + k  # varies by PSU so variance is nonzero
                psu_value_wage = 1000.0 + 10 * (h + k)
                for _ in range(per_psu):
                    rows_cost.append(dict(value=psu_value_cost, weight=1.0, psu=psu_id, stratum=h))
                    rows_wage.append(dict(value=psu_value_wage, weight=1.0, psu=psu_id, stratum=h))
        cost_df = pd.DataFrame(rows_cost)
        wage_df = pd.DataFrame(rows_wage)
        psu_strata = pd.DataFrame(
            {"stratum": h, "psu": h * 100 + k, "n_h": psus_per_stratum}
            for h in range(n_strata)
            for k in range(psus_per_stratum)
        )
        return cost_df, wage_df, psu_strata

    def test_point_estimate_matches_direct_weighted_calculation(self):
        cost_df, wage_df, psu_strata = self._synthetic_design()
        result = jackknife_ratio(cost_df, wage_df, psu_strata)
        expected_cost_mean = weighted_mean(
            cost_df["value"].to_numpy(), cost_df["weight"].to_numpy()
        )
        expected_wage_median = weighted_median(
            wage_df["value"].to_numpy(), wage_df["weight"].to_numpy()
        )
        assert result["weighted_mean_cost_rand"] == round(expected_cost_mean, 2)
        assert result["weighted_median_monthly_wage_rand"] == round(expected_wage_median, 2)
        assert result["point_estimate"] == round(
            expected_cost_mean / (expected_wage_median / 21.7), 4
        )

    def test_zero_variance_when_all_psus_identical(self):
        # every PSU has the exact same cost and wage value -> dropping any PSU
        # cannot change the reweighted mean/median at all -> SE must be exactly 0
        rows_cost, rows_wage = [], []
        for h in range(2):
            for k in range(3):
                psu_id = h * 100 + k
                for _ in range(4):
                    rows_cost.append(dict(value=50.0, weight=1.0, psu=psu_id, stratum=h))
                    rows_wage.append(dict(value=4000.0, weight=1.0, psu=psu_id, stratum=h))
        cost_df = pd.DataFrame(rows_cost)
        wage_df = pd.DataFrame(rows_wage)
        psu_strata = pd.DataFrame(
            {"stratum": h, "psu": h * 100 + k, "n_h": 3} for h in range(2) for k in range(3)
        )
        result = jackknife_ratio(cost_df, wage_df, psu_strata)
        assert result["jackknife_se"] == 0.0

    def test_more_psu_variability_increases_se(self):
        # a design where one stratum's PSUs vary a lot vs. a design where they don't
        low_var_cost, low_var_wage, psu_strata = self._synthetic_design(
            n_strata=2, psus_per_stratum=5, per_psu=3
        )
        low_result = jackknife_ratio(low_var_cost, low_var_wage, psu_strata)

        rows_cost, rows_wage = [], []
        for h in range(2):
            for k in range(5):
                psu_id = h * 100 + k
                psu_value_cost = 10.0 + 100 * (h + k)  # much larger spread across PSUs
                psu_value_wage = 1000.0 + 10 * (h + k)
                for _ in range(3):
                    rows_cost.append(dict(value=psu_value_cost, weight=1.0, psu=psu_id, stratum=h))
                    rows_wage.append(dict(value=psu_value_wage, weight=1.0, psu=psu_id, stratum=h))
        high_var_cost = pd.DataFrame(rows_cost)
        high_var_wage = pd.DataFrame(rows_wage)
        high_result = jackknife_ratio(high_var_cost, high_var_wage, psu_strata)

        assert high_result["jackknife_se"] > low_result["jackknife_se"]
