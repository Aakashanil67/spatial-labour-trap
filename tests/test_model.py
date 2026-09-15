"""Tests for the MVM. Each one has to be able to fail for a real reason -- see kill-slop.

Runs at N=200/T=60 rather than the shipped configs/mvm.yaml's N=500/T=120, so the fast suite
stays fast; the c-sensitivity and re-entry tests are checked separately at a scale small enough
to run in CI (`pytest -m "not slow"`) without needing the `slow` marker.
"""

from __future__ import annotations

from dataclasses import replace

from src.config import Config
from src.model import CityModel

BASE = Config(
    n_agents=200,
    n_vacancies=8,
    initial_search_capital=1.0,
    search_cost_per_trip=0.02,
    separation_rate=0.02,
    belief_multiplier=1.0,
    household_inflow=0.02,
    reentry_threshold=0.05,
    max_trips_per_step=4,
    n_steps=60,
    seed=7,
)


def run(config: Config):
    return CityModel(config).run()


def test_population_conserved_every_step():
    history = run(BASE)
    totals = history["u"] + history["l"] + history["discouraged"]
    assert (totals == BASE.n_agents).all()


def test_deterministic_under_fixed_seed():
    a = run(BASE)
    b = run(BASE)
    assert a.equals(b)


def test_different_seed_gives_different_trajectory():
    a = run(BASE)
    b = run(replace(BASE, seed=BASE.seed + 1))
    assert not a["u"].equals(b["u"])


def test_higher_search_cost_raises_discouragement():
    cheap = run(replace(BASE, search_cost_per_trip=0.01))
    expensive = run(replace(BASE, search_cost_per_trip=0.10))
    tail = slice(-20, None)
    cheap_share = (cheap["discouraged"] / BASE.n_agents).iloc[tail].mean()
    expensive_share = (expensive["discouraged"] / BASE.n_agents).iloc[tail].mean()
    assert expensive_share > cheap_share


def test_reentry_fires():
    history = run(BASE)
    assert history["n_reentries"].sum() > 0


def test_discouragement_fires():
    """The above two tests are meaningless if nobody ever becomes discouraged in the first
    place -- this pins that down directly."""
    history = run(BASE)
    assert history["n_new_discouraged"].sum() > 0


def test_matches_never_exceed_available_stocks():
    """D11: m_t must never exceed min(u_t, v_t), by construction of the matching lottery."""
    history = run(BASE)
    assert (history["m"] <= history[["u", "v"]].min(axis=1)).all()


def test_stock_identity_holds_exactly():
    """D11: u_{t+1} = u_t - m_t + n_separations_{t+1} - n_new_discouraged_{t+1} + n_reentries_{t+1}.

    Flow counters are indexed to when they're detected (start of the step they apply to), so
    this combines period t's outcome (m_t) with period t+1's own transition counts -- see the
    D11 note in DECISIONS.md for the full derivation."""
    history = run(BASE)
    u = history["u"].to_numpy()
    m = history["m"].to_numpy()
    sep = history["n_separations"].to_numpy()
    new_disc = history["n_new_discouraged"].to_numpy()
    reentries = history["n_reentries"].to_numpy()

    predicted_next_u = u[:-1] - m[:-1] + sep[1:] - new_disc[1:] + reentries[1:]
    assert (predicted_next_u == u[1:]).all()


def test_activation_order_robustness():
    """D1: aggregate outcomes should be statistically indistinguishable between shuffled and
    fixed-order activation, since no per-agent method in this MVM reads a sibling agent's
    just-updated state within a step. This currently passes trivially by construction -- it's
    the regression guard for when Week 2's neighbourhood-radius hiring can introduce genuine
    order-sensitivity, not evidence that no such sensitivity could ever exist."""
    shuffled = run(replace(BASE, shuffled_activation=True))
    fixed = run(replace(BASE, shuffled_activation=False))
    shuffled_mean_u = shuffled["u"].tail(20).mean()
    fixed_mean_u = fixed["u"].tail(20).mean()
    assert abs(shuffled_mean_u - fixed_mean_u) <= 0.25 * BASE.n_agents


