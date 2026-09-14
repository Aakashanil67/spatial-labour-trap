"""Focused checks for the decision-ready candidate transport-estimate conversion logic
(scripts/build_transport_candidate_estimates.py). Pure unit tests -- no live microdata.
"""

from __future__ import annotations

import pandas as pd

from scripts.build_transport_candidate_estimates import (
    EXCURSION_BASES,
    FREQ_PRIMARY,
    driver_total,
    journey_total,
    leg_contribution,
)

ONE_DIRECTION = EXCURSION_BASES["one_direction"]
ROUND_TRIP = EXCURSION_BASES["round_trip"]


class TestLegContribution:
    def test_single_trip_one_direction_basis_is_unchanged(self):
        assert leg_contribution(1, 50, ONE_DIRECTION, FREQ_PRIMARY) == 50

    def test_single_trip_round_trip_basis_is_doubled(self):
        assert leg_contribution(1, 50, ROUND_TRIP, FREQ_PRIMARY) == 100

    def test_return_trip_one_direction_basis_is_halved(self):
        assert leg_contribution(2, 100, ONE_DIRECTION, FREQ_PRIMARY) == 50

    def test_return_trip_round_trip_basis_is_unchanged(self):
        assert leg_contribution(2, 100, ROUND_TRIP, FREQ_PRIMARY) == 100

    def test_weekly_divided_by_frequency_assumption(self):
        assert leg_contribution(3, 150, ONE_DIRECTION, FREQ_PRIMARY) == 30  # 150 / 5

    def test_per_year_is_unconvertible(self):
        assert leg_contribution(5, 270, ONE_DIRECTION, FREQ_PRIMARY) is None


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


class TestJourneyTotal:
    def test_single_resolved_leg(self):
        row = pd.Series(leg1_row(pay=1, cost=50))
        assert journey_total(row, ONE_DIRECTION, FREQ_PRIMARY) == 50

    def test_zero_fare_leg_contributes_nothing(self):
        row = pd.Series(leg1_row(pay=7, cost=8888))
        assert journey_total(row, ONE_DIRECTION, FREQ_PRIMARY) == 0

    def test_ambiguous_leg_makes_journey_unresolved(self):
        row = pd.Series(leg1_row(pay=1, cost=9999))
        assert journey_total(row, ONE_DIRECTION, FREQ_PRIMARY) is None

    def test_dnk_leg_makes_journey_unresolved(self):
        row = pd.Series(leg1_row(pay=8, cost=8888))
        assert journey_total(row, ONE_DIRECTION, FREQ_PRIMARY) is None

    def test_per_year_leg_makes_journey_unresolved(self):
        row = pd.Series(leg1_row(pay=5, cost=270))
        assert journey_total(row, ONE_DIRECTION, FREQ_PRIMARY) is None


class TestDriverTotal:
    def test_positive_code_resolved(self):
        row = pd.Series({"Q433bPay": 1, "Q434bCost": 80})
        assert driver_total(row, ONE_DIRECTION, FREQ_PRIMARY, scenario="A") == 80

    def test_numeric_zero_resolved_as_zero(self):
        row = pd.Series({"Q433bPay": 1, "Q434bCost": 0})
        assert driver_total(row, ONE_DIRECTION, FREQ_PRIMARY, scenario="A") == 0

    def test_code_5_scenario_a_is_nonresponse(self):
        row = pd.Series({"Q433bPay": 5, "Q434bCost": 8888})
        assert driver_total(row, ONE_DIRECTION, FREQ_PRIMARY, scenario="A") is None

    def test_code_5_scenario_b_is_legitimate_zero(self):
        row = pd.Series({"Q433bPay": 5, "Q434bCost": 8888})
        assert driver_total(row, ONE_DIRECTION, FREQ_PRIMARY, scenario="B") == 0

    def test_code_6_is_nonresponse_under_both_scenarios(self):
        row = pd.Series({"Q433bPay": 6, "Q434bCost": 8888})
        assert driver_total(row, ONE_DIRECTION, FREQ_PRIMARY, scenario="A") is None
        assert driver_total(row, ONE_DIRECTION, FREQ_PRIMARY, scenario="B") is None

    def test_ambiguous_cost_is_unresolved(self):
        row = pd.Series({"Q433bPay": 1, "Q434bCost": 9999})
        assert driver_total(row, ONE_DIRECTION, FREQ_PRIMARY, scenario="A") is None
