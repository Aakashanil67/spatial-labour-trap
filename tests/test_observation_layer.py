"""Independent fixtures for scripts/observation_layer.py, covering the timing and edge cases
Astra's COMPLETION_REVIEW.md identified: the observation-point/credited-after-measurement
convention, the k=0 vs. cumulative-active distinction, empty traveller-months, zero-cost vs.
non-traveller, the corrected worked-example arithmetic, and the counterexample showing
equal-person and trip-weighted are not a lower/upper bound pair."""

from __future__ import annotations

import pytest

from scripts.observation_layer import (
    classify_observation,
    classify_trace,
    cumulative_active_months,
    episode_clock,
    long_term_candidate_share,
    transport_person_window_estimate,
)


class TestClassifyObservation:
    def test_employed_is_e(self):
        assert classify_observation("EMPLOYED", belief_inactive_this_step=False) == "E"
        # belief_inactive_this_step is meaningless once EMPLOYED -- must not affect the result
        assert classify_observation("EMPLOYED", belief_inactive_this_step=True) == "E"

    def test_hard_discouraged_is_always_d(self):
        assert classify_observation("DISCOURAGED", belief_inactive_this_step=False) == "D"
        assert classify_observation("DISCOURAGED", belief_inactive_this_step=True) == "D"

    def test_searching_with_a_trip_is_u(self):
        assert classify_observation("SEARCHING", belief_inactive_this_step=False) == "U"

    def test_searching_with_zero_trips_is_d(self):
        assert classify_observation("SEARCHING", belief_inactive_this_step=True) == "D"

    def test_unrecognised_state_raises(self):
        with pytest.raises(ValueError):
            classify_observation("RETIRED", belief_inactive_this_step=False)

    def test_classify_trace_applies_rowwise(self):
        rows = [
            dict(state="SEARCHING", belief_inactive_this_step=False),
            dict(state="SEARCHING", belief_inactive_this_step=True),
            dict(state="EMPLOYED", belief_inactive_this_step=False),
            dict(state="DISCOURAGED", belief_inactive_this_step=False),
        ]
        assert classify_trace(rows) == ["U", "D", "E", "D"]


# The DECISIONS_PENDING.md Question 5 worked example: 3 months active search, a 2-month
# pause, then 4 more months active search.
WORKED_EXAMPLE = ["U", "U", "U", "D", "D", "U", "U", "U", "U"]


class TestEpisodeClock:
    def test_k0_matches_the_worked_example_table(self):
        """k=0: strict, any pause of >0 immediately ends the episode. The table's naive
        (non-offset) reading reports 4 at the end of this 9-step sequence; under
        episode_clock()'s credited-after-measurement convention (preserved from
        months_jobless, see the module docstring), the observation AT the 9th step also
        reads 4 here -- the offset and the mid-sequence restart happen to cancel out in this
        specific example (the restarted episode's own first D-step is itself credited 0,
        matching the very first step's convention, so the 4 U-steps from the restart onward
        read 1,2,3,4)."""
        result = episode_clock(WORKED_EXAMPLE, k=0)
        assert result == [0, 1, 2, 0, 0, 1, 2, 3, 4]

    def test_k_infinity_is_the_naive_count_minus_one(self):
        """k=infinity: the episode survives any gap. The table's naive reading is 9 (every
        step counted, including the current one); episode_clock()'s credited-after
        convention reports one less at each step, since the observation at step N credits
        only the N-1 PRIOR completed steps of the episode, matching months_jobless's own
        'reads 11 at step 12' convention exactly."""
        result = episode_clock(WORKED_EXAMPLE, k=10**9)
        assert result == [0, 1, 2, 3, 4, 5, 6, 7, 8]

    def test_k1_tolerates_a_single_month_gap_but_not_two(self):
        result = episode_clock(WORKED_EXAMPLE, k=1)
        # gap_run reaches 2 at the second consecutive D (step index 4), which exceeds k=1 ->
        # episode restarts there, one step later than k=0's restart (which triggers at the
        # FIRST D already, since gap_run=1 > k=0).
        assert result == [0, 1, 2, 3, 0, 1, 2, 3, 4]

    def test_k3_never_exceeds_tolerance_in_this_example_so_behaves_like_k_infinity(self):
        result = episode_clock(WORKED_EXAMPLE, k=3)
        assert result == episode_clock(WORKED_EXAMPLE, k=10**9)

    def test_employment_resets_the_clock_to_none_then_a_fresh_episode(self):
        cats = ["U", "U", "E", "U", "U"]
        result = episode_clock(cats, k=0)
        assert result == [0, 1, None, 0, 1]

    def test_negative_k_is_rejected(self):
        with pytest.raises(ValueError):
            episode_clock(["U"], k=-1)

    def test_unrecognised_category_is_rejected(self):
        with pytest.raises(ValueError):
            episode_clock(["Q"], k=0)


