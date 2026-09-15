# Bounded validation campaign: exact execution manifest (v2, corrected)

15 September 2026. **Specification only -- NOT executed. No held-out simulation, no
calibration, no policy campaign is authorised or run by this document.** This is the SECOND
version. Astra's `REVIEW_FOLLOWUP.md` (F6) found six defects in the first version -- a seed
block that was not actually fresh, historical trajectories cited as if they validated the
CHANGED implementation, an inadmissible grid (three points below the retained `firm_kappa`
lower bound), acceptance criteria checked only against the OLD moments, unspecified
reference-comparison scope and tolerances, and an unmeasured, likely-underestimated storage
cost. All six are corrected below with a stated rationale, not a silent renumbering.

## F6.1 -- A genuinely fresh, disjoint seed block

**Corrected.** The prior "2001-2015" block was not fresh: `WEIGHT_SEEDS` in
`src/calibrate.py` is `tuple(range(2001, 2051))` -- entirely overlapping. Audited every
seed-block constant actually declared in the codebase, not only `src/config.py`:

| Block | Range | Source |
| --- | --- | --- |
| `CALIBRATION_SEEDS` | 1-15 | `src/config.py:106` |
| `VALIDATION_SEEDS` | 1001-1050 | `src/config.py:107` |
| `WEIGHT_SEEDS` | 2001-2050 | `src/calibrate.py:66` |
| `REPLICATE_SEEDS` | 3001-3050 | `scripts/assess_settled_regime.py:57` |
| `SENSITIVITY_SEEDS` | 3001-3008 | `scripts/assess_settled_regime.py:58` (subset of the above) |
| `WINDOW_SEEDS` | 3001-3015 | `scripts/assess_settled_regime.py:59` (subset of the above) |

**Fresh block for this campaign: 4001-4015 (15 seeds)** -- confirmed disjoint from every
block above by direct inspection, not by construction alone.

## F6.2 -- Historical slow-candidate trajectories relabelled; contemporary stress candidates added

**Corrected.** The `adaptive_pilot_v2` trajectories for `firm_kappa` in {0.9, 1.4, 2.0}
predate: the agent/month-paired separation draw (replacing the sequential
`separation_random` stream), `firm_radius` fixed at 2.5 (as opposed to whatever value was in
force when those trajectories were generated), and the corrected observation definitions
(F1-F4 above). They remain valid AS HISTORICAL FINDINGS about the pre-repair implementation
(e.g. the whole-population-mean-capital-fails-but-median-passes pattern is a property of the
model's capital dynamics, not of the separation-draw mechanism, and is not expected to change)
-- but they DO NOT validate the current specification and must not be cited as if they did.

**Tier 3 below (contemporary slow/high-kappa stress candidates) reuses the SAME `firm_kappa`
values (0.9, 1.4, 2.0)**, so that a future run can be compared directly against the
historical trajectories at matched parameter values -- but is NOT launched in this repair
batch, consistent with the standing hold.

### F6.2 continued -- the joint-interaction gap, addressed at development scale, not yet at
### validation scale

**Corrected 2026-09-15** (`REVIEW_AND_NEXT_BATCH.md` F6.2: "the known interaction remains
untested... adding a few selected joint stress points does not require all nine possible
extra combinations"). This batch's DEVELOPMENT feasibility screen
(`scripts/feasibility_screen.py`, `results/review_v2/settled_regime/feasibility_screen_2026-09-15.csv`)
runs the FULL 3x3 joint grid of `search_cost_per_trip` (`a` in
{0.002514642203001423, 0.0074, 0.02}) x `firm_kappa` (in {0.22393789239458572, 0.9, 2.0}) --
all 9 combinations, not a marginal single-axis sweep -- at development scale (3 seeds, 3,000
steps, not the 15-seed/9,000-step validation campaign). **This closes the "untested
interaction" gap at development scale only.** It does NOT replace the validation-scale Tier
1/2/3 design above, which still holds `firm_kappa` fixed at the anchor while Tier 2 varies
the fare intercept, and holds the fare intercept fixed at the anchor while Tier 3 varies
`firm_kappa` -- no joint Tier-2 x Tier-3 combination is in the 15-candidate validation grid.

**What the development screen's joint coverage actually shows** (see the companion
feasibility-assessment handoff for the full numeric table): the fare-intercept x kappa
interaction is not mild. At the anchor `firm_kappa` (0.224), all three fare levels produce
a stock of `U`-classified agent-months large enough to measure a k=0 equal-month long-term
share in window 1. At `firm_kappa`=0.9 or 2.0, the `U` stock collapses to a handful of
agent-months or zero at EVERY fare level tested and EVERY window -- the interaction is that
higher `firm_kappa` (faster/more efficient matching) suppresses sustained unemployment
almost entirely, regardless of the fare. This is a genuine, previously-untested joint
finding, not an assumption.

**Implication for the validation-scale campaign's tier design, stated as an open question,
not resolved here**: if a validation-scale run is authorised, the development screen's
result raises the concrete possibility that Tier 3 (`firm_kappa` in {0.9, 1.4, 2.0}, at the
ANCHOR fare only) will show near-zero `U` stock and therefore near-empty long-term-share
statistics for the SAME reason seen here at development scale -- in which case Tier 3 alone,
without a joint Tier-2 x Tier-3 cross, may not be sufficient to characterise convergence at
the higher-kappa, higher-fare region simultaneously. Whether to add a small number of joint
Tier-2 x Tier-3 points to the validation grid (increasing it beyond 15 candidates) is a
decision for Aakash, informed by this development-scale evidence, not decided in this batch.

## F6.3 -- An admissible, honestly-tiered candidate grid

**Corrected.** The prior grid's `{0.75x, 1.0x, 1.25x}` multiplicative perturbation of
`firm_kappa`'s anchor (0.22393789239458572) put three of nine points at ~0.16795 --
BELOW the retained lower bound of 0.2, outside the box entirely. Separately, the prior
grid's `search_cost_per_trip` values (perturbing the OLD anchor by +-25%, landing in
0.0019-0.0031) sample nowhere near the corrected specification's admissible bounds
([0.001, 0.02]; plausible target-compatible central values ~0.0051-0.0092, per
`approved_specification_2026-09-15.md` Section 2) -- the grid was checking a neighbourhood
the fare-intercept correction has already moved away from.

