# The replenished-population search-duration budget bound: independent derivation and verification

15 September 2026. Written per Aakash's instruction to independently derive and check the
capital/search-duration bound identified in `REVIEW_AND_NEXT_BATCH.md` "The next scientific
question," against the actual transition order and every baseline cash-flow path, with small
deterministic fixtures including fares above the re-entry threshold.

**Verdict: the bound is confirmed, with the underlying mechanism more precise than the
review's own one-paragraph statement (which is correct in its conclusion but does not spell
out that the affordability bounce-back happens WITHIN a single step, not across several).**
Verified directly against `src/model.py`'s `step()` and `src/agents.py`'s `step_discouraged`/
`can_afford_one_trip`, not merely re-derived on paper.

## 1. The two cash-flow facts the bound rests on, verified against the code directly

1. **Capital increases ONLY in the hard `DISCOURAGED` state, by exactly `household_inflow`
   (g) per step** (`step_discouraged()`, `src/agents.py`: `self.search_capital +=
   cfg.household_inflow`).
2. **Capital NEVER increases in `SEARCHING`** -- `step_searching()` only ever subtracts
   (`self.search_capital -= self.trips_this_step * self.cost_per_trip`; zero trips leaves it
   unchanged). There is no household-inflow term, no wage, no other credit anywhere in
   `step_searching()`. `EMPLOYED` agents' capital is untouched entirely (`step_employed()`
   never references `search_capital`).

**Consequence, stated precisely**: once an agent exits hard `DISCOURAGED` back into
`SEARCHING`, the capital it holds AT THAT MOMENT is the ENTIRE budget available to fund
every subsequent trip until it either runs out again (re-entering `DISCOURAGED`) or is hired.
Nothing tops it up along the way.

## 2. The re-entry capital bound, re-derived from the exact step() order

`CityModel.step()`'s order (`src/model.py`, unchanged by this review's repairs): (1)
separations, (2) re-entry (`step_discouraged`, which adds g THEN checks `capital >=
reentry_threshold` (r) and flips to `SEARCHING` if so), (3) capital-exhaustion check
(`can_afford_one_trip`, i.e. `capital >= cost_per_trip` (c); a `SEARCHING` agent that fails
this is sent back to `DISCOURAGED` IMMEDIATELY, in the SAME step, before D11 stocks are even
recorded), (4) D11 stocks, (5) trip decisions, (6) matching.

**The mechanism, precisely, including the within-step bounce the review's prose does not
spell out**: on any given step where a `DISCOURAGED` agent's capital (after adding g) first
reaches `r`, step 2 flips it to `SEARCHING`. Step 3 runs IMMEDIATELY AFTER, in the SAME
step, and re-checks affordability against `c`. If `c > r` and the agent's newly-incremented
capital has crossed `r` but not yet `c`, step 3 sends it straight back to `DISCOURAGED` --
all within one `step()` call. This repeats, invisibly to `trace_history` (which only records
the state at the END of the step), for as many steps as it takes for the accumulating g to
also clear `c`. The trace shows the agent as continuously `DISCOURAGED` throughout this
process; only the terminal step, where it finally clears both bars, shows `SEARCHING`.

**The bound**: let `x` be the agent's capital the step BEFORE it finally clears
`max(r, c)`. By construction `x < max(r, c)` (otherwise it would have cleared on an earlier
step). The step it clears, its capital is `x + g < max(r, c) + g`. This holds identically
whether `c < r` (the transition-threshold `r` binds first, and the agent's very first
`SEARCHING` step already affords a trip) or `c >= r` (the affordability bar `c` binds,
after however many single-step bounces are needed).

**Search-duration consequence**: the k=0 primary clock's 12-month long-term threshold is
first met on the 13th CONSECUTIVE `U` observation (verified in
`tests/test_observation_layer.py::TestEpisodeClock::
test_12_month_threshold_is_not_reached_until_the_13th_consecutive_u`). Sustaining 13
consecutive `U` months requires spending at least `13c` (one trip/month, the cheapest
possible path to `U`), and -- since capital never replenishes while `SEARCHING` -- that
entire `13c` must be affordable from the re-entry capital ALONE: `13c <= x + g < max(r,c) +
g`. **Infeasible whenever `13c >= max(r, c) + g`.**

With `r=0.035`, `g=0.008` (`configs/baseline.yaml`): `max(r,c)+g` equals `0.043` for `c<=r`
and `c+0.008` for `c>=r`. Solving `13c >= max(r,c)+g`:
- For `c <= r`: `13c >= 0.043` iff `c >= 0.0033077`.
- For `c >= r`: `13c >= c+0.008` iff `12c >= 0.008` iff `c >= 0.0006667` -- always true in
  this branch since `c>=r=0.035 >> 0.0006667`.

**So the bound binds for essentially every economically plausible fare**: any `c >
0.0033077` makes a full 13-month `U` streak funded entirely from a fresh re-entry balance
IMPOSSIBLE. The three `search_cost_per_trip` values `approved_specification_2026-09-15.md`
computed as target-compatible (~0.0051-0.0092, all with the primary `b`=0.000145 adding
still more per unit distance) are all comfortably above this cutoff -- confirmed numerically
below, not merely asserted.