def test_jobless_clock_survives_a_discouragement_cycle():
    """The long-term moment's estimand tracks joblessness through a discouragement pause: the
    searching-state spell clock (months_in_state) resets on discouraged -> searching re-entry,
    which is correct for the spell histogram but wrong for this moment -- measuring it off
    months_in_state undercounted long-term joblessness in exact proportion to the model's own
    discouragement churn. See DECISIONS.md, "long_term_share was measuring the wrong clock".

    B1 moved the increment out of step_discouraged/step_searching and into model.step()'s own
    accounting pass (see DECISIONS.md, B1), so this is no longer testable by calling
    step_discouraged() in isolation -- that method no longer touches months_jobless at all.
    The composed path below (a real model.step() call) is the actual regression guard;
    test_calendar_clock_advances_exactly_once_per_step_through_a_full_cycle covers the specific
    double-count/zero-count defect directly."""
    from src.agents import SeekerState

    cfg = replace(BASE, n_steps=1, separation_rate=0.0, n_vacancies=0)
    model = CityModel(cfg)
    for agent in model._seekers():
        agent.state = SeekerState.EMPLOYED  # park everyone else out of the searching pool
    probe = next(iter(model._seekers()))
    probe.state = SeekerState.DISCOURAGED
    probe.months_jobless = 14
    probe.search_capital = cfg.reentry_threshold  # crosses the threshold, re-enters this step
    model.step()
    assert probe.state is SeekerState.SEARCHING  # confirms the re-entry actually happened
    assert probe.months_jobless == 15  # exactly one credit, not two


def test_calendar_clock_advances_once_per_step_regardless_of_state_transitions():
    """One credit per elapsed step for a non-employed agent, whatever transitions it makes.

    The defect this guards against had two halves that cancelled: an agent re-entering search
    advanced the clock twice in one step, and an agent exhausting its capital advanced it zero
    times. A first attempt at the fix removed only the double-advance, which broke the
    cancellation and undercounted. The assertions below therefore count elapsed steps directly
    rather than reproducing either implementation's behaviour."""
    from src.agents import SeekerState

    cfg = replace(
        BASE,
        n_steps=1,
        separation_rate=0.0,
        n_vacancies=0,
        search_cost_per_trip=0.02,
        household_inflow=0.02,
        reentry_threshold=0.05,
    )
    model = CityModel(cfg)
    for agent in model._seekers():
        agent.state = SeekerState.EMPLOYED
    probe = next(iter(model._seekers()))
    probe.state = SeekerState.SEARCHING
    probe.search_capital = 0.0  # cannot afford one trip: exhausts on the very next step
    probe.months_jobless = 0

    # Step 1: exhaustion (searching -> discouraged). The step still elapsed, so it still counts.
    model.step()
    assert probe.state is SeekerState.DISCOURAGED
    assert probe.months_jobless == 1

    # Steps 2 and 3: continuously discouraged. Capital climbs 0.02 per step toward the 0.05
    # re-entry threshold.
    model.step()
    assert probe.months_jobless == 2
    model.step()
    assert probe.months_jobless == 3

    # Step 4: capital crosses the threshold and the agent re-enters search. One credit, not two.
    model.step()
    assert probe.state is SeekerState.SEARCHING
    assert probe.months_jobless == 4

    # Step 5: ordinary continued searching. Topped up first so trip affordability, which draws
    # from model.rng, cannot decide the outcome of a clock test.
    probe.search_capital = 5.0
    model.step()
    assert probe.state is SeekerState.SEARCHING
    assert probe.months_jobless == 5


