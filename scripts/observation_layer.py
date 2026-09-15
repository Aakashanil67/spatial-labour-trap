"""Review-only common E/U/D observation layer, search-duration clocks, and the transport
estimator, per the approved specification (Aakash, 2026-09-15) and Astra's
`COMPLETION_REVIEW.md`. See `data/review_v2/approved_specification_2026-09-15.md` for the
full written specification this module implements.

**Not wired into `src/moments.py`, `data/moments.csv`, or any canonical calibration target.**
Operates on a per-agent, per-step TRACE with the same shape `CityModel.trace_history` produces
for traced agents (extended 2026-09-15 with `belief_inactive_this_step` and `months_jobless`).

**Observation point: POST-MATCHING, the same point `trace_history` already uses -- NOT the
pre-matching D11 aggregate-stock convention `u_t`/`disc_t`/`l_t` (`self.history`) use.** This
is a deliberate, disclosed choice (Astra's finding 3, COMPLETION_REVIEW.md): the approved E/U/D
mapping needs this-step trip decisions (`belief_inactive_this_step`, set in `step_searching`,
step 5 of `CityModel.step()`), which are not yet known at the pre-matching stock point (step 4).
Evaluating post-matching (after step 6) correctly reflects agents hired this step as EMPLOYED
and costs nothing over evaluating between steps 5 and 6, since matching only ever moves a
SEARCHING agent to EMPLOYED and never touches `belief_inactive_this_step`. The canonical D11
aggregate stocks in `self.history` are UNCHANGED and remain the calibration input; this module
produces a separate, additional observation series from the SAME underlying run.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

VALID_STATES = {"EMPLOYED", "SEARCHING", "DISCOURAGED"}
CATEGORIES = ("E", "U", "D")


def classify_observation(state: str, belief_inactive_this_step: bool) -> str:
    """The approved E/U/D mapping (observation_estimation_proposal.md Section 2, unchanged
    by this pass's amendments):
      EMPLOYED                                   -> E
      SEARCHING, took >=1 trip this step          -> U (belief_inactive_this_step is False)
      SEARCHING, belief_inactive_this_step        -> D (capital-solvent, chose not to search)
      DISCOURAGED (hard, capital-exhausted)       -> D
    QLFS's "Other NEA" has no model equivalent -- not represented, not silently folded into
    D; a caller comparing against QLFS Other-NEA destinations must account for that separately
    (see observation_estimation_proposal.md Section 2's stated scope limitation)."""
    if state not in VALID_STATES:
        raise ValueError(f"unrecognised state {state!r}, expected one of {VALID_STATES}")
    if state == "EMPLOYED":
        return "E"
    if state == "DISCOURAGED":
        return "D"
    return "D" if belief_inactive_this_step else "U"


def classify_trace(rows: Sequence[dict]) -> list[str]:
    """Applies classify_observation() to a chronological sequence of trace rows for ONE
    agent (each row needs 'state' and 'belief_inactive_this_step')."""
    return [classify_observation(r["state"], r["belief_inactive_this_step"]) for r in rows]


def episode_clock(categories: Sequence[str], k: int) -> list[int | None]:
    """The k-tolerant search-episode clock (observation_estimation_proposal.md Section 3).
    `categories`: a chronological E/U/D sequence for ONE agent (from classify_trace()).

    **CORRECTED 2026-09-15 (Astra's REVIEW_FOLLOWUP.md finding F1).** The prior version let a
    D observation with no episode in progress OPEN a fresh episode (crediting that D month as
    the episode's day 0), which is wrong: only a U observation can open or continue an
    episode; a D observation can only be WITHIN an already-open episode (as a tolerated gap)
    or outside any episode (undefined, None). The bug also mis-credited the length after a
    tolerated gap: e.g. for `k=0`, `[U, D, U]` must read `[0, None, 0]` -- the returning U is
    a NEW episode (0), not a continuation (the prior, buggy code returned `[0, 0, 1]`). And a
    leading `D` with no prior U, e.g. `[D, U, U, ...]`, must read `[None, 0, 1, ...]`, not
    `[0, 1, 2, ...]` -- confirmed against Astra's independent reference implementation and
    `tests/test_observation_layer.py`'s corrected fixtures.

    Returns, for each step, the number of COMPLETED PRIOR steps of the CURRENT episode,
    credited AS OF that step's own (post-matching) observation -- the SAME "credited after
    measurement" convention already used for `months_jobless` (a continuously active agent
    reads N-1 at its Nth consecutive U observation within one episode; first classified
    long-term, at the existing 12-month threshold, on its 13th such observation, not its
    12th). `None` where category == 'E' (employed) OR where the agent is a D observation with
    no episode currently open (D alone does not create search history; see F1's explicit
    requirement that D must not be given a credited duration it never earned by searching).

    An episode is opened only by a U observation. Once open, it continues through a run of up
    to `k` consecutive D observations since the last U; a D observation that would make the
    gap exceed `k` closes the episode (reading None from then on, until the next U reopens a
    fresh one at reading 0). `k=0`: any single D closes the episode immediately -- the next U
    starts a brand-new episode at 0, not a continuation."""
    if k < 0:
        raise ValueError("k must be >= 0")
    start: int | None = None  # step index the current episode opened at
    last_u: int | None = None  # step index of the episode's most recent U observation
    out: list[int | None] = []
    for t, cat in enumerate(categories):
        if cat not in CATEGORIES:
            raise ValueError(f"unrecognised category {cat!r}")
        if cat == "E":
            start = last_u = None
            out.append(None)
        elif cat == "U":
            if start is None or t - last_u - 1 > k:
                start = t  # no episode open, or the gap since last_u already exceeded k
            last_u = t
            out.append(t - start)
        else:  # D
            if start is not None and t - last_u > k:
                start = last_u = None  # this D itself pushes the gap past tolerance
            out.append(None if start is None else t - start)
    return out


def cumulative_active_months(categories: Sequence[str]) -> list[int | None]:
    """Cumulative active-search months (observation_estimation_proposal.md Section 3): counts
    ONLY 'U' steps, subtracting every 'D' month regardless of any tolerance -- a DISTINCT
    estimator from the episode-clock family, not a k-range point (DECISIONS_PENDING.md
    Question 5's worked example: 3 active, 2-month pause, 4 more active reports 7 here, a
    value no k in {0,1,3,infinity} can produce). Same credited-after-measurement convention
    as episode_clock(): counts completed PRIOR active months as of this step's observation.
    Resets to 0 on re-employment (cat == 'E'), like the episode clocks. Does not reset on a D
    step -- a D step simply is not counted, and does not end the underlying non-employment
    spell this estimator is tracking within.

    Astra's COMPLETION_REVIEW.md item 3 correctly notes the worked example does not prove
    this can NEVER numerically coincide with some episode-clock value on some other path --
    only that it is a distinct FUNCTIONAL, not a special case of the episode-clock family."""
    out: list[int | None] = []
    completed = None
    for cat in categories:
        if cat not in CATEGORIES:
            raise ValueError(f"unrecognised category {cat!r}")
        if cat == "E":
            completed = None
            out.append(None)
            continue
        if completed is None:
            completed = 0
            out.append(0)
            if cat == "U":
                completed += 1
            continue
        out.append(completed)  # credit BEFORE counting this step, if it's active
        if cat == "U":
            completed += 1
    return out


def long_term_candidate_share(
    duration_by_agent_step: Iterable[int | None],
    categories_by_agent_step: Iterable[str],
    threshold_months: int = 12,
) -> dict:
    """POOLED (agent-month) U-ONLY long_term_share candidate diagnostic.

    **CORRECTED 2026-09-15 (Astra's REVIEW_FOLLOWUP.md finding F2).** The prior version
    pooled U and D together in the denominator (and could count a D observation as
    "long-term" in the numerator), which does not match the empirical target: the QLFS
    `Long_term_unempl` target's eligible universe is `Status`=2 (Unemployed -- this project's
    U) ONLY, confirmed live against the 2026-Q1 extract (all 7,502 age-15-64,
    `Long_term_unempl`-eligible records have `Status`=2; none are Discouraged). Pooling U+D
    is a DIFFERENT, expanded non-employment statistic -- if useful, it needs its own name and
    must not be described as this QLFS target. Counterexample that motivated the fix: one U
    observation with duration 12 and one D observation with duration 0 must read 1.0 (the
    U-only share), not the prior code's 0.5.

    A D-only observation set (no U observations at all, `n_stock == 0`) has an UNDEFINED
    U-conditional share -- returned as `share=None`, not zero, mirroring
    `transport_person_window_estimate()`'s empty-traveller-month treatment.

    This is the POOLED (agent-month) variant -- see `long_term_candidate_share_monthly()`
    for the PRIMARY equal-month-average cross-sectional comparator, since the canonical
    `months_jobless`-based comparator is itself constructed as a mean of per-step ratios, not
    one ratio pooled across the whole window; the two aggregation conventions can disagree
    when the size of the U population varies across months.

    `duration_by_agent_step`/`categories_by_agent_step` must be the same length and in
    step-with-step correspondence (e.g. one call's output each from `episode_clock()`/
    `cumulative_active_months()` and `classify_trace()`, concatenated across agents)."""
    durations = list(duration_by_agent_step)
    cats = list(categories_by_agent_step)
    if len(durations) != len(cats):
        raise ValueError("duration and category sequences must have equal length")
    stock = [d for d, c in zip(durations, cats, strict=True) if c == "U"]
    if not stock:
        return dict(share=None, n_stock=0, n_long_term=0)
    n_long_term = sum(1 for d in stock if d is not None and d >= threshold_months)
    return dict(
        share=n_long_term / len(stock),
        n_stock=len(stock),
        n_long_term=n_long_term,
    )


def long_term_candidate_share_monthly(
    rows: Sequence[dict],
    window_steps: Iterable[int],
    threshold_months: int = 12,
) -> dict:
    """PRIMARY cross-sectional long_term_share candidate: the equal-month average of the
    U-conditional long-term share (added 2026-09-15, Astra's REVIEW_FOLLOWUP.md finding F2).
    Matches the canonical `months_jobless`-based comparator's own construction (mean of each
    step's `n_long_term/u`, not one ratio pooled across agent-months --
    `scripts/demo_observation_layer_run.py`'s `long_term_share_canonical_months_jobless`).

    `rows`: one dict per (agent, step) observation, each needing 'step', 'duration',
    'category' (U-only rows matter; D/E rows are ignored here, matching
    `long_term_candidate_share()`'s U-only population). `window_steps`: every step in the
    measurement window, including steps with zero U observations -- required to detect and
    exclude those months explicitly (undefined, not zero), the same convention as
    `transport_person_window_estimate()`'s empty-traveller-month handling."""
    by_step: dict[int, list[int | None]] = {s: [] for s in window_steps}
    for r in rows:
        if r["category"] == "U" and r["step"] in by_step:
            by_step[r["step"]].append(r["duration"])

    month_shares: list[float] = []
    n_empty = 0
    for durations in by_step.values():
        if not durations:
            n_empty += 1
            continue
        n_long = sum(1 for d in durations if d is not None and d >= threshold_months)
        month_shares.append(n_long / len(durations))

    if not month_shares:
        return dict(share=None, n_months_used=0, n_months_empty=n_empty)
    return dict(
        share=sum(month_shares) / len(month_shares),
        n_months_used=len(month_shares),
        n_months_empty=n_empty,
    )


# --- Transport person-window estimator (observation_estimation_proposal.md Section 4) -----


def transport_person_window_estimate(
    traveller_records: Sequence[dict],
    window_steps: Iterable[int],
    weighting: str = "equal_person",
) -> dict:
    """`traveller_records`: rows for TRAVELLERS ONLY (trips >= 1 this step; a non-traveller
    contributes no row at all for that step -- see the module docstring's zero-cost-vs-
    non-traveller distinction). Each row needs 'step', 'agent_id', 'spend', 'trips'.
    `window_steps`: every step in the measurement window, including steps with zero
    travellers -- required to detect and exclude empty traveller-months explicitly, rather
    than inferring "no travellers" from a step's simple absence in `traveller_records` (which
    would be indistinguishable from a caller error that dropped a step's rows by accident).

    `weighting`:
      - 'equal_person' (PRIMARY, approved 2026-09-15): each traveller's own per-trip mean
        cost this month, averaged equally across that month's travellers; those per-month
        cross-sectional means are then averaged equally across measurement months.
      - 'trip_weighted' (a named SENSITIVITY SCENARIO, not a bound -- Astra's
        COMPLETION_REVIEW.md item 4 -- the two are NOT shown to bracket the true weekly-
        screen estimand, and 'trip_weighted' is not even uniformly the larger of the two
        in general): total spend over total trips within the month, i.e. the trip-mean,
        then averaged equally across measurement months (unlike the OLD estimator, which
        pooled trips across the WHOLE window rather than averaging equally per month -- so
        even the trip-weighted scenario here differs from the pre-existing
        `transport_budget_share()` formula purely through the across-month averaging
        convention change).

    Empty traveller-months (window steps with zero rows in `traveller_records`) are EXCLUDED
    from the across-month average, never treated as a zero-cost observation -- an undefined
    conditional mean is not the same thing as an observed zero."""
    if weighting not in ("equal_person", "trip_weighted"):
        raise ValueError(f"weighting must be 'equal_person' or 'trip_weighted', got {weighting!r}")
    by_step: dict[int, list[dict]] = defaultdict(list)
    for r in traveller_records:
        if r["trips"] < 1:
            raise ValueError(
                "traveller_records must contain travellers only (trips>=1); "
                f"got trips={r['trips']!r}"
            )
        by_step[r["step"]].append(r)

    month_values: list[float] = []
    n_empty = 0
    steps_seen = list(window_steps)
    for step in steps_seen:
        records = by_step.get(step, [])
        if not records:
            n_empty += 1
            continue
        if weighting == "equal_person":
            per_agent = [r["spend"] / r["trips"] for r in records]
            month_values.append(sum(per_agent) / len(per_agent))
        else:
            total_spend = sum(r["spend"] for r in records)
            total_trips = sum(r["trips"] for r in records)
            month_values.append(total_spend / total_trips)

    if not month_values:
        return dict(estimate=None, n_months_used=0, n_months_empty=n_empty)
    return dict(
        estimate=sum(month_values) / len(month_values),
        n_months_used=len(month_values),
        n_months_empty=n_empty,
    )


# --- Streaming collector (added 2026-09-15, F6.6: results/review_v2/settled_regime/ -------
# --- validation_manifest_2026-09-15.md's storage/memory repair) ---------------------------


class StreamingEpisodeClockState:
    """O(1)-memory-per-agent streaming equivalent of episode_clock(): processes ONE
    observation at a time via observe() and returns the SAME value episode_clock() would
    give at that position, without ever storing the agent's full category history. Validated
    against episode_clock() directly in tests/test_observation_layer.py
    (TestStreamingEpisodeClockState) -- the exact "streaming state validated against full
    traces on a small fixture" the manifest repair requires before trusting it for a resource
    estimate."""

    __slots__ = ("k", "start", "last_u", "_t")

    def __init__(self, k: int):
        if k < 0:
            raise ValueError("k must be >= 0")
        self.k = k
        self.start: int | None = None
        self.last_u: int | None = None
        self._t = -1

    def observe(self, category: str) -> int | None:
        if category not in CATEGORIES:
            raise ValueError(f"unrecognised category {category!r}")
        self._t += 1
        t = self._t
        if category == "E":
            self.start = self.last_u = None
            return None
        if category == "U":
            if self.start is None or t - self.last_u - 1 > self.k:
                self.start = t
            self.last_u = t
            return t - self.start
        # D
        if self.start is not None and t - self.last_u > self.k:
            self.start = self.last_u = None
        return None if self.start is None else t - self.start


class StreamingCumulativeActiveState:
    """O(1)-memory-per-agent streaming equivalent of cumulative_active_months(): processes
    one observation at a time via observe(), matching that function's behaviour exactly
    (validated in tests/test_observation_layer.py). Added 2026-09-15 alongside
    StreamingEpisodeClockState for the feasibility-screen development runner, which needs
    every approved clock (k=0/1/3/infinity AND cumulative-active) available in streaming
    form."""

    __slots__ = ("completed",)

    def __init__(self):
        self.completed: int | None = None

    def observe(self, category: str) -> int | None:
        if category not in CATEGORIES:
            raise ValueError(f"unrecognised category {category!r}")
        if category == "E":
            self.completed = None
            return None
        if self.completed is None:
            self.completed = 0
            result = 0
            if category == "U":
                self.completed += 1
            return result
        result = self.completed
        if category == "U":
            self.completed += 1
        return result


class StreamingMonthlySummary:
    """Per-step SUFFICIENT SUMMARY for long_term_candidate_share_monthly(), accumulated one
    (agent, step) observation at a time without retaining the underlying per-agent rows: only
    a running (n_U, n_long_term_U) counter PER STEP is kept, not one row per agent per step.
    Memory scales with the number of measurement-window STEPS, not steps x agents -- the
    change `validation_manifest_2026-09-15.md` F6.6 asks for in place of holding a full
    per-agent trace for the whole window."""

    def __init__(self, threshold_months: int = 12):
        self.threshold_months = threshold_months
        self._n_u: dict[int, int] = defaultdict(int)
        self._n_long: dict[int, int] = defaultdict(int)

    def observe(self, step: int, category: str, duration: int | None) -> None:
        if category != "U":
            return
        self._n_u[step] += 1
        if duration is not None and duration >= self.threshold_months:
            self._n_long[step] += 1

    def result(self, window_steps: Iterable[int]) -> dict:
        month_shares = []
        n_empty = 0
        for step in window_steps:
            n_u = self._n_u.get(step, 0)
            if n_u == 0:
                n_empty += 1
                continue
            month_shares.append(self._n_long.get(step, 0) / n_u)
        if not month_shares:
            return dict(share=None, n_months_used=0, n_months_empty=n_empty)
        return dict(
            share=sum(month_shares) / len(month_shares),
            n_months_used=len(month_shares),
            n_months_empty=n_empty,
        )


class StreamingTransportSummary:
    """Per-step SUFFICIENT SUMMARY for transport_person_window_estimate(): running
    (sum of per-agent spend/trip ratios, traveller count) PER STEP, not one row per
    (agent, step). Supports the 'equal_person' weighting exactly; 'trip_weighted' needs only
    total spend and total trips per step, also accumulated here so both weightings can be
    recovered from the same O(steps)-sized summary."""

    def __init__(self):
        self._sum_person_ratio: dict[int, float] = defaultdict(float)
        self._n_travellers: dict[int, int] = defaultdict(int)
        self._sum_spend: dict[int, float] = defaultdict(float)
        self._sum_trips: dict[int, int] = defaultdict(int)

    def observe(self, step: int, spend: float, trips: int) -> None:
        if trips < 1:
            raise ValueError(f"observe() is for travellers only (trips>=1); got trips={trips!r}")
        self._sum_person_ratio[step] += spend / trips
        self._n_travellers[step] += 1
        self._sum_spend[step] += spend
        self._sum_trips[step] += trips

    def result(self, window_steps: Iterable[int], weighting: str = "equal_person") -> dict:
        if weighting not in ("equal_person", "trip_weighted"):
            raise ValueError(
                f"weighting must be 'equal_person' or 'trip_weighted', got {weighting!r}"
            )
        month_values = []
        n_empty = 0
        for step in window_steps:
            n = self._n_travellers.get(step, 0)
            if n == 0:
                n_empty += 1
                continue
            if weighting == "equal_person":
                month_values.append(self._sum_person_ratio[step] / n)
            else:
                month_values.append(self._sum_spend[step] / self._sum_trips[step])
        if not month_values:
            return dict(estimate=None, n_months_used=0, n_months_empty=n_empty)
        return dict(
            estimate=sum(month_values) / len(month_values),
            n_months_used=len(month_values),
            n_months_empty=n_empty,
        )
