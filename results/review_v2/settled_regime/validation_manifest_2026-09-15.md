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
Section 2's table, all at the PRIMARY `b` = 0.000145):

| candidate | `search_cost_per_trip` | `firm_kappa` | rationale |
| --- | --- | --- | --- |
| T2.1 | 0.00509 | 0.22394 (anchor) | central estimate if `b` were double (context only; this run still uses primary `b`) |
| T2.2 | 0.00712 | 0.22394 | central estimate under the PRIMARY `b` scenario itself |
| T2.3 | 0.00915 | 0.22394 | central estimate if `b` were zero (context only; this run still uses primary `b`) |

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
model run (as smoke-tested), not full per-agent tracing. Runtime below already assumes this.

## Runtime estimate, re-derived from these measurements

Using **0.0095 s/step** (single-worker-equivalent; slightly above both measured figures --
0.00917 untraced, 0.00749 live-streaming-hooked -- for a small conservative margin) and
`N_JOBS=6`:

| component | runs | steps/run | total steps | single-worker seconds | wall-clock at N_JOBS=6 |
| --- | --- | --- | --- | --- | --- |
| Main campaign (15 candidates x 15 seeds) | 225 | 9,000 | 2,025,000 | 19,237.5s | ~3,206s (~53 min) |
| Reference verification (3 candidates x 15 seeds) | 45 | 30,000 | 1,350,000 | 12,825s | ~2,137.5s (~36 min) |
| **Total** | **270** | -- | -- | **32,062.5s** | **~5,343s (~89 min)** |

Streaming-collector memory is negligible at this scale (megabytes, not gigabytes) -- the
27 GB full-tracing risk identified above does not apply to this design.

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
