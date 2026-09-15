# Bounded feasibility assessment: does the corrected observation layer support the k=0 primary
# long-term-unemployment moment under the approved specification?

15 September 2026. Written per `REVIEW_AND_NEXT_BATCH.md`'s "Recommended instruction to Claude,"
item 6: one feasibility assessment covering what the budget bound proves, what the development
runs show, what remains initial-wealth-dependent, and whether a full validation campaign is worth
launching -- with, if infeasible, the smallest defensible alternatives presented but NOT
implemented. This is a DEVELOPMENT-scale finding (3 seeds, 3,000 steps, `n_agents=500`), not a
held-out or validation-scale result; no canonical file, held-out simulation, recalibration or
policy experiment was touched to produce it.

Evidence base: `data/review_v2/replenished_capital_budget_bound.md` (the theoretical bound, with
its two verified deterministic fixtures and end-to-end model verification) and
`feasibility_screen_2026-09-15.csv` / `feasibility_screen_2026-09-15_manifest.json` (the
development screen: 27 trajectories = 3 `search_cost_per_trip` values x 3 `firm_kappa` values x 3
seeds, 3,000 steps each, 1,134 rows across 14 metrics and 3 windows; commit `f2fb021`..`50ea012`;
CSV `sha256=7f5d293823c1ba8b0b3b900028c198714e6f0c4c7d594bb4e8cf359ff35d5ed9`, independently
recomputed and matched against the manifest in this assessment).

## 1. What the bound proves, on paper

`data/review_v2/replenished_capital_budget_bound.md` shows, verified directly against
`src/agents.py`'s `step_discouraged()`/`can_afford_one_trip()` and `src/model.py`'s `step()`
order (not merely re-derived by hand): capital replenishes ONLY while `DISCOURAGED`, at rate `g`
(`household_inflow`) per step; it never replenishes while `SEARCHING` or `EMPLOYED`. The capital
an agent holds the instant it re-enters `SEARCHING` is therefore bounded above by
`max(reentry_threshold, cost_per_trip) + g`, and that bound is the ENTIRE budget available to fund
every subsequent trip until the agent is hired or exhausts it again. Sustaining the k=0 clock's
13-consecutive-`U` threshold (the 12-month long-term-unemployment cutoff) costs at least `13c`
(one trip/month, the cheapest path). With the baseline `r=0.035`, `g=0.008`: **infeasible whenever
`13c >= max(r,c)+g`, which binds for any `c > 0.0033077`** -- comfortably below all three
target-compatible fare candidates (~0.0057-0.0091) computed in
`approved_specification_2026-09-15.md`.

This is a structural, deterministic argument about the model's cash-flow rules. It says nothing
by itself about how OFTEN the bound actually matters in a running population, how large the
"initial-wealth-exempt" transient is, or whether other clock tolerances (k=1/3/infinity) are
covered by the same argument. That is what the development screen was built to check.

## 2. What the development screen shows, empirically

### 2.1 The bound's prediction is confirmed with zero exceptions, not merely "mostly"

`k0_long_term_share_within_replenished_U` -- the k=0 equal-month long-term share computed ONLY
over agent-months belonging to the "ever-discouraged" (replenished) population -- is **exactly
0.0 in every one of the 68 (parameter-combination x window) cells where the replenished `U` stock
is nonzero**, across all 9 (`a`, `firm_kappa`) combinations, all 3 seeds, all 3 windows. Not "close
to zero," not "small with outliers" -- exactly `0.0`, independently recomputed from the raw CSV in
this assessment (`nonnull['share'].max() == 0.0`, `n=68`). This is the strongest empirical
confirmation the bound could have produced at development scale: a replenished agent never once
sustains a 13-consecutive-`U` streak, anywhere in the grid, anywhere in the 3,000-step run.

### 2.2 The nonzero long-term share seen anywhere is entirely an initial-wealth transient

Every nonzero k0 long-term share in the whole 1,134-row output comes from
`k0_long_term_share_within_initial_capital_supported_U` (agents who have never yet been
`DISCOURAGED`, still living off their starting endowment) -- and ONLY in window 1 (steps 51-150).
At the anchor `firm_kappa` (0.224), this population's k0 share is 0.74-0.79 (a=0.00251),
0.58-0.70 (a=0.0074), 0.17-0.43 (a=0.02) in window 1. By window 2 (steps 1351-1500) its `n_stock`
has collapsed to 0 in all but one cell (40 agent-months, share 0.275, at the lowest fare/seed 3),
and by window 3 it is 0 everywhere. **The entire population that can ever register k=0 long-term
unemployment is the initial-endowment cohort, and it is exhausted well before step 1,351.** After
that point, every `U`-classified agent-month in the run belongs to the replenished population,
whose k0 long-term share is the confirmed, exceptionless 0.0 from Section 2.1.