**Replaced with three explicitly labelled tiers**, not a single undifferentiated grid:

**Tier 1 -- neighbourhood of the published starting point (bounds-respecting; exploratory,
NOT claimed target-compatible):**

| candidate | `search_cost_per_trip` | `firm_kappa` |
| --- | --- | --- |
| T1.1 | 0.0018860 (0.75x anchor) | 0.20000 (clamped to the retained lower bound) |
| T1.2 | 0.0018860 | 0.22394 (anchor) |
| T1.3 | 0.0018860 | 0.31351 (1.4x anchor) |
| T1.4 | 0.0025146 (anchor) | 0.20000 |
| **T1.5 (anchor)** | **0.0025146** | **0.22394** |
| T1.6 | 0.0025146 | 0.31351 |
| T1.7 | 0.0031433 (1.25x anchor) | 0.20000 |
| T1.8 | 0.0031433 | 0.22394 |
| T1.9 | 0.0031433 | 0.31351 |

**Tier 2 -- target-compatible fare-intercept probe** (firm_kappa held at the anchor; `a`
spans the admissible-bounds central estimates computed in `approved_specification_2026-09-15.md`
Section 2's table, all at the PRIMARY `b` = 0.000145).

**CORRECTED 2026-09-15** (`REVIEW_AND_NEXT_BATCH.md` "F6 is improved" item 4): the previous
version of this table gave 0.00509/0.00712/0.00915 as these central estimates, which do not
match `approved_specification_2026-09-15.md`'s own corrected table (its four `b`-scenario
central values are the MIDPOINTS of the ranges given there: `0.009088-0.009202` for `b=0`,
`0.008218-0.008332` for `b`=half, `0.007348-0.007462` for the PRIMARY `b`, and
`0.005608-0.005722` for `b`=double). Recomputed correctly below, as actual midpoints of
those ranges, not re-derived from scratch:

| candidate | `search_cost_per_trip` | `firm_kappa` | rationale |
| --- | --- | --- | --- |
| T2.1 | 0.005665 | 0.22394 (anchor) | midpoint of 0.005608-0.005722, the central estimate IF `b` were double (context only; this run still uses the primary `b`) |
| T2.2 | 0.007405 | 0.22394 | midpoint of 0.007348-0.007462, the central estimate under the PRIMARY `b` scenario itself |
| T2.3 | 0.009145 | 0.22394 | midpoint of 0.009088-0.009202, the central estimate IF `b` were zero (context only; this run still uses the primary `b`) |