def test_jobless_clock_matches_an_independent_elapsed_time_reference():
    """The real acceptance check: over a full run, months_jobless at every measurement point
    must equal a reference clock built only from observed state transitions, which cannot
    inherit whatever defect months_jobless itself has.

    The reference counts completed steps since each agent's last hire during which it was not
    employed. That convention -- completed months, excluding the step in progress -- is what
    makes a continuously unemployed agent read 11 at the step-12 measurement."""
    from src.agents import JobSeeker, SeekerState

    reference: dict[int, int] = {}
    mismatches: list[tuple[int, int, int, int]] = []

    orig_collect = CityModel._collect_cell_row
    orig_resolve_hire = JobSeeker.resolve_hire
    orig_step = CityModel.step

    def patched_resolve_hire(self):
        reference[self.unique_id] = 0
        return orig_resolve_hire(self)

    def patched_collect(self, searching):
        for agent in searching:
            expected = reference.get(agent.unique_id, 0)
            if agent.months_jobless != expected:
                mismatches.append((self.steps, agent.unique_id, agent.months_jobless, expected))
        return orig_collect(self, searching)

    def patched_step(self):
        for agent in self._seekers():
            reference.setdefault(agent.unique_id, 0)
        orig_step(self)
        for agent in self._seekers():
            if agent.state is not SeekerState.EMPLOYED:
                reference[agent.unique_id] = reference.get(agent.unique_id, 0) + 1

    CityModel._collect_cell_row = patched_collect
    JobSeeker.resolve_hire = patched_resolve_hire
    CityModel.step = patched_step
    try:
        CityModel(replace(BASE, n_steps=80)).run()
    finally:
        CityModel._collect_cell_row = orig_collect
        JobSeeker.resolve_hire = orig_resolve_hire
        CityModel.step = orig_step

    assert not mismatches, (
        f"{len(mismatches)} measurement points disagree with the independent reference; "
        f"first five (step, agent, months_jobless, expected): {mismatches[:5]}"
    )


def _reference_mismatches(config: Config) -> list[tuple[int, int, int, int]]:
    """Runs config once, comparing months_jobless against the same independent reference used
    above, and returns every (step, agent, months_jobless, expected) disagreement found. Factored
    out so several configurations and code variants can be checked against the identical
    reference logic, rather than each carrying its own copy."""
    from src.agents import JobSeeker, SeekerState

    reference: dict[int, int] = {}
    mismatches: list[tuple[int, int, int, int]] = []

    orig_collect = CityModel._collect_cell_row
    orig_resolve_hire = JobSeeker.resolve_hire
    orig_step = CityModel.step

    def patched_resolve_hire(self):
        reference[self.unique_id] = 0
        return orig_resolve_hire(self)

    def patched_collect(self, searching):
        for agent in searching:
            expected = reference.get(agent.unique_id, 0)
            if agent.months_jobless != expected:
                mismatches.append((self.steps, agent.unique_id, agent.months_jobless, expected))
        return orig_collect(self, searching)

    def patched_step(self):
        for agent in self._seekers():
            reference.setdefault(agent.unique_id, 0)
        orig_step(self)
        for agent in self._seekers():
            if agent.state is not SeekerState.EMPLOYED:
                reference[agent.unique_id] = reference.get(agent.unique_id, 0) + 1

    CityModel._collect_cell_row = patched_collect
    JobSeeker.resolve_hire = patched_resolve_hire
    CityModel.step = patched_step
    try:
        CityModel(config).run()
    finally:
        CityModel._collect_cell_row = orig_collect
        JobSeeker.resolve_hire = orig_resolve_hire
        CityModel.step = orig_step

    return mismatches


def test_jobless_clock_matches_reference_across_seeds_and_a_repeated_discouragement_config():
    """P0.2: the single-seed check above is not enough on its own -- extend to several seeds and
    to a configuration engineered to cycle agents through discouragement repeatedly (high search
    cost relative to capital, slow household inflow), since that is exactly the path the original
    defect corrupted and a config that rarely discourages anyone would not exercise it."""
    repeated_discouragement_cfg = replace(
        BASE,
        n_agents=100,
        n_steps=120,
        search_cost_per_trip=0.15,  # expensive relative to initial_search_capital=1.0
        household_inflow=0.01,  # slow recovery -- many steps spent discouraged per episode
        reentry_threshold=0.08,
        separation_rate=0.05,
    )
    for seed in (1, 2, 3, 4, 5):
        cfg = replace(repeated_discouragement_cfg, seed=seed)
        mismatches = _reference_mismatches(cfg)
        assert not mismatches, (
            f"seed {seed}: {len(mismatches)} mismatches, first three: {mismatches[:3]}"
        )