`capital_all_mean` (0.745 -> 0.246 -> 0.108 across the 3 windows, averaged over all 27
trajectories) and `capital_non_employed_mean` (0.131 -> 0.018 -> 0.019) show the same transition
directly in the capital distribution: the population's aggregate wealth decays from the initial
endowment toward a low, replenished-population-dominated steady state, and the k=0 long-term-share
transient tracks that decay almost exactly in timing.

### 2.3 A genuine joint fare x kappa interaction, not previously tested (resolves F6.2's gap at
### development scale)

At `firm_kappa` in {0.9, 2.0}, the `U`-classified stock is small-to-empty (`n_months_used` in the
single digits to low dozens, out of 100-150 possible months) at EVERY fare level tested, in EVERY
window -- matching efficiency alone suppresses sustained unemployment almost entirely, regardless
of the fare. The transient described in 2.2 is visible only at the anchor `firm_kappa`. **The
interaction is not mild: higher `firm_kappa` does not merely shrink the transient, it removes the
`U` population it would act on.** This directly answers F6.2's "known interaction remains
untested" complaint (see the manifest's F6.2 addendum) -- at development scale, not yet at
validation scale.

### 2.4 A boundary the bound does NOT cover, found by the screen, not assumed away

The bound in Section 1 is specifically about the k=0 (zero-tolerance, 13-CONSECUTIVE-`U`) clock.
`long_term_share_k3_equal_month` (3-month tolerance) at the anchor `firm_kappa` and the HIGHEST
fare (a=0.02) is 0.611 / 0.592 / 0.626 across the three windows -- roughly CONSTANT, not decaying
like k0/k1 do. At the two lower fares under k3 it still collapses to ~0 by window 2/3, matching
k0/k1. `long_term_share_kinf_equal_month` (cumulative-active, no reset) stays around 0.70-0.78
throughout, at every fare and every window, by construction (it never resets on an `E` month the
way the finite-k clocks do). **A tolerant-enough clock (k>=3, or the cumulative-active
sensitivity) is not covered by the "13 consecutive" argument, and the screen shows concretely that
it does not collapse to zero the way k0/k1 do** -- gaps within a tolerance window let a
replenished agent accumulate a long non-consecutive spell without ever affording 13 CONSECUTIVE
trips. This is a demonstrated boundary of the bound's scope, not a loophole invented here to
rescue the k=0 target.

### 2.5 The two transport weightings do not diverge at development scale

`transport_ratio_equal_person` and `transport_ratio_trip_weighted`, across all 81 non-null rows,
have nearly identical distributions (mean 0.2515 vs. 0.2513, same min/25%/50%/75%/max to 3 decimal
places). At this development scale, the choice between the two weightings does not appear to
change the reported transport moment materially -- consistent with, not proof of, a low-stakes
choice; the validation manifold keeps both without adopting either canonically, per the hold.

## 3. What remains initial-wealth-dependent

Everything that gives k=0 (or k=1) a nonzero long-term-unemployment reading in this specification
is the initial-capital-supported transient described in 2.2, and it is gone by roughly step 1,350
of a 3,000-step run. **Under the current resource rules and the approved fare range, the k=0
primary clock's long-term share is not a property of the model's long-run behaviour -- it is a
property of how the population was seeded, decaying to exactly zero once that seed is spent.** A
longer run does not fix this; it only shrinks the window in which any k=0 long-term unemployment
can be observed at all. This was not separately re-tested at 9,000 or 30,000 steps this batch (the
held-out/validation-scale hold is respected) -- it follows directly from the confirmed-exceptionless
0.0 replenished-population result plus the observed exhaustion timing, not from a new run at that
scale.

## 4. Runtime estimate: a discrepancy worth flagging, not resolved

