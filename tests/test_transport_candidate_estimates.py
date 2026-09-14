"""Focused checks for the decision-ready candidate transport-estimate conversion logic
(scripts/build_transport_candidate_estimates.py). Pure unit tests -- no live microdata.

Covers the 2026-09-14 fix: frequency conversion (periods 3/4) must respect the
excursion definition exactly like periods 1/2 do, so round_trip == 2 * one_direction
for every period code, not just single/return trip.
"""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.build_transport_candidate_estimates import (
    driver_outcome,
    journey_outcome,
    leg_contribution,
)

FREQ = 5  # days/week, matches PRIMARY_FREQ_DAYS_PER_WEEK


class TestLegContributionConsistency:
    @pytest.mark.parametrize("pay,cost", [(1, 50), (2, 100), (3, 150), (4, 600)])
    def test_round_trip_is_exactly_twice_one_direction(self, pay, cost):
        one = leg_contribution(pay, cost, FREQ, "one_direction")
        two = leg_contribution(pay, cost, FREQ, "round_trip")
        assert two == pytest.approx(one * 2)

    def test_single_trip_one_direction_is_unchanged(self):
        assert leg_contribution(1, 50, FREQ, "one_direction") == 50

    def test_return_trip_one_direction_is_halved(self):
        assert leg_contribution(2, 100, FREQ, "one_direction") == 50

    def test_weekly_conversion_depends_on_excursion_basis(self):
        # this is the bug being fixed: previously week/month conversions ignored
        # the excursion basis entirely, so one_direction == round_trip for period 3/4
        one = leg_contribution(3, 150, FREQ, "one_direction")
        two = leg_contribution(3, 150, FREQ, "round_trip")
        assert one != two
        assert two == one * 2

    def test_monthly_conversion_uses_weeks_per_month_consistently(self):
        # freq=5 days/week -> 5*4.345=21.725 days/month, matching the wage side's
        # 21.7-day convention closely (not coincidentally: 21.7/4.345 ~= 5)
        contribution = leg_contribution(4, 21.725 * 2 * 10, FREQ, "round_trip")
        assert contribution == pytest.approx(10 * 2)

    def test_per_year_is_unconvertible(self):
        assert leg_contribution(5, 270, FREQ, "round_trip") is None


def leg1_row(mode=1, pay=1, cost=50):
    return {
        "Q429bMode1Trv": mode,
        "Q429b2Pay1": pay,
        "Q429b3Cost1": cost,
        "Q430bMode2Trv": 99,
        "Q430b2Pay2": 9,
        "Q430b3Cost2": 888,
        "Q431bMode3Trv": 99,
        "Q431b2Pay3": 9,
        "Q431b3Cost3": 888,
        "Q432bMode4Trv": 99,
        "Q432b2Pay4": 9,
        "Q432b3Cost4": 888,
    }


class TestJourneyOutcome:
    def test_single_resolved_leg_directly_supported(self):
        row = pd.Series(leg1_row(pay=1, cost=50))
        total, cls = journey_outcome(row, FREQ, "round_trip")
        assert total == 100
        assert cls == "directly_supported"

    def test_weekly_leg_requires_frequency(self):
        row = pd.Series(leg1_row(pay=3, cost=150))
        total, cls = journey_outcome(row, FREQ, "round_trip")
        assert cls == "requires_frequency"
        assert total is not None

    def test_zero_fare_leg_directly_supported_zero_total(self):
        row = pd.Series(leg1_row(pay=7, cost=8888))
        total, cls = journey_outcome(row, FREQ, "round_trip")
        assert total == 0
        assert cls == "directly_supported"

    def test_ambiguous_leg_unresolved(self):
        row = pd.Series(leg1_row(pay=1, cost=9999))
        total, cls = journey_outcome(row, FREQ, "round_trip")
        assert total is None
        assert cls == "unresolved"

    def test_dnk_leg_unresolved(self):
        row = pd.Series(leg1_row(pay=8, cost=8888))
        total, cls = journey_outcome(row, FREQ, "round_trip")
        assert cls == "unresolved"

    def test_per_year_leg_unresolved(self):
        row = pd.Series(leg1_row(pay=5, cost=270))
        total, cls = journey_outcome(row, FREQ, "round_trip")
        assert cls == "unresolved"


class TestDriverOutcome:
    def test_positive_code_directly_supported(self):
        row = pd.Series({"Q433bPay": 1, "Q434bCost": 80})
        total, cls = driver_outcome(row, FREQ, "round_trip", scenario="A")
        assert total == 160
        assert cls == "directly_supported"

    def test_weekly_code_requires_frequency(self):
        row = pd.Series({"Q433bPay": 3, "Q434bCost": 300})
        _total, cls = driver_outcome(row, FREQ, "round_trip", scenario="A")
        assert cls == "requires_frequency"

    def test_numeric_zero_directly_supported_zero(self):
        row = pd.Series({"Q433bPay": 1, "Q434bCost": 0})
        total, cls = driver_outcome(row, FREQ, "round_trip", scenario="A")
        assert total == 0
        assert cls == "directly_supported"

    def test_code_5_scenario_a_unresolved(self):
        row = pd.Series({"Q433bPay": 5, "Q434bCost": 8888})
        total, cls = driver_outcome(row, FREQ, "round_trip", scenario="A")
        assert total is None
        assert cls == "unresolved"

    def test_code_5_scenario_b_directly_supported_zero(self):
        row = pd.Series({"Q433bPay": 5, "Q434bCost": 8888})
        total, cls = driver_outcome(row, FREQ, "round_trip", scenario="B")
        assert total == 0
        assert cls == "directly_supported"

    def test_code_6_unresolved_under_both_scenarios(self):
        row = pd.Series({"Q433bPay": 6, "Q434bCost": 8888})
        assert driver_outcome(row, FREQ, "round_trip", "A")[1] == "unresolved"
        assert driver_outcome(row, FREQ, "round_trip", "B")[1] == "unresolved"

    def test_ambiguous_cost_unresolved(self):
        row = pd.Series({"Q433bPay": 1, "Q434bCost": 9999})
        assert driver_outcome(row, FREQ, "round_trip", "A")[1] == "unresolved"
