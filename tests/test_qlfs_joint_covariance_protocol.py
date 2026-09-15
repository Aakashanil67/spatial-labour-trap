"""Synthetic acceptance fixtures for the joint stock-transition covariance protocol
(Astra `REVIEW_FOLLOWUP.md` deliverable 2). Pure unit tests against synthetic data -- no
live microdata, no dependency on `scripts/build_qlfs_candidate_moments.py`'s production
pipeline. See `data/review_v2/qlfs_joint_covariance_protocol.md` for the full spec these
fixtures check.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import scripts.qlfs_joint_covariance_protocol as jp
from scripts.qlfs_joint_covariance_protocol import joint_stock_transition_bootstrap

MOMENT_COLS = [
    "discouraged_share",
    "employment_share",
    "long_term_share",
    "u_to_e_quarterly",
    "e_to_non_e_quarterly",
]


def _stock_rows(households: list[str], stratum: int, status: int, long_term=np.nan):
    return [
        dict(Status=status, Long_term_unempl=long_term, Weight=1.0, UQNO=h, Stratum=stratum)
        for h in households
    ]


def _transition_rows(households: list[str], stratum: int, status_q4: int, status_q1: int):
    return [
        dict(
            Status_q4=status_q4,
            Status_q1=status_q1,
            Weight_q4=1.0,
            UQNO=h,
            Stratum_q4=stratum,
        )
        for h in households
    ]


_LT_PAD_STRATUM = 999999  # a dedicated singleton-household stratum: n_h=1, so
# np.random.choice(size=1, replace=True) always redraws that one household, guaranteeing
# a non-empty Long_term_unempl-eligible mask without affecting any other stratum's draw.
_LT_PAD = dict(Status=2, Long_term_unempl=1, Weight=1.0, UQNO="_lt_pad_hh", Stratum=_LT_PAD_STRATUM)


def _stock_frame(rows: list[dict]) -> pd.DataFrame:
    """Wraps stock fixture rows with a long-term-eligible pad record in its own singleton
    stratum, matching the pattern already needed for stock_point_estimates() in
    test_qlfs_candidate_moments.py -- long_term_share's weighted average raises
    ZeroDivisionError if no record anywhere has Long_term_unempl in {1, 2}."""
    return pd.DataFrame([*rows, _LT_PAD])


_ORIGIN_PADS = [
    # Each in its OWN singleton stratum (n_h=1 there), so np.random.choice always redraws
    # that one household -- guarantees both an employed-origin and an unemployed-origin
    # record always exist, regardless of the test's own one-sided fixture, avoiding the
    # same empty-mask crash on u_to_e_quarterly/e_to_non_e_quarterly that _LT_PAD avoids
    # for long_term_share. Two households in ONE shared stratum would not give this
    # guarantee (either could be the one drawn twice).
    dict(Status_q4=2, Status_q1=2, Weight_q4=1.0, UQNO="_u_origin_pad", Stratum_q4=999998),
    dict(Status_q4=1, Status_q1=1, Weight_q4=1.0, UQNO="_e_origin_pad", Stratum_q4=999997),
]


def _transition_frame(rows: list[dict]) -> pd.DataFrame:
    """Wraps transition fixture rows with the origin-population pad records above."""
    return pd.DataFrame([*rows, *_ORIGIN_PADS])


class TestOutputSchema:
    def test_returns_exactly_the_five_named_estimators(self):
        """Correct estimator labels: the joint replicate output columns must be exactly
        the five moments it claims to compute -- nothing renamed, nothing extra."""
        stock = _stock_frame(_stock_rows([f"s{i}" for i in range(10)], 0, 1))
        matched = _transition_frame(_transition_rows([f"s{i}" for i in range(10)], 0, 2, 1))
        boot = joint_stock_transition_bootstrap(stock, matched, n_boot=5, seed=1)
        assert list(boot.columns) == MOMENT_COLS

    def test_covariance_matrix_is_symmetric_and_positive_semidefinite(self):
        rng_stock = _stock_rows([f"a{i}" for i in range(20)], 0, 1) + _stock_rows(
            [f"a{i}" for i in range(20, 30)], 0, 3
        )
        rng_matched = _transition_rows([f"a{i}" for i in range(20)], 0, 1, 1) + _transition_rows(
            [f"a{i}" for i in range(20, 25)], 0, 2, 2
        )
        stock = _stock_frame(rng_stock)
        matched = _transition_frame(rng_matched)
        boot = joint_stock_transition_bootstrap(stock, matched, n_boot=300, seed=7)
        cov = boot[MOMENT_COLS].cov().to_numpy()
        assert np.allclose(cov, cov.T)
        eigvals = np.linalg.eigvalsh(cov)
        assert eigvals.min() >= -1e-10


class TestSharedHouseholdCovariance:
    def test_zero_induced_covariance_when_frames_share_no_households_and_no_stratum(self):
        """Households that never appear together in the same stratum are drawn by
        independent per-stratum lotteries, so a stock moment computed entirely from
        stratum 0 households and a transition moment computed entirely from stratum 1
        households should show ~zero sampling covariance -- a negative control."""
        stock = _stock_frame(
            _stock_rows([f"s{i}" for i in range(100)], 0, status=1)
            + _stock_rows([f"s{i}" for i in range(100, 150)], 0, status=3)
        )
        # Mixed q1 outcomes within stratum 1 (half succeed, half don't) so u_to_e_quarterly
        # actually varies replicate-to-replicate -- an all-success fixture gives it exactly
        # zero variance regardless of which households are drawn, making the correlation
        # undefined (0/0) rather than a meaningful zero.
        matched = _transition_frame(
            _transition_rows([f"t{i}" for i in range(100)], stratum=1, status_q4=2, status_q1=1)
            + _transition_rows(
                [f"t{i}" for i in range(100, 200)], stratum=1, status_q4=2, status_q1=2
            )
        )
        boot = joint_stock_transition_bootstrap(stock, matched, n_boot=4000, seed=12)
        corr = boot[["discouraged_share", "u_to_e_quarterly"]].corr().iloc[0, 1]
        assert abs(corr) < 0.15  # loose bound: Monte Carlo noise at 4,000 replicates, not exactly 0

    def test_nonzero_induced_covariance_when_households_are_shared(self):
        """The same households, in the same stratum, feed both frames with status values
        constructed so that a household drawn more often pushes discouraged_share AND
        u_to_e_quarterly in the same direction -- a positive control confirming the shared
        draw actually links the two estimators, not just the two data frames."""
        discouraged_households = [f"d{i}" for i in range(30)]
        other_households = [f"e{i}" for i in range(30)]
        stock = _stock_frame(
            _stock_rows(discouraged_households, 0, status=3)
            + _stock_rows(other_households, 0, status=1)
        )
        # In the transition frame, the SAME "discouraged_households" also have members who
        # transitioned unemployed->employed (u_to_e "success"), while "other_households"
        # supply unemployed->still-unemployed. A stratum draw favouring discouraged_households
        # this replicate therefore raises BOTH discouraged_share and u_to_e_quarterly together.
        matched = _transition_frame(
            _transition_rows(discouraged_households, 0, status_q4=2, status_q1=1)
            + _transition_rows(other_households, 0, status_q4=2, status_q1=2)
        )
        boot = joint_stock_transition_bootstrap(stock, matched, n_boot=4000, seed=21)
        corr = boot[["discouraged_share", "u_to_e_quarterly"]].corr().iloc[0, 1]
        assert corr > 0.3  # a real, detectable positive linkage, not Monte Carlo noise


class TestMultiplierSharing:
    def test_household_present_in_both_frames_gets_one_shared_multiplier(self, monkeypatch):
        """Directly checks the mechanism, not just its statistical consequence: patches the
        per-replicate household draw to a fixed, hand-chosen multiplier map and confirms
        both frames apply it identically to a shared household (h0), not two independent
        draws that happen to agree only in expectation."""
        stock = _stock_frame(_stock_rows(["h0"], 0, status=3) + _stock_rows(["h1"], 0, status=1))
        matched = _transition_frame(
            _transition_rows(["h0"], 0, status_q4=2, status_q1=1)
            + _transition_rows(["h2"], 0, status_q4=2, status_q1=2)
        )
        # Fixed map: h0 drawn 3x (shared by both frames), h1 drawn 1x (stock-only), the
        # long-term and origin pad households drawn 1x each (keep long_term_share and
        # e_to_non_e_quarterly computable -- this fixture has no employed-origin record of
        # its own), h2 drawn 0x (transition-only, not drawn this replicate).
        monkeypatch.setattr(
            jp,
            "_draw_multiplier_map",
            lambda strata, rng: {
                "h0": 3,
                "h1": 1,
                "_lt_pad_hh": 1,
                "_u_origin_pad": 1,
                "_e_origin_pad": 1,
            },
        )
        boot = joint_stock_transition_bootstrap(stock, matched, n_boot=1, seed=0)
        # Stock: elf = h0 (status 3, weight 3) + h1 (status 1, weight 1) + the pad household
        # (status 2, weight 1, drawn 1x per the fixed map) -> discouraged_share = 3/5 = 0.6,
        # by hand -- the pad household is Status=2 (Unemployed), which counts toward elf.
        assert boot.loc[0, "discouraged_share"] == pytest.approx(0.6)
        # Transition: unemployed_t0 = h0 (multiplier 3, moved to employed: 3 "successes")
        # + _u_origin_pad (multiplier 1, stayed unemployed: 0 successes) -> u_to_e_quarterly
        # = 3/4 = 0.75, by hand. h2 (multiplier 0, absent from the fixed map) contributes
        # nothing, confirming its non-draw removed it from the transition domain exactly as
        # it removed nothing extra from h0's weight.
        assert boot.loc[0, "u_to_e_quarterly"] == pytest.approx(0.75)
