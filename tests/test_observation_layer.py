"""Independent fixtures for scripts/observation_layer.py, covering the timing and edge cases
Astra's COMPLETION_REVIEW.md identified: the observation-point/credited-after-measurement
convention, the k=0 vs. cumulative-active distinction, empty traveller-months, zero-cost vs.
non-traveller, the corrected worked-example arithmetic, and the counterexample showing
equal-person and trip-weighted are not a lower/upper bound pair."""

from __future__ import annotations

import random

import pytest

from scripts.observation_layer import (
    StreamingEpisodeClockState,
    StreamingMonthlySummary,
    StreamingTransportSummary,
    classify_observation,
    classify_trace,
    cumulative_active_months,
    episode_clock,
    long_term_candidate_share,
    long_term_candidate_share_monthly,
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
    """CORRECTED 2026-09-15 (Astra's REVIEW_FOLLOWUP.md F1): episode_clock() previously let a
    D observation open a fresh episode, crediting search history that was never earned by
    actually searching. Every fixture below is derived independently (by hand, following only
    "an episode opens on U, tolerates up to k consecutive D since its last U, and credits
    completed PRIOR steps of the CURRENT episode") rather than by asking the implementation
    what it currently returns -- the failure mode F1 warned against."""

    def test_k0_matches_the_corrected_worked_example(self):
        """k=0: any D closes the episode immediately. U,U,U,D,D,U,U,U,U (3 active, 2-month
        pause, 4 active) must read 0,1,2,None,None,0,1,2,3 -- the two D steps have NO
        episode open (neither the old one, closed at the first D, nor a new one: D cannot
        open an episode), and the resuming U on step 6 (index 5) starts a brand-new episode
        at 0, not a continuation of anything."""
        result = episode_clock(WORKED_EXAMPLE, k=0)
        assert result == [0, 1, 2, None, None, 0, 1, 2, 3]

    def test_k_infinity_survives_any_gap(self):
        """k=infinity: once an episode is open (by a U), it survives any subsequent D run,
        so this example is UNAFFECTED by the F1 fix (there is always an open episode by the
        time the D's occur) -- included as a regression check that the fix did not disturb
        the already-correct infinite-tolerance case."""
        result = episode_clock(WORKED_EXAMPLE, k=10**9)
        assert result == [0, 1, 2, 3, 4, 5, 6, 7, 8]

    def test_k1_tolerates_a_gap_of_exactly_one_but_not_two(self):
        """The 2-month pause exceeds k=1's tolerance (a gap of 2 > 1), so the episode closes
        on the second D and the resuming U restarts at 0."""
        result = episode_clock(WORKED_EXAMPLE, k=1)
        assert result == [0, 1, 2, 3, None, 0, 1, 2, 3]

    def test_k3_tolerates_the_2_month_gap_so_behaves_like_k_infinity_here(self):
        result = episode_clock(WORKED_EXAMPLE, k=3)
        assert result == episode_clock(WORKED_EXAMPLE, k=10**9)

    def test_gap_of_exactly_k_survives(self):
        """A single U, then exactly k consecutive D's, then a U: the episode must survive
        (a gap of exactly k is tolerated, not just gaps strictly less than k)."""
        for k in (0, 1, 2, 5):
            cats = ["U"] + ["D"] * k + ["U"]
            result = episode_clock(cats, k=k)
            assert result[0] == 0
            assert result[1:-1] == list(range(1, k + 1))  # each D credited, episode open
            assert result[-1] == k + 1  # the returning U continues the SAME episode

    def test_gap_of_k_plus_one_closes_the_episode(self):
        """One more consecutive D than the tolerance closes the episode; the next U starts a
        fresh one at 0, not a continuation."""
        for k in (0, 1, 2, 5):
            cats = ["U"] + ["D"] * (k + 1) + ["U"]
            result = episode_clock(cats, k=k)
            assert result[-2] is None  # the (k+1)-th D itself closes the episode
            assert result[-1] == 0  # the next U opens a brand-new episode

    def test_initial_d_with_no_prior_episode_is_undefined(self):
        """A leading D, before any U has ever occurred, must read None -- it cannot credit
        search history that was never earned by searching. The requested [D, U*12] fixture."""
        cats = ["D"] + ["U"] * 12
        result = episode_clock(cats, k=0)
        assert result[0] is None
        assert result[1:] == list(range(12))  # 0..11, the episode opened fresh at the U

    def test_repeated_gaps_each_start_a_fresh_episode_under_k0(self):
        cats = ["U", "D", "U", "D", "U"]
        result = episode_clock(cats, k=0)
        assert result == [0, None, 0, None, 0]

    def test_e_then_d_then_u_has_no_episode_during_the_d(self):
        """Employment resets the clock to None; the immediately following D has no episode to
        belong to either (D cannot open one); only the U opens a fresh episode."""
        cats = ["E", "D", "U"]
        result = episode_clock(cats, k=3)
        assert result == [None, None, 0]

    def test_employment_resets_the_clock_to_none_then_a_fresh_episode(self):
        cats = ["U", "U", "E", "U", "U"]
        result = episode_clock(cats, k=0)
        assert result == [0, 1, None, 0, 1]

    def test_12_month_threshold_is_not_reached_until_the_13th_consecutive_u(self):
        """A leading D followed by twelve U observations reads 11 at the 12th (final) U, per
        the credited-after-measurement convention (F1's own worked example in
        REVIEW_FOLLOWUP.md: 'only eleven prior active-search months have been completed').
        Reaching the >=12 long-term threshold needs a 13th consecutive U, which reads 12."""
        twelve_us = ["D"] + ["U"] * 12
        result = episode_clock(twelve_us, k=0)
        assert result[-1] == 11  # 12th U: only 11 PRIOR completed active steps credited
        thirteen_us = ["D"] + ["U"] * 13
        result13 = episode_clock(thirteen_us, k=0)
        assert result13[-1] == 12  # 13th U: now >= the 12-month long-term threshold

    def test_negative_k_is_rejected(self):
        with pytest.raises(ValueError):
            episode_clock(["U"], k=-1)

    def test_unrecognised_category_is_rejected(self):
        with pytest.raises(ValueError):
            episode_clock(["Q"], k=0)


class TestWindowSlicingMustHappenAfterClockComputation:
    """F3 (2026-09-15, Astra's REVIEW_FOLLOWUP.md): a regression guard against the exact
    anti-pattern found in scripts/demo_observation_layer_run.py -- trimming an agent's trace
    to a measurement window BEFORE computing episode_clock()/cumulative_active_months()
    silently resets any episode already in progress at the window's start. These functions
    are pure and have no notion of a "window" themselves; the guard is that CALLERS must
    compute on the full history first and select observations afterward, demonstrated here
    exactly the way REVIEW_FOLLOWUP.md's own fixture does."""

    def test_full_history_then_slice_disagrees_with_slice_then_compute(self):
        full_history = ["U"] * 20
        full_result = episode_clock(full_history, k=0)
        assert full_result[-1] == 19  # 20 uninterrupted U's: credited 19 prior steps

        trimmed_first = episode_clock(full_history[-5:], k=0)
        assert trimmed_first[-1] == 4  # WRONG workflow: resets the episode at the window edge
        assert full_result[-5:][-1] != trimmed_first[-1]  # the two workflows disagree

        # CORRECT workflow: slice the ALREADY-COMPUTED full-history result, not the input.
        correctly_windowed = full_result[-5:]
        assert correctly_windowed[-1] == 19  # matches computing on the full history throughout

    def test_full_replay_and_incremental_chunked_processing_agree_exactly(self):
        """A second way to state the same requirement: processing an agent's history in
        chronological chunks (as a streaming collector might, to avoid holding a full trace in
        memory -- see the validation manifest's storage discussion) must reproduce full-replay
        results exactly, PROVIDED the running episode state (start/last_u analogues) carries
        across chunk boundaries. episode_clock() itself is stateless per call, so this test
        documents the CONTRACT a future streaming collector must satisfy: concatenating
        clock outputs from repeated full-history calls on growing prefixes reproduces the
        one-shot full-history call at every point, chunk boundaries included."""
        history = ["U", "U", "D", "D", "U", "U", "U", "D", "U", "U"]
        one_shot = episode_clock(history, k=1)
        # Simulate chunked processing: recompute from scratch on each growing prefix (what a
        # correct streaming collector's cheap summary must be equivalent to) and confirm every
        # prefix's LAST value matches the one-shot computation at that same index -- i.e. no
        # information from steps beyond the prefix ever influences an earlier reading.
        for end in range(1, len(history) + 1):
            prefix_result = episode_clock(history[:end], k=1)
            assert prefix_result[-1] == one_shot[end - 1]


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
    """CORRECTED 2026-09-15 (Astra's REVIEW_FOLLOWUP.md F2): the QLFS Long_term_unempl
    target's eligible universe is Status=2 (this project's U) only -- verified live against
    the 2026-Q1 extract (all 7,502 age-15-64 eligible records have Status=2, none
    Discouraged). long_term_candidate_share() must therefore be U-only, not U+D."""

    def test_shares_computed_only_over_u_not_d_or_employed_observations(self):
        durations = [0, 15, None, 3, 20]
        cats = ["U", "D", "E", "U", "D"]
        result = long_term_candidate_share(durations, cats, threshold_months=12)
        assert result["n_stock"] == 2  # only the two U observations (indices 0 and 3)
        assert result["n_long_term"] == 0  # neither U observation (0, 3) reaches 12
        assert result["share"] == pytest.approx(0.0)

    def test_counterexample_one_u_at_12_and_one_d_at_0_reads_1_not_0_5(self):
        """The exact counterexample from REVIEW_FOLLOWUP.md F2: the prior U+D-pooled code
        returned 0.5 here; the correct U-only answer is 1.0."""
        result = long_term_candidate_share([12, 0], ["U", "D"], threshold_months=12)
        assert result["share"] == pytest.approx(1.0)
        assert result["n_stock"] == 1
        assert result["n_long_term"] == 1

    def test_empty_stock_returns_none_share(self):
        result = long_term_candidate_share([None], ["E"], threshold_months=12)
        assert result["share"] is None
        assert result["n_stock"] == 0

    def test_d_only_observations_are_undefined_not_zero(self):
        """A D-only agent-month set has no U observations at all -- the U-conditional share
        is undefined (None), not zero, mirroring the empty-traveller-month convention in
        transport_person_window_estimate()."""
        result = long_term_candidate_share([5, 0], ["D", "D"], threshold_months=12)
        assert result["share"] is None
        assert result["n_stock"] == 0


class TestLongTermCandidateShareMonthly:
    """The PRIMARY equal-month-average cross-sectional comparator, added 2026-09-15 (F2)."""

    def test_equal_month_average_of_the_u_conditional_share(self):
        # Step 1: two U observations, one long-term (12) one not (0) -> share 0.5.
        # Step 2: one U observation, long-term (15) -> share 1.0.
        # Equal-month average: (0.5 + 1.0) / 2 = 0.75 -- NOT the pooled agent-month average
        # (1 long-term out of 3 U observations = 1/3), demonstrating the two conventions
        # differ when the U population size varies across months.
        rows = [
            dict(step=1, duration=12, category="U"),
            dict(step=1, duration=0, category="U"),
            dict(step=2, duration=15, category="U"),
        ]
        result = long_term_candidate_share_monthly(rows, window_steps=[1, 2], threshold_months=12)
        assert result["share"] == pytest.approx(0.75)
        assert result["n_months_used"] == 2
        assert result["n_months_empty"] == 0

    def test_month_with_no_u_observations_is_excluded_not_zero(self):
        rows = [
            dict(step=1, duration=12, category="U"),
            dict(step=2, duration=0, category="D"),  # no U this month
        ]
        result = long_term_candidate_share_monthly(rows, window_steps=[1, 2], threshold_months=12)
        assert result["share"] == pytest.approx(1.0)  # only step 1 counted
        assert result["n_months_used"] == 1
        assert result["n_months_empty"] == 1

    def test_all_months_empty_returns_none(self):
        result = long_term_candidate_share_monthly([], window_steps=[1, 2], threshold_months=12)
        assert result["share"] is None
        assert result["n_months_empty"] == 2

    def test_steps_outside_window_are_ignored(self):
        rows = [
            dict(step=1, duration=12, category="U"),
            dict(step=99, duration=0, category="U"),  # not in window_steps
        ]
        result = long_term_candidate_share_monthly(rows, window_steps=[1], threshold_months=12)
        assert result["n_months_used"] == 1
        assert result["share"] == pytest.approx(1.0)

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


class TestStreamingEpisodeClockState:
    """Validates the streaming collector against episode_clock() (batch) on the same
    fixtures already used above, plus randomised sequences -- the "streaming state validated
    against full traces on a small fixture" the manifest repair (F6.6) requires."""

    @pytest.mark.parametrize("k", [0, 1, 3, 10**9])
    def test_matches_batch_episode_clock_on_the_worked_example(self, k):
        state = StreamingEpisodeClockState(k)
        streamed = [state.observe(c) for c in WORKED_EXAMPLE]
        assert streamed == episode_clock(WORKED_EXAMPLE, k)

    def test_matches_batch_on_every_hand_derived_fixture_above(self):
        fixtures = [
            (["U", "D", "U"], 0),
            (["D"] + ["U"] * 12, 0),
            (["U", "D", "D", "U"], 1),
            (["E", "D", "U"], 3),
            (["U", "U", "E", "U", "U"], 0),
            (["U", "D", "U", "D", "U"], 0),
        ]
        for cats, k in fixtures:
            state = StreamingEpisodeClockState(k)
            streamed = [state.observe(c) for c in cats]
            assert streamed == episode_clock(cats, k), f"mismatch for {cats}, k={k}"

    def test_matches_batch_on_randomised_sequences(self):
        rng = random.Random(42)
        for _ in range(50):
            length = rng.randint(1, 40)
            cats = [rng.choice(["E", "U", "D"]) for _ in range(length)]
            k = rng.choice([0, 1, 2, 5])
            state = StreamingEpisodeClockState(k)
            streamed = [state.observe(c) for c in cats]
            assert streamed == episode_clock(cats, k), f"mismatch for {cats}, k={k}"

    def test_negative_k_rejected(self):
        with pytest.raises(ValueError):
            StreamingEpisodeClockState(-1)

    def test_unrecognised_category_rejected(self):
        with pytest.raises(ValueError):
            StreamingEpisodeClockState(0).observe("Q")


class TestStreamingMonthlySummary:
    def test_matches_batch_long_term_candidate_share_monthly(self):
        rows = [
            dict(step=1, duration=12, category="U"),
            dict(step=1, duration=0, category="U"),
            dict(step=2, duration=15, category="U"),
            dict(step=2, duration=3, category="D"),
        ]
        window_steps = [1, 2, 3]  # step 3 has no observations at all -> empty
        batch = long_term_candidate_share_monthly(rows, window_steps, threshold_months=12)

        summary = StreamingMonthlySummary(threshold_months=12)
        for r in rows:
            summary.observe(r["step"], r["category"], r["duration"])
        streamed = summary.result(window_steps)

        assert streamed == batch

    def test_memory_scales_with_steps_not_agent_steps(self):
        """The whole point of the streaming summary: its internal dict size is bounded by
        the number of DISTINCT steps observed, not the number of (agent, step) rows fed in."""
        summary = StreamingMonthlySummary(threshold_months=12)
        n_agents, n_steps = 500, 300
        for step in range(n_steps):
            for _agent in range(n_agents):
                summary.observe(step, "U", 5)
        assert len(summary._n_u) == n_steps  # not n_agents * n_steps


class TestStreamingTransportSummary:
    def test_matches_batch_transport_person_window_estimate_both_weightings(self):
        records = [
            dict(step=1, agent_id="A", spend=30, trips=3),
            dict(step=1, agent_id="B", spend=30, trips=1),
            dict(step=1, agent_id="C", spend=0, trips=2),
            dict(step=2, agent_id="A", spend=10, trips=1),
            dict(step=2, agent_id="C", spend=0, trips=2),
        ]
        window_steps = [1, 2]

        summary = StreamingTransportSummary()
        for r in records:
            summary.observe(r["step"], r["spend"], r["trips"])

        for weighting in ("equal_person", "trip_weighted"):
            batch = transport_person_window_estimate(records, window_steps, weighting)
            streamed = summary.result(window_steps, weighting)
            assert streamed == batch, f"mismatch for weighting={weighting}"

    def test_empty_window_step_excluded_matches_batch(self):
        records = [dict(step=1, agent_id="A", spend=10, trips=1)]
        window_steps = [1, 2, 3]
        summary = StreamingTransportSummary()
        for r in records:
            summary.observe(r["step"], r["spend"], r["trips"])
        batch = transport_person_window_estimate(records, window_steps, "equal_person")
        streamed = summary.result(window_steps, "equal_person")
        assert streamed == batch
        assert streamed["n_months_empty"] == 2

    def test_rejects_a_non_traveller_observation(self):
        with pytest.raises(ValueError):
            StreamingTransportSummary().observe(1, 0.0, 0)

    def test_rejects_unrecognised_weighting(self):
        summary = StreamingTransportSummary()
        summary.observe(1, 10.0, 1)
        with pytest.raises(ValueError):
            summary.result([1], weighting="bogus")
