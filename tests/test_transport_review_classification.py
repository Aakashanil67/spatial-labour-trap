"""Focused checks for the 2026-09-14 transport-classifier corrections (see
data/review_v2/transport_definition.md): numeric-zero handling (a named payment
period with a reported cost of exactly R0 is a zero fare, not a positive cost) and
DNK-as-unresolved (a "do not know" payment period on one leg must not be overridden
by a positive cost on another leg into "fully costed"). Pure unit tests against the
classifier functions -- no live microdata required.
"""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.build_transport_review_tables import (
    UNRESOLVED_CLASSES,
    ZERO_CLASSES,
    classify_leg,
    journey_class,
    summarise_driver,
)

LEG1_SPEC = dict(
    mode="mode",
    mode_na=(99,),
    pay="pay",
    pay_zero=7,
    pay_dnk=8,
    pay_na=(99,),
    cost="cost",
    cost_na=8888,
    cost_unspec=9999,
)
LEG2_SPEC = dict(
    mode="mode",
    mode_na=(88, 99),
    pay="pay",
    pay_zero=7,
    pay_dnk=None,
    pay_na=(9,),
    cost="cost",
    cost_na=888,
    cost_unspec=999,
)


def leg_row(mode, pay, cost):
    return pd.Series(dict(mode=mode, pay=pay, cost=cost))


NA = "not_administered"


class TestNumericZeroLegClassification:
    def test_named_period_with_zero_cost_is_a_numeric_zero_fare(self):
        row = leg_row(mode=1, pay=1, cost=0)
        assert classify_leg(row, LEG1_SPEC) == "zero_fare_numeric"

    def test_do_not_pay_is_a_stated_zero_fare_not_numeric(self):
        row = leg_row(mode=1, pay=7, cost=8888)
        assert classify_leg(row, LEG1_SPEC) == "zero_fare_stated"

    def test_both_zero_classes_are_in_zero_classes(self):
        assert "zero_fare_numeric" in ZERO_CLASSES
        assert "zero_fare_stated" in ZERO_CLASSES

    def test_positive_cost_is_unaffected(self):
        row = leg_row(mode=1, pay=1, cost=17)
        assert classify_leg(row, LEG1_SPEC) == "positive_numeric"

    @pytest.mark.parametrize("leg2_pay_zero_cost", [888, 999])
    def test_leg2_convention_zero_cost_also_recognised(self, leg2_pay_zero_cost):
        # legs 2-4 use a different sentinel set (888/999) from leg 1 (8888/9999);
        # a genuine numeric zero must be recognised under either convention.
        row = leg_row(mode=1, pay=1, cost=0)
        assert classify_leg(row, LEG2_SPEC) == "zero_fare_numeric"


class TestJourneyLevelClassification:
    def test_positive_leg_plus_dnk_leg_is_partially_observed_not_fully_costed(self):
        classes = ["positive_numeric", "nonresponse_period_dnk", NA, NA]
        assert journey_class(classes) == "partially_observed_positive"

    def test_positive_leg_plus_ambiguous_leg_is_partially_observed(self):
        classes = ["positive_numeric", "ambiguous_unspecified_cost", NA, NA]
        assert journey_class(classes) == "partially_observed_positive"

    def test_all_positive_is_fully_costed(self):
        classes = ["positive_numeric", "positive_numeric", NA, NA]
        assert journey_class(classes) == "fully_costed_positive"

    def test_zero_fare_plus_positive_is_still_fully_costed(self):
        # a free leg alongside a paid leg is fully known, not partially observed
        classes = ["zero_fare_stated", "positive_numeric", NA, NA]
        assert journey_class(classes) == "fully_costed_positive"

    def test_mix_of_stated_and_numeric_zero_legs_is_zero(self):
        classes = ["zero_fare_stated", "zero_fare_numeric", NA, NA]
        assert journey_class(classes) == "zero"

    def test_all_dnk_is_nonresponse(self):
        classes = ["nonresponse_period_dnk", NA, NA, NA]
        assert journey_class(classes) == "nonresponse"

    def test_zero_leg_plus_dnk_leg_no_positive_is_ambiguous_not_zero(self):
        # the DNK leg's true cost is unknown -- it could have been paid -- so the
        # journey total is not confirmed zero even though one leg is a known zero
        classes = ["zero_fare_stated", "nonresponse_period_dnk", NA, NA]
        assert journey_class(classes) == "ambiguous"

    def test_no_legs_administered(self):
        classes = [NA] * 4
        assert journey_class(classes) == "no_legs_administered"

    def test_unresolved_classes_excludes_dnk(self):
        # DNK is handled as its own case in journey_class, not folded into the
        # generic UNRESOLVED_CLASSES tuple used for ambiguous/internal-inconsistency
        assert "nonresponse_period_dnk" not in UNRESOLVED_CLASSES


class TestDriverNumericZero:
    def test_numeric_zero_counted_as_legitimate_zero_not_positive(self):
        sub = pd.DataFrame(
            {
                "Q433bPay": [1, 2, 1, 5, 6],
                "Q434bCost": [0, 80, 200, 8888, 8888],
            }
        )
        result = summarise_driver(sub)
        assert result["legitimate_zero"] == 1
        assert result["usable_numeric_cost"] == 2
        assert result["fully_costed_positive"] == 2

    def test_all_zero_costs_none_positive(self):
        sub = pd.DataFrame({"Q433bPay": [1, 2], "Q434bCost": [0, 0]})
        result = summarise_driver(sub)
        assert result["legitimate_zero"] == 2
        assert result["usable_numeric_cost"] == 0