**Tier 3 -- contemporary slow/high-kappa stress candidates** (F6.2; `search_cost_per_trip`
held at the anchor, matching the historical setup for direct comparability):

| candidate | `search_cost_per_trip` | `firm_kappa` |
| --- | --- | --- |
| T3.1 | 0.0025146 (anchor) | 0.9 |
| T3.2 | 0.0025146 | 1.4 |
| T3.3 | 0.0025146 | 2.0 |

**15 candidates total** (9 + 3 + 3), each x 15 seeds = 225 runs for the main 9,000-step
campaign. **What this design can and cannot support, stated explicitly**: Tier 1 and Tier 3
characterise convergence NEAR the published starting point and at the historically-slow
region, respectively; Tier 2 characterises convergence at a plausible POST-re-estimation
intercept, holding `firm_kappa` fixed at the anchor -- it does NOT explore how convergence at
a higher intercept interacts with a different `firm_kappa` (no joint Tier-2-x-Tier-3 cross
is included, to keep the campaign at 15 candidates; flagged as a real gap, not silently
covered).

## F6.4 -- Corrected (new) moments used in acceptance and reference checks, via the streaming collector

**Corrected.** The prior manifest specified collecting the OLD canonical moments only,
merely mentioning the new observation-layer series as an afterthought -- which the review
correctly identified as not qualifying the new specification at all.

**This campaign's acceptance and reference checks use BOTH series, collected from the SAME
run:**
- OLD (unchanged): `discouraged_share`, `transport_budget_share`, `long_term_share`,
  `distance_gradient_slope`, from `self.history`/`self.cell_history` (the D11 pre-matching
  convention, untouched).
- NEW: the k=0 PRIMARY long-term-share candidate (plus k=1/3/infinity and cumulative-active
  sensitivities) and the equal-person transport candidate, computed via the STREAMING
  collectors added this pass (`scripts/observation_layer.py`'s `StreamingEpisodeClockState`,
  `StreamingMonthlySummary`, `StreamingTransportSummary`) hooked at the SAME post-matching
  observation point `trace_history` already uses -- NOT via full per-agent trace collection
  (see F6.6 for why).

### F6.4 continued -- the new discouraged-share series, explicitly defined and placed

**Corrected 2026-09-15** (`REVIEW_AND_NEXT_BATCH.md` "F6 is improved" item 1): a NEW E/U/D
discouraged-share candidate is now defined and implemented (`scripts/feasibility_screen.py`,
metric `discouraged_share_EUD_post_matching_equal_month`):
`share_t = n_D(t) / (n_E(t) + n_U(t) + n_D(t))`, evaluated at the POST-MATCHING observation
point (the same point the whole observation layer uses), equal-month-averaged across a
window exactly like `long_term_candidate_share_monthly()`. **This is explicitly NOT the same
quantity as the OLD D11 pre-matching `discouraged_share`** (`self.history`'s `discouraged`
column, from `src/moments.py::discouraged_share()`) -- the old series is measured BEFORE trip
decisions and matching each step; the new series is measured AFTER, and uses the approved
`belief_inactive_this_step`-based mapping to fold belief-driven inactivity into D. The two
are collected and reported SEPARATELY in the campaign design; neither is relabelled as the
other.

### F6.4 continued -- numerical acceptance tolerances for the new moments, pre-registered

**Corrected 2026-09-15**: F6.5's tolerances below apply to the OLD moments only (they have an
existing `combined_se` from `precision_decomposition.csv`, itself computed under the OLD
clock/transport definitions -- reusing it for the NEW moments would be invalid, exactly as
the review warns). The new moments (k=0 primary long-term share, both transport weightings,
the new discouraged-share series) had NO empirical uncertainty evidence at all until this
batch's development screen (`scripts/feasibility_screen.py`) produced the first one: a small
(`n=3` development seeds), explicitly noisy, seed-to-seed SPREAD at each of the screen's 9
parameter combinations. **Proposed tolerance, using this evidence, stated with its unit and
its limitation up front**: for each new moment, at each Tier-1/2/3 validation candidate,
declare practical equivalence between the 9,000-step and 30,000-step reference readings only
if the paired difference is smaller in magnitude than the LARGER of (a) the development
screen's own across-seed standard deviation at the nearest matching parameter combination
(a genuinely empirical, if noisy, scale) or (b) an absolute floor of 0.01 (one percentage
point of share, chosen as a round, conservative floor given the `n=3` estimate's own
uncertainty is not itself well quantified). **This is a PROPOSAL for Aakash's approval, not
an adopted acceptance rule** -- `n=3` is too small to trust as a precise SE, and the floor is
a judgement call, disclosed as such rather than hidden inside a precise-looking number.