class TestCumulativeActiveMonths:
    def test_worked_example_matches_the_decisions_pending_table_minus_one(self):
        """The table's naive reading is 7 (only the 3+4=7 active/U months counted, ignoring
        the 2 pause months entirely). Under the same credited-after convention as
        episode_clock(), the observation at the 9th (last) step reports 6 -- one less, for
        the same reason episode_clock()'s k=infinity case reports 8 instead of 9."""
        result = cumulative_active_months(WORKED_EXAMPLE)
        assert result == [0, 1, 2, 3, 3, 3, 4, 5, 6]

    def test_is_a_distinct_estimator_from_every_episode_clock_k_in_this_example(self):
        """DECISIONS_PENDING.md Question 5's own point: the pause-tolerance family spans 4
        to 9 (naively) and never produces 7 in this specific example -- confirmed here on
        the actual implementations, at the final (9th) step, not merely asserted from the
        hand-derived table. Astra's COMPLETION_REVIEW.md correctly notes this does not prove
        no k can ever coincide with cumulative-active on ANY path -- only that they differ on
        THIS one, which is all this test claims."""
        cumulative_final = cumulative_active_months(WORKED_EXAMPLE)[-1]
        for k in (0, 1, 3, 10**9):
            assert episode_clock(WORKED_EXAMPLE, k=k)[-1] != cumulative_final

    def test_employment_resets_to_none_then_zero(self):
        cats = ["U", "U", "E", "D", "U"]
        result = cumulative_active_months(cats)
        assert result == [0, 1, None, 0, 0]

    def test_d_steps_are_never_counted_but_do_not_reset(self):
        cats = ["U", "D", "D", "D", "U"]
        result = cumulative_active_months(cats)
        # step1 U: credit 0, then completed->1. step2 D: credit 1 (unchanged). step3 D:
        # credit 1. step4 D: credit 1. step5 U: credit 1, then completed->2.
        assert result == [0, 1, 1, 1, 1]


class TestLongTermCandidateShare:
    def test_shares_computed_only_over_the_u_d_stock_not_employed_observations(self):
        durations = [0, 15, None, 3, 20]
        cats = ["U", "D", "E", "U", "D"]
        result = long_term_candidate_share(durations, cats, threshold_months=12)
        assert result["n_stock"] == 4  # excludes the one E observation
        assert result["n_long_term"] == 2  # the 15 and the 20
        assert result["share"] == pytest.approx(0.5)

    def test_empty_stock_returns_none_share(self):
        result = long_term_candidate_share([None], ["E"], threshold_months=12)
        assert result["share"] is None
        assert result["n_stock"] == 0

    def test_mismatched_lengths_raise(self):
        with pytest.raises(ValueError):
            long_term_candidate_share([0, 1], ["U"], threshold_months=12)


