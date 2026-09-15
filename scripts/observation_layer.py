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

    Returns, for each step, the number of COMPLETED PRIOR consecutive-episode steps credited
    AS OF that step's own (post-matching) observation -- the SAME "credited after
    measurement" convention already used for `months_jobless` (a continuously non-employed
    agent reads N-1 at its Nth consecutive non-employed observation; first classified
    long-term, at the existing 12-month threshold, on its 13th such observation, not its
    12th). None where category == 'E' (duration undefined while employed).

    An episode is a maximal run of U/D steps within which no run of MORE than k consecutive D
    steps occurs since the episode's last U step (or the episode's own start, if it opened on
    a D step -- a hard-discouraged agent that resumes searching before exceeding tolerance is
    one continuous episode, not two). k=0: any D step immediately following a U step, or any
    second consecutive D step, exceeds tolerance and starts a fresh episode as of that step."""
    if k < 0:
        raise ValueError("k must be >= 0")
    out: list[int | None] = []
    completed: int | None = None  # None: no episode in progress (last observation was E)
    gap_run = 0  # consecutive D-steps since the episode's last U-step (or its start)
    for cat in categories:
        if cat not in CATEGORIES:
            raise ValueError(f"unrecognised category {cat!r}")
        if cat == "E":
            completed = None
            gap_run = 0
            out.append(None)
            continue
        if completed is None:
            completed = 0
            gap_run = 1 if cat == "D" else 0
            out.append(0)
            continue
        gap_run = 0 if cat == "U" else gap_run + 1
        if gap_run > k:
            completed = 0
            gap_run = 1  # this step is itself the D step that exceeded tolerance
            out.append(0)
            continue
        completed += 1
        out.append(completed)
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
    """Candidate long_term_share: share of (agent, step) observations classified U or D
    (the searching/discouraged stock -- the model-side analogue of QLFS's currently-unemployed
    universe under the approved mapping) whose duration clock reading is >= threshold_months.
    `duration_by_agent_step`/`categories_by_agent_step` must be the same length and in
    step-with-step correspondence (e.g. one call's output each from episode_clock()/
    cumulative_active_months() and classify_trace(), concatenated across agents)."""
    durations = list(duration_by_agent_step)
    cats = list(categories_by_agent_step)
    if len(durations) != len(cats):
        raise ValueError("duration and category sequences must have equal length")
    stock = [(d, c) for d, c in zip(durations, cats, strict=True) if c in ("U", "D")]
    if not stock:
        return dict(share=None, n_stock=0, n_long_term=0)
    n_long_term = sum(1 for d, _ in stock if d is not None and d >= threshold_months)
    return dict(
        share=n_long_term / len(stock),
        n_stock=len(stock),
        n_long_term=n_long_term,
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