**Filled in with the actual development-screen spread** (`feasibility_screen_2026-09-15.csv`,
27 trajectories = 9 parameter combinations x 3 seeds; computed for
`discouraged_share_EUD_post_matching_equal_month`): the across-seed standard deviation at each
of the 9 (`a`, `firm_kappa`) combinations, pooled over the 3 windows, ranges from 0.00004
(highest fare x highest kappa, near-empty stock) up to **0.03029** (anchor fare x anchor kappa,
window 3) -- mean 0.00778 across all 27 combination/window cells. Applying the proposed rule
with the observed MAXIMUM as the "nearest matching combination" scale for the anchor-region
candidates (T1.*, T2.*) and the 0.01 floor elsewhere gives a concrete, non-hypothetical number:
**tolerance = max(per-combination seed std, 0.01)**, which evaluates to approximately 0.01
(floor-bound) for every combination except the anchor-fare/anchor-kappa region, where it rises to
~0.02-0.03 (std-bound). For the k=0/k=1 primary long-term-share clocks specifically, the `n=3`
seed stock was frequently too small (`n_stock` in the single digits, or zero) at the higher-kappa
combinations to compute a meaningful standard deviation at all.

**WITHDRAWN, 2026-09-15 (second pass), per an independent review's correction 6**: the rule
above is NOT adopted, and should not be used. It conflates three-development-seed SIMULATION
spread with EMPIRICAL (QLFS/NHTS) target uncertainty -- the model estimator changing does not
make the existing survey-based `combined_se` evidence (F6.5) cease to exist or become
inapplicable in principle; it omits the estimated PAIRED DIFFERENCE's own standard error from the
comparison rule entirely; and it perversely permits MORE drift exactly where the simulation is
noisiest, rather than less. It also incorrectly implied that the two transport weightings and the
discouraged-share series have precision problems tied to a small `U` stock -- independently
re-verified false: `transport_ratio_equal_person`, `transport_ratio_trip_weighted`, and
`discouraged_share_EUD_post_matching_equal_month` are all non-null in every one of the screen's 81
rows (the discouraged-share denominator is `E+U+D`, not `U`; transport includes genuine hire-month
travellers regardless of the concurrent `U` stock). Only the k=0/k=1 long-term-share CLOCKS
themselves are `U`-stock-limited at `n=3` seeds, as stated above. Once the model/observation
specification is settled, a practical tolerance should be proposed anchored to the APPROPRIATE
empirical uncertainty for each moment (existing `combined_se` for old moments; a separately
estimated empirical uncertainty for new ones, not simulation spread), with simulation error
estimated separately from it, and an uncertainty-aware paired reference comparison -- not
requested of Aakash as an arbitrary SD-floor choice before that groundwork is done.

## F6.5 -- Reference comparisons and tolerances, specified exactly

**Corrected.** The prior manifest extended-referenced only 2 of 9 candidates and gave no
numerical tolerance for "practical equivalence," leaving open the possibility of tuning a
judgement call after seeing results.

**Exactly which candidates get a 30,000-step reference-verification run, and why (NOT all
15 -- cost-bounded, stated explicitly):**

| candidate | reference? | why |
| --- | --- | --- |
| T1.5 (anchor) | YES | the actual published starting point; everything else is a perturbation around it |
| T2.2 (primary-`b`-scenario intercept) | YES | the specific point the fare-intercept correction is aimed at |
| T3.3 (`firm_kappa`=2.0) | YES | the historically slowest-converging corner, most likely to still be unresolved at 9,000 steps |
| all other 12 candidates | NO | not extended this campaign; their 9,000-step (fixed-horizon) or adaptive-acceptance reading is reported WITHOUT a longer-window comparison, and is explicitly flagged as such in the output -- not silently presented as equivalent in confidence to the three reference-checked candidates |

3 candidates x 15 fresh seeds x 30,000 steps = **45 reference runs**.