The measured full-screen wall-clock (27 trajectories, N_JOBS=6) was **199.70s** --
substantially BELOW the single-trajectory smoke test's naive extrapolation of **~826s**
(`183.62s` serial x 27 / 6). This is a ~4.1x overestimate from the extrapolation method used both
for the smoke test's own projection and for the validation manifest's re-costed ~9.6-hour
campaign estimate (`validation_manifest_2026-09-15.md`, F6.6), which was derived the same way
from the same single anchor-parameter trajectory. **The source of the discrepancy was not
diagnosed this batch** (candidates: JIT/allocator warm-up counted once in the serial smoke test,
joblib worker-startup overhead amortised differently across 27 short jobs vs. one long one, or
genuine per-trajectory cost variation across parameter combinations with very different `U`-stock
sizes) -- it is reported as an open question, not silently resolved in either direction. **Do not
treat the ~9.6-hour validation-campaign figure as precise; it was built with the same
extrapolation method that just overestimated by ~4x on a directly comparable workload.** A
batch-level (not single-trajectory) smoke test at true campaign scale (15 candidates, a handful of
seeds, 9,000 steps) would be needed before that number is used to plan a launch -- not performed
this batch, consistent with the hold on the validation-scale campaign itself.

## 5. Judgement: is a full ~9.6-hour (or, per Section 4, uncertain) validation campaign worth
## launching now?

**No, not as currently specified, without a decision from Aakash first.** The reasoning is not
about cost -- it is that the primary target moment (k=0 equal-month long-term share, matched
against the QLFS 12-month threshold) is, on this development-scale evidence, structurally unable
to hold a nonzero long-run value under the current resource rules at any economically plausible
fare. A 15-candidate, 15-seed, 9,000-30,000-step campaign built around that moment would spend
several hours (magnitude uncertain per Section 4) largely re-confirming the same
initial-wealth-transient-then-zero pattern already visible at 3,000 steps and 3 seeds, unless the
campaign is redesigned around a moment or a mechanism that survives the bound. This is a
demonstrated limitation, not a reason to keep the finding quiet or to adjust the model to produce
a better-looking number -- per your explicit instruction, it is reported as a completed, valid
result.

## 6. Smallest defensible alternatives, presented for Aakash's decision, NOT implemented

None of the following were built, tested, or partially implemented this batch. They are listed in
increasing order of how much they change the approved specification.

**Option A -- run the campaign as specified anyway, and report the near-zero k=0 result
honestly.** Cheapest to execute (no design change). Consequence: the calibration/acceptance
exercise for the k=0 primary moment would very likely report a near-zero simulated value against
a nonzero QLFS target across most or all of the campaign's window, i.e. a large, structural
residual -- a legitimate finding, but one whose main information content (the model cannot
currently reproduce sustained long-term unemployment under its own resource rules) is already
established by this development screen at a fraction of the cost.

**Option B -- adopt a higher-tolerance clock (k=3, or a similar bounded tolerance) as the primary
long-term-unemployment target instead of k=0.** Section 2.4 shows this clock does NOT collapse to
zero the way k0/k1 do, at the anchor `firm_kappa` and higher fares. Consequence: this changes what
the target statistic measures relative to QLFS's own 12-months-with-no-explicit-tolerance
definition (`Q36TIMESEEK`) -- it would need its own re-justification against the survey
question's actual tolerance for reporting gaps, not simply be substituted in because it produces a
non-zero number. This is exactly the kind of "change the clock to improve fit" move the standing
instruction prohibits doing unilaterally; it is listed here as an option for Aakash, not adopted.

**Option C -- revisit the resource-replenishment rule (`household_inflow` rate `g`, or the
`reentry_threshold` `r`) so that `13c < max(r,c)+g` becomes achievable at the approved fare
range.** This is a genuine model-mechanism change and is explicitly out of scope under the
standing hold ("do not change the clock or model mechanisms to improve fit"); listed only as the
alternative that would most directly address the mechanism the bound identifies, for a future
batch if one is authorised, with its own justification and sensitivity analysis, not as a fix
applied here.

No option is recommended over another here; the choice is a research judgement about what the
long-term-unemployment target is meant to represent, which is Aakash's decision per the standing
stop-and-ask protocol, not something a bounded development screen resolves on its own.

## 7. Holds respected

No canonical file under `results/published/`, `Data/`, `data/moments.csv`, `configs/`, or
`Draft/` was touched (verified empty diff on every path, this batch and cumulative). No held-out
simulation, full recalibration, or policy experiment was run. No clock or model mechanism was
changed to improve fit -- the budget bound and the development screen both examine the APPROVED
specification exactly as implemented. This assessment is itself the demonstrated-limitation result
called for by the standing instruction, not a step toward quietly resolving it.
