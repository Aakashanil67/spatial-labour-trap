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

## 0. Corrections (2026-09-15, second pass, per `REVIEW_AND_RECOMMENDATION.md`)

An independent review re-ran the anchor trajectory, re-derived the bound, and checked this
document's claims against the raw CSV and code directly. Six of its seven findings apply to this
file; each is corrected in place below (marked **CORRECTED**) rather than silently rewritten. All
corrections were independently re-verified against the CSV/code again before being applied here,
not merely copied from the review.

1. **Section 2.2 overstated the initial-wealth cohort's disappearance.** At anchor fare/kappa,
   seed 3, window 2 (steps 1351-1500) actually contains 40 initial-capital-supported `U`
   agent-months (11 long-term, share 0.275) -- not zero. Six candidate/seed combinations still
   have initial-cohort `U` observations in window 3 (e.g. anchor fare, kappa=0.9, seed 3: 18
   agent-months, 62.1% of that window's tiny `U` sample, though their own k=0 share there is 0).
   Corrected below: "no positive long-term reading in a window" and "the cohort has vanished" are
   different claims, and this document did not establish the second.
2. **Section 2.1's "68 cells" and "everywhere in the 3,000-step run" overstated what the CSV
   establishes.** The 68 cells are candidate x seed x window rows, not parameter/window
   combinations after seed-averaging. The three windows cover 400 of the model's 3,000 steps; the
   CSV shows zero replenished long-term observations WITHIN those windows, not at every step
   outside them. Where the theoretical bound (Section 1) independently holds for a given fare, it
   supplies the all-step conclusion; the simulation evidence alone does not. The two
   population-split rows (`k0_long_term_share_within_*_U`) are POOLED agent-month shares
   (`total_lt / total_u` across the window), not equal-month means -- corrected below.
3. **Section 2.4 misdescribed `kinf`.** `kinf` is an episode clock (the same family as k0/k1/k3,
   with near-infinite D-tolerance, `k=10**9` in `scripts/feasibility_screen.py`), not cumulative
   active months (a separate, already-distinct metric, `long_term_share_cumulative_equal_month`).
   Both reset on an `E` observation -- confirmed directly in `scripts/observation_layer.py`'s
   `episode_clock()` and `cumulative_active_months()`. The claim that `kinf` "never resets on E"
   was false and is withdrawn. `kinf` is also NOT ~0.70-0.78 at every fare/kappa: independently
   recomputed, it is exactly **0.0 in all 49 non-empty reported cells at the two higher
   `firm_kappa` values**, and ranges 0.679-0.811 only in the anchor-`firm_kappa` rows.
4. **Section 4's runtime comparison used mismatched instrumentation, now identified as (most of)
   the actual explanation.** `scripts/feasibility_screen.py`'s `--smoke-test` branch wraps the one
   anchor trajectory in `tracemalloc.start()`/`get_traced_memory()`; the production 27-trajectory
   run (`main()`'s non-smoke branch) never calls `tracemalloc` at all. So the 183.62s smoke-test
   figure paid a memory-tracking cost the actual screen never incurred, before any extrapolation
   ratio was even taken. This substantially explains, though was not re-measured to precisely
   quantify, the ~4x gap between the extrapolated (~826s) and measured (199.70s) full-screen
   times. The ~9.6-hour validation-campaign estimate in `validation_manifest_2026-09-15.md` (F6.6)
   was built the same (tracemalloc-instrumented, single-trajectory) way and should be treated as
   an overestimate for the same reason, not as a precise figure -- corrected in that file
   separately. Diagnosing this further (a matched, unprofiled batch-level smoke test) is routine
   technical work, not a decision for Aakash, and is not performed here to avoid another
   simulation run this batch.
5. **The manifest's commit fingerprint does not identify the code that actually ran.**
   `feasibility_screen_2026-09-15_manifest.json` records `code_fingerprint_git_commit: ce97697`,
   but `scripts/feasibility_screen.py` did not exist in that commit (confirmed: `git show
   ce97697:scripts/feasibility_screen.py` fails -- the file was uncommitted working-tree state
   when the screen ran, first committed afterwards at `9f4349c`). The numerical reproduction
   independently performed by the review supports the INSPECTED implementation for that
   trajectory; it does not repair this attribution gap. Recorded honestly as a historical
   provenance limitation, not corrected retroactively -- a future runner should record the
   resolved configuration, source/config input hashes, and working-tree dirty status alongside
   `HEAD`, not `HEAD` alone.
6. **The F6.4 new-moment tolerance proposal is withdrawn, not adopted.** It conflated
   three-development-seed SIMULATION spread with EMPIRICAL target uncertainty, omitted the paired
   difference's own standard error, and incorrectly implied transport/discouraged-share precision
   depends on `U` stock size (independently re-verified here: both transport weightings and the
   discouraged-share series are defined, non-null, in all 81 screen rows -- the discouraged-share
   denominator is `E+U+D`, not `U`). Withdrawal recorded in `validation_manifest_2026-09-15.md`'s
   F6.4 section directly.
7. Item 7 of the review (decision-table proposal-vs-approved status) applies to
   `REVIEW_HANDOFF.md`, not to this file, and is corrected there.

The confirmed, unaffected results: the theoretical bound (Section 1); the exceptionless
replenished-population zero result WITHIN the three sampled windows (Section 2.1, now correctly
scoped); the joint fare x kappa interaction (Section 2.3); and the k=3/cumulative-active boundary
finding, net of the `kinf` mislabelling above (Section 2.4). None of these are weakened by the
corrections -- they are stated more precisely.

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

`k0_long_term_share_within_replenished_U` -- the POOLED (`total_lt/total_u` across the window's
agent-months, not an equal-month mean) k=0 long-term share computed ONLY over agent-months
belonging to the "ever-discouraged" (replenished) population -- is **exactly 0.0 in every one of
the 68 candidate x seed x window rows where the replenished `U` stock is nonzero** (9 (`a`,
`firm_kappa`) combinations x 3 seeds x up to 3 windows each). Not "close to zero," not "small with
outliers" -- exactly `0.0`, independently recomputed from the raw CSV in this assessment
(`nonnull['share'].max() == 0.0`, `n=68`). **Scope of this claim, stated precisely**: the three
sampled windows cover 400 of the model's 3,000 steps; this is zero replenished long-term
observations WITHIN those windows, across every combination and seed tested -- not an audited
claim about every one of the 3,000 steps, which the CSV does not itself record. Where the
theoretical bound in Section 1 independently holds for a given fare (as it does for all three
target-compatible candidates), that bound supplies the all-step conclusion on its own; the 68-cell
result is corroborating simulation evidence, not a separate all-step audit.

### 2.2 The nonzero long-term share seen anywhere is entirely an initial-wealth transient

Every nonzero k0 long-term share in the whole 1,134-row output comes from
`k0_long_term_share_within_initial_capital_supported_U` (agents who have never yet been
`DISCOURAGED`, still living off their starting endowment). At the anchor `firm_kappa` (0.224),
this population's k0 share is 0.74-0.79 (a=0.00251), 0.58-0.70 (a=0.0074), 0.17-0.43 (a=0.02) in
window 1 (steps 51-150).

**CORRECTED 2026-09-15**: the original version of this paragraph claimed the initial-capital
cohort's `U` stock "collapsed to 0 in all but one cell" by window 2 and was "0 everywhere" by
window 3, and that "every `U`-classified agent-month" after window 1 belongs to the replenished
population. Independently re-checked against the raw CSV and this is not what it shows. At the
anchor fare/kappa/seed 3, window 2 (steps 1351-1500) contains 40 initial-capital-supported `U`
agent-months (11 long-term, share 0.275) -- not a rare exception, and not zero. Initial-cohort `U`
observations persist into window 3 (steps 2851-3000) in six candidate/seed combinations; e.g. at
the anchor fare, `firm_kappa`=0.9, seed 3, window 3 has 18 such agent-months, 62.1% of that
window's very small `U` sample (their own k=0 share there is 0, consistent with Section 2.1, but
the cohort itself has not disappeared). Four distinct claims must be kept separate, and this
screen establishes only some of them: (i) no POSITIVE long-term reading in a sampled window --
established, Section 2.1; (ii) no initial-cohort `U` observations in a window -- NOT established
in general, only in most cells; (iii) no initial-cohort agents left anywhere in the population --
not established at all (an agent can hold non-zero starting capital while EMPLOYED, untouched by
either the `U`/`D` classification or this screen); (iv) independence from initial conditions --
not established. `capital_all_mean`/`capital_non_employed_mean` at window ENDPOINTS (below) show
a downward trend but cannot by themselves establish a steady state or when it is reached. **The
narrower, correctly-scoped claim that survives**: the k=0 long-term share is NEVER positive for
the replenished population in any sampled window (Section 2.1), and it IS positive, transiently,
for the initial-capital cohort specifically in window 1 at the anchor `firm_kappa` -- without a
claim about that cohort's exact expiry date.

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
k0/k1.

**CORRECTED 2026-09-15**: this document previously described `kinf` as "cumulative-active, no
reset," claiming it "never resets on an `E` month." That is false and is withdrawn. `kinf` is an
EPISODE clock (the same family as k0/k1/k3, using `k=10**9` as a practically-unlimited `D`-gap
tolerance in `scripts/feasibility_screen.py`'s `CLOCK_KS`), not the separate cumulative-active-
months metric (`long_term_share_cumulative_equal_month`, computed from a genuinely distinct
collector). Both DO reset on an `E` observation -- confirmed directly in
`scripts/observation_layer.py`'s `episode_clock()` (`if cat == "E": start = last_u = None`) and
`cumulative_active_months()` (`if cat == "E": completed = None`). `kinf` is also NOT
"~0.70-0.78 at every fare and every window": independently recomputed, it is **exactly 0.0 in all
49 non-empty reported cells at the two higher `firm_kappa` values (0.9, 2.0)**, and the
0.679-0.811 range is confined to the anchor-`firm_kappa` rows only -- the same joint fare x kappa
interaction identified in Section 2.3, not a fare/kappa-independent constant.

**What survives, correctly scoped**: `long_term_share_k3_equal_month` at the anchor `firm_kappa`
and the highest tested fare does not collapse to zero across the three windows, unlike k0/k1 at
the same combination. **A tolerant-enough clock (k>=3) is not covered by the "13 consecutive"
argument, and the screen shows concretely that it does not collapse to zero the way k0/k1 do at
that specific combination** -- gaps within a tolerance window let a replenished agent accumulate a
long non-consecutive spell without ever affording 13 CONSECUTIVE trips. This is a demonstrated
boundary of the bound's scope, not a loophole invented here to rescue the k=0 target -- but it is
a narrower finding (one fare/kappa combination) than the withdrawn "kinf stays high everywhere"
claim implied.

### 2.5 The two transport weightings do not diverge at development scale

`transport_ratio_equal_person` and `transport_ratio_trip_weighted`, across all 81 non-null rows,
have nearly identical distributions (mean 0.2515 vs. 0.2513, same min/25%/50%/75%/max to 3 decimal
places). At this development scale, the choice between the two weightings does not appear to
change the reported transport moment materially -- consistent with, not proof of, a low-stakes
choice; the validation manifold keeps both without adopting either canonically, per the hold.

## 3. What remains initial-wealth-dependent

Everything that gives k=0 (or k=1) a nonzero long-term-unemployment READING in a sampled window is
the initial-capital-supported transient described in 2.2. **CORRECTED 2026-09-15**: this document
previously claimed that transient is "gone by roughly step 1,350" -- the CSV does not establish
that; initial-capital-cohort `U` agent-months persist into window 3 (steps 2851-3000) in six of
the 27 trajectories (Section 2.2). What the screen DOES establish, precisely: the initial-capital
cohort's k=0 long-term share is positive in window 1 and (where measured at all) non-positive in
windows 2 and 3 -- the transient's positive READING fades quickly even where the cohort itself has
not fully vanished. **Under the current resource rules and the approved fare range, the k=0
primary clock's long-term share is not a property of the model's long-run behaviour for the
REPLENISHED population -- it is exactly 0.0 in every sampled window (Section 2.1) -- while the
INITIAL-ENDOWMENT population can transiently register a positive share whose exact expiry this
screen does not pin down.** This was not separately re-tested at 9,000 or 30,000 steps this batch
(the held-out/validation-scale hold is respected).

## 4. Runtime estimate: a discrepancy worth flagging, not resolved

The measured full-screen wall-clock (27 trajectories, N_JOBS=6) was **199.70s** --
substantially BELOW the single-trajectory smoke test's naive extrapolation of **~826s**
(`183.62s` serial x 27 / 6). This is a ~4.1x overestimate from the extrapolation method used both
for the smoke test's own projection and for the validation manifest's re-costed ~9.6-hour
campaign estimate (`validation_manifest_2026-09-15.md`, F6.6), which was derived the same way
from the same single anchor-parameter trajectory.

**CORRECTED 2026-09-15**: this document previously reported the discrepancy's source as
undiagnosed. An independent review identified, and this assessment independently re-confirmed
against `scripts/feasibility_screen.py`'s source, a real and substantial confound: the
`--smoke-test` branch wraps the one measured trajectory in `tracemalloc.start()` /
`get_traced_memory()`; the production 27-trajectory branch (`main()`'s non-smoke path) never
calls `tracemalloc` at all. The smoke test's 183.62s therefore includes memory-tracking overhead
the actual screen never paid, before any extrapolation is even applied. The review's own
controlled four-run benchmark (same 150-step, 500-agent runner, alternating instrumentation:
3.69s / 16.81s / 3.99s / 16.10s off/on/off/on) shows `tracemalloc` alone costs roughly 4x on a
comparable workload -- enough to explain most or all of the ~4.1x gap here, though this was not
re-measured on the actual anchor trajectory to close the account precisely. **Do not treat the
~9.6-hour validation-campaign figure as precise; it was built the same (single-trajectory,
tracemalloc-instrumented) way and should be revised downward before being used to plan a launch.**
A matched, UNPROFILED batch-level smoke test at true campaign scale would be needed for a precise
figure -- this is routine technical work, not a decision for Aakash, and is not performed here to
avoid launching another simulation run this batch.

**A separate, unresolved provenance gap** (independently re-confirmed: `git show
ce97697:scripts/feasibility_screen.py` fails -- the file did not exist at that commit):
`feasibility_screen_2026-09-15_manifest.json` records `code_fingerprint_git_commit: ce97697`, but
the screen actually ran against UNCOMMITTED working-tree code (the script was first committed
afterwards, at `9f4349c`). The recorded commit hash does not identify the code that produced this
CSV. This is a genuine historical attribution gap, not repaired retroactively by the numerical
reproduction a reviewer performed against the current, now-committed implementation. A future
runner should record the fully resolved configuration plus source/config input hashes and
working-tree dirty status alongside `HEAD`, not `HEAD` alone.

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

**Update, 2026-09-15 (second pass)**: Aakash selected Option C as a bounded DESIGN
INVESTIGATION (not an implementation) following an independent review of this assessment. The
resulting economic specification -- a precise `search_capital` ledger, two parsimonious resource
alternatives, and a recommendation with equations, identification and policy-budget treatment --
is in `data/review_v2/search_capital_ledger_and_resource_design_2026-09-15.md`. This section is
left as it was written (the three options as originally weighed) rather than edited to look as if
Option C had already been chosen at the time of this assessment.

No option was recommended over another AT THE TIME THIS ASSESSMENT WAS WRITTEN; the choice was a
research judgement about what the long-term-unemployment target is meant to represent, put to
Aakash per the standing stop-and-ask protocol rather than resolved by a bounded development screen
on its own.

## 7. Holds respected

No canonical file under `results/published/`, `Data/`, `data/moments.csv`, `configs/`, or
`Draft/` was touched (verified empty diff on every path, this batch and cumulative). No held-out
simulation, full recalibration, or policy experiment was run. No clock or model mechanism was
changed to improve fit -- the budget bound and the development screen both examine the APPROVED
specification exactly as implemented. This assessment is itself the demonstrated-limitation result
called for by the standing instruction, not a step toward quietly resolving it.