**Numerical tolerances, PRE-REGISTERED here (not to be adjusted after seeing outcomes):**
for each of the three reference-checked candidates, compute the PAIRED (same-seed)
difference between the 15,000-step and 30,000-step readings for every moment (old and new).
Report the paired-difference MEAN, its standard error (`SD / sqrt(15)`, the correct
paired-difference SE, not a raw single-run gap), and declare **practical equivalence** only
if `|mean paired difference| + 1.96 * SE < tolerance`, where:
- For the three combined-SE-bearing moments (`discouraged_share`, `transport_budget_share`,
  `long_term_share`): `tolerance = 0.1 * combined_se` (a fifth of the existing 0.5-combined-SE
  acceptance bar used elsewhere in this project, so the reference check does not itself
  consume the whole existing tolerance budget).
- For the four capital diagnostics: `tolerance = 5%` of the reference's own level (a quarter
  of the existing 20% capital acceptance bar).
- For the new observation-layer candidates (k=0 long-term-share, equal-person transport):
  no pre-existing combined-SE or acceptance bar exists yet -- report the paired difference
  and its SE descriptively, without a pass/fail declaration, since no tolerance for these has
  been approved. Proposing one is a decision for a future batch, not invented here.

**A failure to detect a trend is NOT sufficient evidence that remaining drift is small
enough** -- the tolerance above is an explicit bound on the ESTIMATED difference plus its
uncertainty, not merely "the point estimate looks close" or "no significant trend by eye."

## F6.6 -- Storage and memory: measured, not assumed; a streaming collector built and validated

**Corrected, with real measurements, not a hand-waved extrapolation.** The prior manifest's
"4.5 million trace rows at 9,000 steps" was correct as far as it went but did not state the
memory cost in bytes, did not extrapolate the compounding effect of 6-way parallelism, and
proposed no alternative to full per-agent tracing.

**Measured this pass** (`configs/baseline.yaml`, `n_agents=500`, `n_steps=900`, one run):

| collection method | wall-clock | s/step | peak memory (tracemalloc) |
| --- | --- | --- | --- |
| No tracing (canonical moments only) | 8.25s | 0.00917 | not separately measured (baseline) |
| Full per-agent trace (`trace_agent_ids`=all 500) | 35.43s | 0.03937 | 135.5 MB for 450,000 rows (~301 bytes/row) |
| Streaming collectors, LIVE-hooked into the step loop | 6.75s | 0.00749 | not separately measured; within normal run-to-run variance of the untraced baseline |

**Full tracing costs ~4.3x the untraced baseline and ~301 bytes/row.** Extrapolated (not
re-measured) to this campaign's actual scale: 500 agents x 9,000 steps = 4.5 million rows
(~1.35 GB) per run; at the 30,000-step reference length, 15 million rows (~4.5 GB) per run --
and critically, **before parallel workers are counted**: at `N_JOBS=6`, up to SIX such
reference runs could be resident simultaneously, i.e. up to ~27 GB, a real and previously
unstated risk.

**The streaming collectors (`StreamingEpisodeClockState`, `StreamingMonthlySummary`,
`StreamingTransportSummary`, added this pass) avoid this entirely**: memory scales with
`O(n_agents)` tiny per-agent state objects (three ints each, via `__slots__`) plus
`O(n_steps)` summary-dict entries, not `O(n_agents x n_steps)` trace rows. **Validated against
full-batch computation on small fixtures** (`tests/test_observation_layer.py`:
`TestStreamingEpisodeClockState`, `TestStreamingMonthlySummary`, `TestStreamingTransportSummary`
-- exact agreement on the worked examples, 50 randomised sequences, and a direct
`transport_person_window_estimate()` cross-check). **A short development-only smoke test**
(measured this pass, not a held-out campaign): live-hooking the streaming collectors into an
actual 900-step, 500-agent run gave 0.00749 s/step -- AT OR BELOW the untraced baseline's own
0.00917 s/step, i.e. the streaming overhead is not distinguishable from ordinary run-to-run
variance at this scale, consistent with (not merely asserted alongside) a separate synthetic
benchmark of the collectors alone (4.5 million observations processed in 3.65s, ~0.81
microseconds/observation).

**Recommendation for the eventual campaign**: hook the streaming collectors into the live
model run (as smoke-tested), not full per-agent tracing.

