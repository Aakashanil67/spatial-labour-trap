"""Focused checks for scripts/build_qlfs_candidate_moments.py: the Kish design-effect
formula, stock/transition point estimates, and the household-cluster bootstrap's
structural properties. Pure unit tests against synthetic data -- no live microdata.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.build_qlfs_candidate_moments import (
    build_matched_panel,
    kish_se,
    restrict_working_age,
    stock_cluster_bootstrap,
    stock_point_estimates,
    transition_point_estimates,
)


class TestKishSe:
    def test_equal_weights_reduces_to_simple_random_sample_formula(self):
        w = np.ones(100)
        p = 0.3
        se = kish_se(p, w)
        assert se == pytest.approx(np.sqrt(p * (1 - p) / 100))

    def test_unequal_weights_inflate_se_above_equal_weight_case(self):
        w_equal = np.ones(100)
        w_unequal = np.concatenate([np.full(10, 5.0), np.full(90, 1.0)])
        p = 0.3
        assert kish_se(p, w_unequal) > kish_se(p, w_equal)


class TestRestrictWorkingAge:
    def test_excludes_ages_outside_15_64(self):
        df = pd.DataFrame({"Q14AGE": [10, 15, 40, 64, 65, 90]})
        kept = restrict_working_age(df, "Q14AGE")
        assert sorted(kept["Q14AGE"]) == [15, 40, 64]

    def test_boundary_ages_inclusive(self):
        df = pd.DataFrame({"Q14AGE": [14, 15, 64, 65]})
        kept = restrict_working_age(df, "Q14AGE")
        assert set(kept["Q14AGE"]) == {15, 64}

    def test_missing_age_filter_would_change_discouraged_share(self):
        """Regression fixture for Astra's review finding 1 (2026-09-14): STOCK_COLS
        previously omitted Q14AGE, so the stock calculation could not impose the 15-64
        filter it claimed to apply. This synthetic frame makes every 65+ respondent
        Discouraged and every 15-64 respondent Employed, so an unapplied age filter and
        a correctly applied one give maximally different, easily distinguished answers
        (0.5 vs 0.0) rather than a subtle numeric drift that could pass unnoticed."""
        rows = []
        for i in range(19):
            rows.append(
                dict(
                    Status=1,
                    Long_term_unempl=np.nan,
                    Weight=1.0,
                    UQNO=f"a{i}",
                    Stratum=0,
                    Q14AGE=30,
                )
            )
        # one unemployed 15-64 record so the working-age unemployed mask is non-empty
        rows.append(
            dict(Status=2, Long_term_unempl=1, Weight=1.0, UQNO="a19", Stratum=0, Q14AGE=30)
        )
        for i in range(20):
            rows.append(
                dict(
                    Status=3,
                    Long_term_unempl=np.nan,
                    Weight=1.0,
                    UQNO=f"b{i}",
                    Stratum=0,
                    Q14AGE=70,
                )
            )
        df = pd.DataFrame(rows)
        unrestricted = stock_point_estimates(df)
        restricted = stock_point_estimates(restrict_working_age(df, "Q14AGE"))
        assert unrestricted["discouraged_share"] == pytest.approx(0.5)
        assert restricted["discouraged_share"] == pytest.approx(0.0)
        assert restricted["n_expanded_lf"] == 20


def _synthetic_stock_df(n_strata=3, hh_per_stratum=8, people_per_hh=2):
    rows = []
    for h in range(n_strata):
        for k in range(hh_per_stratum):
            uqno = f"{h}-{k}"
            for p in range(people_per_hh):
                # alternate Employed/Unemployed/Discouraged deterministically
                status = [1, 2, 3][(h + k + p) % 3]
                if status != 2:
                    long_term = np.nan
                else:
                    long_term = 1 if (h + k + p) % 2 == 0 else 2
                rows.append(
                    dict(
                        Status=status,
                        Long_term_unempl=long_term,
                        Weight=1.0,
                        UQNO=uqno,
                        Stratum=h,
                    )
                )
    return pd.DataFrame(rows)


class TestStockPointEstimates:
    def test_shares_sum_correctly_within_expanded_labour_force(self):
        df = _synthetic_stock_df()
        result = stock_point_estimates(df)
        elf = df[df["Status"].isin([1, 2, 3])]
        unemployment_implied = 1 - result["discouraged_share"] - result["employment_share"]
        actual_unemployment = (elf["Status"] == 2).mean()
        assert unemployment_implied == pytest.approx(actual_unemployment)

    def test_n_matches_population_sizes(self):
        df = _synthetic_stock_df()
        result = stock_point_estimates(df)
        assert result["n_expanded_lf"] == len(df)  # every synthetic row is 1/2/3
        assert result["n_unemployed"] == (df["Status"] == 2).sum()


class TestStockClusterBootstrap:
    def test_zero_variance_when_every_cluster_identical(self):
        rows = []
        for h in range(2):
            for k in range(6):
                uqno = f"{h}-{k}"
                # one employed, one unemployed-long-term in every household, identically
                rows.append(
                    dict(Status=1, Long_term_unempl=np.nan, Weight=1.0, UQNO=uqno, Stratum=h)
                )
                rows.append(dict(Status=2, Long_term_unempl=1, Weight=1.0, UQNO=uqno, Stratum=h))
        df = pd.DataFrame(rows)
        boot = stock_cluster_bootstrap(df, n_boot=200, seed=1)
        assert boot["employment_share"].std(ddof=1) == pytest.approx(0.0, abs=1e-9)
        assert boot["long_term_share"].std(ddof=1) == pytest.approx(0.0, abs=1e-9)

    def test_bootstrap_mean_close_to_point_estimate(self):
        df = _synthetic_stock_df(n_strata=5, hh_per_stratum=20, people_per_hh=3)
        point = stock_point_estimates(df)
        boot = stock_cluster_bootstrap(df, n_boot=500, seed=1)
        assert boot["discouraged_share"].mean() == pytest.approx(
            point["discouraged_share"], abs=0.03
        )


def _synthetic_matched_panel():
    rows = []
    # unemployed at t0, half move to Employed at t1
    for i in range(20):
        status_q1 = 1 if i % 2 == 0 else 2
        rows.append(
            dict(
                Status_q4=2,
                Status_q1=status_q1,
                Q13GENDER_q4="M",
                Q13GENDER_q1="M",
                Q14AGE_q4=30,
                Q14AGE_q1=30,
                Weight_q4=1.0,
                UQNO=f"u{i}",
                Stratum_q4=0,
            )
        )
    # employed at t0, a quarter move to non-employed at t1
    for i in range(20):
        status_q1 = 2 if i % 4 == 0 else 1
        rows.append(
            dict(
                Status_q4=1,
                Status_q1=status_q1,
                Q13GENDER_q4="F",
                Q13GENDER_q1="F",
                Q14AGE_q4=25,
                Q14AGE_q1=25,
                Weight_q4=1.0,
                UQNO=f"e{i}",
                Stratum_q4=0,
            )
        )
    df = pd.DataFrame(rows)
    df["consistent"] = True
    return df


class TestTransitionPointEstimates:
    def test_u_to_e_matches_hand_count(self):
        matched = _synthetic_matched_panel()
        result = transition_point_estimates(matched, consistent_only=True)
        assert result["u_to_e_quarterly"] == pytest.approx(0.5)
        assert result["n_unemployed_origin"] == 20

    def test_e_to_non_e_matches_hand_count(self):
        matched = _synthetic_matched_panel()
        result = transition_point_estimates(matched, consistent_only=True)
        assert result["e_to_non_e_quarterly"] == pytest.approx(0.25)
        assert result["n_employed_origin"] == 20

    def test_monthly_sensitivity_is_smaller_than_quarterly(self):
        matched = _synthetic_matched_panel()
        result = transition_point_estimates(matched, consistent_only=True)
        assert (
            result["e_to_non_e_monthly_compounded_SENSITIVITY_ONLY"]
            < result["e_to_non_e_quarterly"]
        )


class TestBuildMatchedPanel:
    def test_consistent_flag_requires_stable_gender_and_small_age_change(self):
        q4 = pd.DataFrame(
            {
                "UQNO": ["a", "b", "c"],
                "PERSONNO": [1, 1, 1],
                "Status": [1, 1, 1],
                "Q13GENDER": ["M", "M", "M"],
                "Q14AGE": [30, 30, 30],
                "Weight": [1.0, 1.0, 1.0],
                "Stratum": [0, 0, 0],
            }
        )
        q1 = pd.DataFrame(
            {
                "UQNO": ["a", "b", "c"],
                "PERSONNO": [1, 1, 1],
                "Status": [1, 1, 1],
                "Q13GENDER": ["M", "F", "M"],  # b: gender flip
                "Q14AGE": [30, 30, 45],  # c: implausible age jump
                "Weight": [1.0, 1.0, 1.0],
                "Stratum": [0, 0, 0],
            }
        )
        matched = build_matched_panel(q4, q1)
        consistent = dict(zip(matched["UQNO"], matched["consistent"], strict=True))
        assert bool(consistent["a"])
        assert not consistent["b"]
        assert not consistent["c"]