def test_continuous_search_reads_eleven_completed_months_at_the_step_twelve_measurement():
    """The documented observation convention, checked directly rather than inferred: a
    continuously searching agent's months_jobless reads 11 at the step-12 measurement and 12 at
    the step-13 measurement -- the first step at which it is classified long-term, since
    LONG_TERM_THRESHOLD_MONTHS is 12 and 11 < 12 <= 12."""
    from src.model import LONG_TERM_THRESHOLD_MONTHS

    assert LONG_TERM_THRESHOLD_MONTHS == 12

    cfg = replace(BASE, n_steps=1, separation_rate=0.0, n_vacancies=0, n_agents=50)
    model = CityModel(cfg)
    probe = next(iter(model._seekers()))
    probe.search_capital = 1000.0  # never exhausts, never discouraged, always searching

    measured_at_step: dict[int, int] = {}
    orig_collect = CityModel._collect_cell_row

    def patched_collect(self, searching):
        measured_at_step[self.steps] = probe.months_jobless
        return orig_collect(self, searching)

    CityModel._collect_cell_row = patched_collect
    try:
        for _ in range(13):
            model.step()
    finally:
        CityModel._collect_cell_row = orig_collect

    assert measured_at_step[12] == 11
    assert measured_at_step[13] == 12
    assert 11 < LONG_TERM_THRESHOLD_MONTHS <= 12  # confirms this is the actual classification edge


def _reference_mismatches_under_variant(
    config: Config, step_searching_credit: int, step_discouraged_credit: int
) -> list[tuple[int, int, int, int]]:
    """Reproduces a historical months_jobless variant by monkeypatch, then runs it through the
    same independent reference check the corrected implementation passes.

    The corrected model.step() applies one unconditional credit per elapsed step to every
    non-employed agent (see model.py). To emulate a variant where the credit instead lived
    inside step_searching/step_discouraged with different (possibly wrong) per-call amounts,
    this cancels that unconditional credit exactly -- subtracting 1 from every currently
    non-employed agent immediately after each step() call, which is the whole and only effect
    the model-level loop has -- and then applies the requested per-method credit amounts
    instead. This is precise, not approximate: the corrected loop's effect is fully known and
    unconditional, so cancelling it exactly is not a source of error in what remains.

    step_searching_credit=1, step_discouraged_credit=1 reproduces the pre-refactor
    implementation, expected to PASS this check: its double-advance on re-entry and
    zero-advance on exhaustion cancel by the time of measurement.

    step_searching_credit=0, step_discouraged_credit=1 reproduces the broken half-fix (the
    double-advance removed, the zero-advance left in place), expected to FAIL: removing only
    one side of the cancellation leaves an undercount.

    Cancellation detail that matters: the corrected credit loop runs on the FULL non-employed
    population at one exact mid-step instant (after separations/re-entry/exhaustion resolve,
    before matching) -- not the population non-employed at the very start or end of step().
    An agent that separates and is not rehired in the same step, for instance, is non-employed
    at that mid-step instant but was employed at the step's start, so a naive before/after
    snapshot would miss it. `_collect_cell_row` is called at exactly that instant in the real
    step(), immediately before the credit loop runs, so hooking it (and querying the model's
    own live DISCOURAGED set at that same moment, since `_collect_cell_row` is only handed the
    SEARCHING half) gives the exact population to cancel, not an approximation of it."""
    from src.agents import JobSeeker, SeekerState

    reference: dict[int, int] = {}
    mismatches: list[tuple[int, int, int, int]] = []
    to_cancel: list = []

    orig_collect = CityModel._collect_cell_row
    orig_resolve_hire = JobSeeker.resolve_hire
    orig_step_searching = JobSeeker.step_searching
    orig_step_discouraged = JobSeeker.step_discouraged
    orig_step = CityModel.step

    def patched_resolve_hire(self):
        reference[self.unique_id] = 0
        return orig_resolve_hire(self)

    def patched_collect(self, searching):
        for agent in searching:
            expected = reference.get(agent.unique_id, 0)
            if agent.months_jobless != expected:
                mismatches.append((self.steps, agent.unique_id, agent.months_jobless, expected))
        # The exact population the real credit loop is about to apply to: SEARCHING (handed in
        # here) plus whoever is DISCOURAGED at this same instant, queried live.
        to_cancel.clear()
        to_cancel.extend(searching)
        to_cancel.extend(self._seekers(SeekerState.DISCOURAGED))
        return orig_collect(self, searching)

    def variant_step_searching(self):
        orig_step_searching(self)
        self.months_jobless += step_searching_credit

    def variant_step_discouraged(self):
        self.months_jobless += step_discouraged_credit
        orig_step_discouraged(self)

    def patched_step(self):
        for agent in self._seekers():
            reference.setdefault(agent.unique_id, 0)
        orig_step(self)
        # Cancel the corrected model-level credit exactly, on exactly the population it applied
        # to (captured by patched_collect above, during this same orig_step call) -- excluding
        # anyone hired later in this same step. resolve_hire already reset such an agent's
        # counter to 0 chronologically before this line runs; subtracting further would corrupt
        # that reset into a spurious -1, which has nothing to do with the variant under test.
        for agent in to_cancel:
            if agent.state is not SeekerState.EMPLOYED:
                agent.months_jobless -= 1
        for agent in self._seekers():
            if agent.state is not SeekerState.EMPLOYED:
                reference[agent.unique_id] = reference.get(agent.unique_id, 0) + 1

    CityModel._collect_cell_row = patched_collect
    JobSeeker.resolve_hire = patched_resolve_hire
    JobSeeker.step_searching = variant_step_searching
    JobSeeker.step_discouraged = variant_step_discouraged
    CityModel.step = patched_step
    try:
        CityModel(config).run()
    finally:
        CityModel._collect_cell_row = orig_collect
        JobSeeker.resolve_hire = orig_resolve_hire
        JobSeeker.step_searching = orig_step_searching
        JobSeeker.step_discouraged = orig_step_discouraged
        CityModel.step = orig_step

    return mismatches