## CORRECTED 2026-09-15 (`REVIEW_AND_NEXT_BATCH.md` "F6 is improved" item 3): the runtime
## estimate below was based on a LIGHTER collector than the campaign actually needs

The 0.00749 s/step figure above came from a smoke test hooking only THREE collectors
(episode clock at one `k`, one monthly summary, one transport summary) -- not the FULL set
F6.4 requires (all four approved episode-clock tolerances plus cumulative-active, the new
discouraged-share series, and capital snapshots, together). That fuller collector is now
built and measured for the first time in this batch, as `scripts/feasibility_screen.py`'s
`run_one_trajectory()` -- the "reproduced executable deliverable" the review asked for, not
a described-but-uncommitted inline script.

**Measured** (`--smoke-test`, one trajectory: anchor `a`, anchor `firm_kappa`, seed=1,
3,000 steps, `n_agents`=500): **183.62s wall-clock, 0.06121 s/step, 30.8 MB peak traced
memory.** This is **~8.2x** the earlier lighter-collector figure (0.00749 s/step) -- the
extra clocks, the replenished-vs-initial-capital tracking, and the per-window capital
snapshots are not free, and the earlier estimate significantly understated them.

**Runtime re-estimated using this measured, full-collector figure** (not the lighter one),
`N_JOBS=6`:

| component | runs | steps/run | total steps | single-worker seconds (0.06121 s/step) | wall-clock at N_JOBS=6 |
| --- | --- | --- | --- | --- | --- |
| Main campaign (15 candidates x 15 seeds) | 225 | 9,000 | 2,025,000 | 123,950s | ~20,658s (~5.7 hours) |
| Reference verification (3 candidates x 15 seeds) | 45 | 30,000 | 1,350,000 | 82,633s | ~13,772s (~3.8 hours) |
| **Total (full collector)** | **270** | -- | -- | **206,583s** | **~34,430s (~9.6 hours)** |

**This is the honest, currently-best estimate for collecting every approved-clock
sensitivity plus capital snapshots at validation scale -- materially larger than the
previous ~89-minute figure, which is now WITHDRAWN as understated, not merely superseded.**
Memory stays negligible either way (megabytes; the streaming design's `O(agents)+O(steps)`
footprint, not `O(agents x steps)`, is unaffected by which clocks are collected).

**A cheaper alternative, offered but not adopted here**: a REDUCED collector computing only
the k=0 PRIMARY clock, one transport weighting, and the discouraged-share candidate (skipping
k=1/k=3/k=infinity/cumulative-active and the second transport weighting, which are
sensitivities, not primary acceptance criteria) would cost proportionally less, plausibly
close to the lighter smoke test's 0.00749-0.02 s/step range -- not measured this pass, since
building a second, reduced collector variant is additional implementation work beyond this
batch's smoke-test scope. **Whether to accept the ~9.6-hour full-collector cost, build and
measure the reduced variant, or reduce the candidate/reference counts is a decision for
Aakash, not resolved here.**

## Computational cap and unresolved-candidate treatment

Unchanged in substance: 9,000-step cap for the main campaign's adaptive evaluation; `nan`
loss (not a penalty) for any candidate the local-trend rule never accepts by that cap;
mandatory disclosure of how much of the checked neighbourhood was unresolved; every candidate
still gets a fixed-9,000-step reading recorded regardless of the adaptive rule's own
decision. **Explicitly, per instruction**: an unresolved evaluation must never be reported as
a valid stationary loss, and the campaign's design (Tier 1/2/3 above) must not be narrowed
for computational convenience without disclosing that the narrowing occurred and what it
excludes.

## What this campaign would decide

Whether the neighbourhood around the published starting point (Tier 1), a plausible
post-re-estimation fare intercept (Tier 2), and the historically-slow region under the
CURRENT specification (Tier 3) show the same capital-criterion pattern found at the single
previously-checked fitted point; whether the 15,000-step reference is settled against a
30,000-step check for the three reference-verified candidates specifically (not generalised
to the other 12); and gives the first baseline-scale readings for the k=0 primary
long-term-share candidate and the equal-person transport candidate, computed cheaply via the
streaming collectors rather than requiring full-population tracing.

**Not decided by this campaign, and not authorised to be launched by this document**: any
choice among burn-in protocol candidates, any canonical target adoption, any recalibration,
any policy comparison. This manifest is a cost-and-design specification only.