## 3. Deterministic fixtures (verified directly against the live model, not a hand simulation)

Two fixtures, both run through the ACTUAL `CityModel.step()` sequence (not a standalone
re-implementation of the transition logic), isolating one probe agent (every other agent
parked `EMPLOYED` so nothing else perturbs the run):

**Fixture A, `c < r`** (`search_cost_per_trip=0.003`, `transport_cost_rate=0`, so
`c=0.003`): probe starts `DISCOURAGED` with `search_capital=0.0`. Re-enters `SEARCHING`
after 5 steps at `capital=0.040` -- confirmed `r <= 0.040 < r+g` (`0.035 <= 0.040 <
0.043`), and `can_afford_one_trip()` is `True` immediately (no bounce needed, since `c<r`
means the very step it clears `r` it already clears `c` too).

**Fixture B, `c > r`** (`search_cost_per_trip=0.1`, `transport_cost_rate=0`, so `c=0.1`):
probe's trace shows `DISCOURAGED` continuously from step 1 through step 12 (capital rising
by exactly `g=0.008` each step: 0.008, 0.016, ..., 0.096), then `SEARCHING` at step 13,
`capital=0.104`. Confirmed `c <= 0.104 < c+g` (`0.1 <= 0.104 < 0.108`) -- matching
`max(r,c)+g = max(0.035, 0.1) + 0.008 = 0.108` exactly. The within-step bounce (Section 2)
is confirmed to be happening but invisible in the trace at steps 1-12: internally, the
re-entry check fires and is immediately reversed by the exhaustion check every one of those
12 steps, and only the terminal state is recorded.

Both fixtures committed as `tests/test_model.py::test_capital_at_reentry_is_bounded_...`
(below).

## 4. Numeric application to the approved specification's target-compatible intercepts

`13c >= max(r,c)+g` evaluated at each Tier-2 candidate (`transport_cost_rate` fixed at the
PRIMARY 0.000145, so `c = a` for a zero-distance agent, larger for any positive distance --
the bound only gets MORE binding at positive distance, so `d=0` is the most favourable case
for feasibility and is used below):

| candidate `a` | `c` at `d=0` | `max(r,c)+g` | `13c` | infeasible? |
| --- | --- | --- | --- | --- |
| 0.00509 (T2.1) | 0.00509 | 0.043 | 0.06617 | YES (0.06617 > 0.043) |
| 0.00712 (T2.2, primary) | 0.00712 | 0.043 | 0.09256 | YES |
| 0.00915 (T2.3) | 0.00915 | 0.043 | 0.11895 | YES |

**All three are infeasible for the replenished population, even at zero distance** --
confirming the review's own headline number (0.09256 at `a=0.00712`) and extending it to the
other two Tier-2 points, which the review did not individually check.

## 5. Scope, stated precisely (not overclaimed)

This bound applies EXACTLY to: an agent's FIRST `U`-eligible re-entry into `SEARCHING`
after a hard `DISCOURAGED` spell, under the CURRENT baseline cash-flow rules (no other
capital source), evaluated against the k=0 PRIMARY clock's 12-month (13-observation)
threshold specifically.

**It does NOT establish**:
- That every finite-run statistic must be exactly zero -- an agent could still reach a
  SHORTER long-term-adjacent duration, or a different threshold, or benefit from multiple
  discouragement/re-entry cycles that each fund a few months (though each such cycle is
  itself capped by the same bound, so summing several never-quite-reaching-13 stretches
  under k=0's strict reset does not help -- k=0 resets on ANY gap, so cycles cannot be
  concatenated into one longer credited episode).
- That every point in the parameter box is infeasible -- a sufficiently small `a` (e.g. the
  admissible lower bound 0.001) is NOT covered by this bound (`13*0.001=0.013 < 0.043`) --
  feasible in principle, though far below the target-compatible range.
- That a proposed POLICY with additional cash flows (e.g. a wage or transport subsidy) obeys
  the same bound -- any new inflow while `SEARCHING` would directly break the "capital never
  replenishes while searching" premise Section 1 relies on.
- Anything about agents who have NEVER been hard-discouraged and are still spending down
  their INITIAL capital (`initial_search_capital=1.4962`, ~200x a typical re-entry balance)
  -- those agents are not bound by this argument at all. Section 3's fixtures and this
  document's derivation concern ONLY the REPLENISHED (post-exhaustion) population. The
  development screen (`scripts/feasibility_screen.py`) measures the split between these two
  populations directly, rather than assuming it.

## 6. What this means for interpreting the demo's zero-share finding

The prior batches' 0% k=0 long-term-share finding (100-agent illustrative run) is NOT
resolved or explained away by this bound alone -- it is CONSISTENT with it for whatever
share of that run's `U` population had already been hard-discouraged at least once. The
development screen (item 3 of this batch) measures this split directly at baseline
population scale, across three windows, rather than asserting it from the bound.