def test_reference_check_distinguishes_the_historical_defect_from_the_broken_half_fix():
    repeated_discouragement_cfg = replace(
        BASE,
        n_agents=60,
        n_steps=100,
        search_cost_per_trip=0.15,
        household_inflow=0.01,
        reentry_threshold=0.08,
        separation_rate=0.05,
        seed=11,
    )

    historical = _reference_mismatches_under_variant(
        repeated_discouragement_cfg, step_searching_credit=1, step_discouraged_credit=1
    )
    assert not historical, (
        f"the pre-refactor implementation was expected to pass (its two errors cancel at "
        f"measurement), but got {len(historical)} mismatches: {historical[:3]}"
    )

    broken_half_fix = _reference_mismatches_under_variant(
        repeated_discouragement_cfg, step_searching_credit=0, step_discouraged_credit=1
    )
    assert broken_half_fix, (
        "the broken half-fix (double-advance removed, zero-advance retained) was expected to "
        "undercount and fail this check, but it passed -- the check is not discriminating"
    )


def test_jobless_clock_resets_only_on_hire():
    model = CityModel(BASE)
    agent = next(iter(model._seekers()))
    agent.months_jobless = 20
    agent.resolve_hire()
    assert agent.months_jobless == 0


def test_trips_this_step_is_reset_for_agents_who_stop_searching():
    """F4 (2026-09-15, Astra's REVIEW_FOLLOWUP.md): trips_this_step must reflect only THIS
    step's genuine decision. Before the fix, an agent who stopped being SEARCHING (employed
    or discouraged) silently retained trips_this_step from the last step it actually
    searched, since step_searching() -- the only place that sets the field -- never runs on
    a non-searching agent."""
    from src.agents import SeekerState

    cfg = replace(BASE, n_steps=1, separation_rate=0.0)
    model = CityModel(cfg)
    probe = next(iter(model._seekers()))
    probe.state = SeekerState.SEARCHING
    probe.search_capital = 100.0  # affordable: decide_trips() should return > 0
    model._traced_agents = [probe]

    model.step()
    row1 = model.trace_history[-1]
    assert row1["trips_this_step"] > 0, "setup check: probe must search genuinely this step"

    # An employed agent that stays employed (no separation): must read 0, not the stale
    # positive value from the step above.
    probe.state = SeekerState.EMPLOYED
    model.step()
    row2 = model.trace_history[-1]
    assert row2["state"] == "EMPLOYED"
    assert row2["trips_this_step"] == 0

    # A discouraged agent (as capital exhaustion would produce): must also read 0. Capital
    # kept below reentry_threshold so step_discouraged's own re-entry check does not flip it
    # straight back to SEARCHING before trips_this_step could be observed as DISCOURAGED.
    probe.state = SeekerState.DISCOURAGED
    probe.search_capital = 0.0
    model.step()
    row3 = model.trace_history[-1]
    assert row3["state"] == "DISCOURAGED"
    assert row3["trips_this_step"] == 0