class TestTransportPersonWindowEstimate:
    def test_worked_example_matches_astras_corrected_arithmetic(self):
        """The three-agent, two-month fixture from observation_estimation_proposal.md
        Section 4, corrected per Astra's COMPLETION_REVIEW.md item 4: month 1 total is
        30+30+0=... using the SAME per-agent-mean-then-average-across-agents construction,
        the exact equal-month figure is 55/6 (~9.166667), not the previously miscomputed
        9.165 (premature rounding of the per-month figures before averaging them)."""
        records = [
            # Month 1: A (3 trips, 10 each), B (1 trip, 30), C (2 trips, 0 each -- zero-cost)
            dict(step=1, agent_id="A", spend=30, trips=3),
            dict(step=1, agent_id="B", spend=30, trips=1),
            dict(step=1, agent_id="C", spend=0, trips=2),
            # Month 2: A (1 trip, 10) and C (2 trips, 0) travel; B does not travel at all
            dict(step=2, agent_id="A", spend=10, trips=1),
            dict(step=2, agent_id="C", spend=0, trips=2),
        ]
        result = transport_person_window_estimate(
            records, window_steps=[1, 2], weighting="equal_person"
        )
        assert result["estimate"] == pytest.approx(55 / 6, abs=1e-9)
        assert result["n_months_used"] == 2
        assert result["n_months_empty"] == 0

    def test_zero_cost_traveller_is_included_distinct_from_a_non_traveller(self):
        """A zero-cost traveller (trips>=1, spend==0) contributes a real 0 to its month's
        per-agent mean and keeps that month from being 'empty'; a non-traveller (absent from
        traveller_records for that step) contributes nothing and, if it were the ONLY agent
        that step, would make the month empty (excluded), not zero."""
        records_with_zero_cost_traveller = [dict(step=1, agent_id="X", spend=0.0, trips=2)]
        result = transport_person_window_estimate(
            records_with_zero_cost_traveller, window_steps=[1], weighting="equal_person"
        )
        assert result["estimate"] == pytest.approx(0.0)
        assert result["n_months_used"] == 1
        assert result["n_months_empty"] == 0

    def test_empty_traveller_month_is_excluded_not_treated_as_zero(self):
        records = [dict(step=1, agent_id="A", spend=10, trips=1)]
        result = transport_person_window_estimate(
            records, window_steps=[1, 2, 3], weighting="equal_person"
        )
        assert result["estimate"] == pytest.approx(10.0)  # only step 1 contributes
        assert result["n_months_used"] == 1
        assert result["n_months_empty"] == 2

    def test_all_months_empty_returns_none_estimate(self):
        result = transport_person_window_estimate([], window_steps=[1, 2], weighting="equal_person")
        assert result["estimate"] is None
        assert result["n_months_empty"] == 2

    def test_trips_less_than_one_is_rejected(self):
        with pytest.raises(ValueError):
            transport_person_window_estimate(
                [dict(step=1, agent_id="A", spend=0, trips=0)],
                window_steps=[1],
                weighting="equal_person",
            )

    def test_unrecognised_weighting_is_rejected(self):
        with pytest.raises(ValueError):
            transport_person_window_estimate(
                [dict(step=1, agent_id="A", spend=1, trips=1)], window_steps=[1], weighting="bogus"
            )

    def test_astras_counterexample_equal_person_and_trip_weighted_can_coincide(self):
        """COMPLETION_REVIEW.md item 4's counterexample: monthly trip counts 1, 2, 3 with
        constant per-trip costs 0, 100, 0 give equal-person and trip-weighted means that
        coincide (both 100/3), demonstrating neither can be relied on as a uniform
        lower/upper bound on the other -- confirmed here numerically, not merely asserted in
        prose. (A true weekly-inclusion-weighted estimate could still fall outside this
        shared value under a specific within-month trip-timing schedule, per Astra's second,
        schedule-dependent counterexample -- not reproduced here since it requires
        information (which week within the month each trip fell in) this estimator does not
        use or claim to use)."""
        records = [
            dict(step=1, agent_id="A", spend=0, trips=1),
            dict(step=1, agent_id="B", spend=200, trips=2),
            dict(step=1, agent_id="C", spend=0, trips=3),
        ]
        equal_person = transport_person_window_estimate(
            records, window_steps=[1], weighting="equal_person"
        )
        trip_weighted = transport_person_window_estimate(
            records, window_steps=[1], weighting="trip_weighted"
        )
        assert equal_person["estimate"] == pytest.approx(100 / 3)
        assert trip_weighted["estimate"] == pytest.approx(100 / 3)

    def test_trip_weighted_is_not_uniformly_an_upper_bound(self):
        """COMPLETION_REVIEW.md item 4: the plan's original 'lower bound = equal-person,
        upper bound = trip-weighted' language is false even in the plan's OWN two-person
        fixture (costs 10 and 30, trip counts 3 and 1): person-mean 20, trip-weighted mean
        15 -- trip-weighted is LOWER here, not higher."""
        records = [
            dict(step=1, agent_id="A", spend=30, trips=3),  # 3 trips at 10 each
            dict(step=1, agent_id="B", spend=30, trips=1),  # 1 trip at 30
        ]
        equal_person = transport_person_window_estimate(
            records, window_steps=[1], weighting="equal_person"
        )
        trip_weighted = transport_person_window_estimate(
            records, window_steps=[1], weighting="trip_weighted"
        )
        assert equal_person["estimate"] == pytest.approx(20.0)
        assert trip_weighted["estimate"] == pytest.approx(15.0)
        assert trip_weighted["estimate"] < equal_person["estimate"]