def test_trips_taken_in_a_hire_month_are_preserved_in_the_trace():
    """F4's explicit warning: filtering all post-matching EMPLOYED observations to zero would
    introduce a DIFFERENT error. An agent who searches (genuine trips > 0) and is matched to
    a job in the SAME step must show that step's real trip count in the post-matching trace,
    not zero."""
    from src.agents import SeekerState

    cfg = replace(BASE, n_steps=1, separation_rate=0.0, n_vacancies=100)
    model = CityModel(cfg)
    for agent in model._seekers():
        agent.state = SeekerState.EMPLOYED  # park everyone else so the probe is sure to be hired
    probe = next(iter(model._seekers()))
    probe.state = SeekerState.SEARCHING
    probe.search_capital = 100.0
    model._traced_agents = [probe]

    model.step()
    row = model.trace_history[-1]
    assert row["state"] == "EMPLOYED", "setup check: abundant vacancies must hire the probe"
    assert row["trips_this_step"] > 0, "a hire-month's genuine search trips must be preserved"


def test_n_long_term_counts_jobless_duration_not_state_spell():
    """An agent 15 months jobless whose current searching spell is only 2 months old IS
    long-term unemployed on QLFS's definition. Before the fix, n_long_term read
    months_in_state and counted this agent as short-term."""
    from src.agents import SeekerState

    cfg = replace(BASE, n_steps=1, separation_rate=0.0, n_vacancies=0)
    model = CityModel(cfg)
    for agent in model._seekers():
        agent.state = SeekerState.EMPLOYED  # park everyone else out of the searching pool
    probe = next(iter(model._seekers()))
    probe.state = SeekerState.SEARCHING
    probe.months_jobless = 15
    probe.months_in_state = 2
    probe.search_capital = 5.0  # comfortably above one trip, so no exhaustion exit
    history = model.run()
    assert history["n_long_term"].iloc[0] == 1


def test_capital_at_reentry_is_bounded_by_max_r_c_plus_g_when_c_below_r():
    """Budget-bound derivation (data/review_v2/replenished_capital_budget_bound.md,
    2026-09-15): after hard capital exhaustion, capital replenishes ONLY via
    household_inflow (g) while DISCOURAGED, never while SEARCHING. When the per-trip cost c
    is below the re-entry threshold r, the agent's first SEARCHING step already affords a
    trip (no within-step bounce needed), and the re-entry capital is in [r, r+g)."""
    from src.agents import SeekerState

    cfg = replace(
        BASE,
        n_agents=5,
        n_vacancies=0,
        search_cost_per_trip=0.003,
        household_inflow=0.008,
        reentry_threshold=0.035,
        n_steps=1,
    )
    model = CityModel(cfg)
    probe = next(iter(model._seekers()))
    probe.state = SeekerState.DISCOURAGED
    probe.search_capital = 0.0
    r, g = cfg.reentry_threshold, cfg.household_inflow
    c = probe.cost_per_trip
    assert c < r, "setup check: this fixture is the c < r case"

    steps = 0
    while probe.state == SeekerState.DISCOURAGED:
        probe.step_discouraged()
        steps += 1
        assert steps <= 1000, "did not re-enter within a generous step budget"

    assert probe.state == SeekerState.SEARCHING
    assert r <= probe.search_capital < r + g
    assert probe.can_afford_one_trip()  # no within-step bounce needed when c < r


def test_capital_at_reentry_is_bounded_by_max_r_c_plus_g_when_c_above_r():
    """Same bound, c > r case: the re-entry check (step 2 of CityModel.step()) and the
    capital-exhaustion check (step 3) run in that order WITHIN one step() call, so an agent
    whose newly-incremented capital clears r but not c is sent straight back to DISCOURAGED
    the SAME step -- invisible in trace_history, which only records the step's terminal
    state. Verified here through the ACTUAL CityModel.step() sequence, not a standalone
    re-implementation of the transition logic."""
    from src.agents import SeekerState

    cfg = replace(
        BASE,
        n_agents=5,
        n_vacancies=0,
        search_cost_per_trip=0.1,
        household_inflow=0.008,
        reentry_threshold=0.035,
        n_steps=1,
    )
    model = CityModel(cfg)
    probe = next(iter(model._seekers()))
    probe.state = SeekerState.DISCOURAGED
    probe.search_capital = 0.0
    r, g = cfg.reentry_threshold, cfg.household_inflow
    c = probe.cost_per_trip
    assert c > r, "setup check: this fixture is the c > r case"

    steps = 0
    while probe.state == SeekerState.DISCOURAGED:
        model.steps += 1
        probe.step_discouraged()  # step 2 of CityModel.step()'s sequence
        if probe.state == SeekerState.SEARCHING and not probe.can_afford_one_trip():
            probe.state = SeekerState.DISCOURAGED  # step 3's exhaustion check, same step
            probe.months_in_state = 0
        steps += 1
        assert steps <= 1000, "did not re-enter within a generous step budget"

    assert probe.state == SeekerState.SEARCHING
    assert c <= probe.search_capital < c + g  # max(r, c) == c here
    assert probe.can_afford_one_trip()


def test_reentry_bound_reproduces_end_to_end_through_the_real_model_step():
    """The same c > r case, but driven entirely through CityModel.step() (not by manually
    calling step_discouraged()/can_afford_one_trip() as the two tests above do) -- confirms
    the derivation against the actual production step() sequence end to end, including the
    within-step bounce, D11 stock timing and trace recording all interacting correctly."""
    from src.agents import SeekerState

    cfg = replace(
        BASE,
        n_agents=5,
        n_vacancies=0,
        search_cost_per_trip=0.1,
        household_inflow=0.008,
        reentry_threshold=0.035,
        separation_rate=0.0,
        n_steps=50,
        trace_agent_ids=tuple(range(1, 11)),
    )
    model = CityModel(cfg)
    probe = next(iter(model._seekers()))
    probe.state = SeekerState.DISCOURAGED
    probe.search_capital = 0.0
    for agent in model._seekers():
        if agent.unique_id != probe.unique_id:
            agent.state = SeekerState.EMPLOYED  # isolate the probe's own dynamics
    g = cfg.household_inflow
    c = probe.cost_per_trip

    import pandas as pd

    model.run()
    trace = pd.DataFrame(model.trace_history)
    trace = trace[trace["unique_id"] == probe.unique_id].sort_values("step")
    first_searching = trace[trace["state"] == "SEARCHING"].iloc[0]
    assert c <= first_searching["search_capital"] < c + g
    # Every step before it: DISCOURAGED, capital rising by exactly g each recorded step
    # (the within-step bounces are not individually visible, but the net effect -- g per
    # DISCOURAGED-terminal step -- is).
    before = trace[trace["step"] < first_searching["step"]]
    assert (before["state"] == "DISCOURAGED").all()
