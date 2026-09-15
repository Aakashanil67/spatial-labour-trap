# Bounded validation campaign: exact execution manifest

15 September 2026. **Specification only -- NOT executed. No held-out simulation, no
calibration, no policy campaign is authorised or run by this document.** Written per
Aakash's 2026-09-15 instruction and Astra's `COMPLETION_REVIEW.md` item 6 (audit the seed
blocks, give actual joint candidate vectors, use the approved observation definitions,
re-derive runtime from measured throughput, keep the reference explicitly unvalidated).

## 0. Correction to the prior manifest sketch

The `REVIEW_HANDOFF.md` v3 sketch described the `adaptive_pilot_v2` development trajectories
as using a "5001-5015" seed block. **That was wrong, audited here:** `scripts/
adaptive_burn_in_pilot.py` imports and uses `CALIBRATION_SEEDS` directly
(`from src.calibrate import CALIBRATION_SEEDS`), which `src/config.py` defines as
`tuple(range(1, 16))` -- seeds **1-15**, the SAME seeds the published calibration itself
uses, not a separate development block. `VALIDATION_SEEDS` (`src/config.py`) is
`tuple(range(1001, 1051))` -- seeds **1001-1050**, 50 seeds, already reserved and disjoint.

**Fresh seed block for this campaign: 2001-2015 (15 seeds).** Disjoint from both
`CALIBRATION_SEEDS` (1-15) and `VALIDATION_SEEDS` (1001-1050) -- audited directly against
`src/config.py`, not assumed.

## 1. Candidate parameter vectors -- genuine joint perturbations, listed exactly

Per the approved specification (`approved_specification_2026-09-15.md`), only TWO parameters
are estimated: `search_cost_per_trip` and `firm_kappa` (`initial_search_capital` is fixed at
1.4962; `firm_radius` is fixed at 2.5). The anchor point uses the PUBLISHED starting values
(`results/published/calibration_result.json`): `search_cost_per_trip=0.002514642203001423`,
`firm_kappa=0.22393789239458572` -- NOT yet re-estimated under the new fare-structure bounds
(Section 2 of the approved specification); this campaign checks the NEIGHBOURHOOD around
these starting values, not a re-estimated point (re-estimation is a separate, later step).

**A genuine 3x3 joint grid** (both parameters varied together, not one-at-a-time):

| candidate | `search_cost_per_trip` | `firm_kappa` |
| --- | --- | --- |
| C1 | 0.0018860 (0.75x) | 0.1679534 (0.75x) |
| C2 | 0.0018860 (0.75x) | 0.2239379 (1.00x) |
| C3 | 0.0018860 (0.75x) | 0.2799224 (1.25x) |
| C4 | 0.0025146 (1.00x) | 0.1679534 (0.75x) |
| **C5 (anchor)** | **0.0025146 (1.00x)** | **0.2239379 (1.00x)** |
| C6 | 0.0025146 (1.00x) | 0.2799224 (1.25x) |
| C7 | 0.0031433 (1.25x) | 0.1679534 (0.75x) |
| C8 | 0.0031433 (1.25x) | 0.2239379 (1.00x) |
| C9 | 0.0031433 (1.25x) | 0.2799224 (1.25x) |

**Reused, not rerun** (already verified in `adaptive_pilot_v2`, per "keep previously verified
checks closed"): the three slow `firm_kappa` exploration-box extremes (0.9, 1.4, 2.0) at the
published `search_cost_per_trip`. These remain UNRESOLVED-by-9,000 reference points; C1-C9
above are the NEW neighbourhood check this campaign adds.

**All 9 candidates use the approved fixed roles**: `initial_search_capital=1.4962`,
`firm_radius=2.5`, `transport_cost_rate=0.000145` (primary slope scenario -- the b-sensitivity
scenarios in Section 2 of the approved specification are a SEPARATE, not-yet-scoped campaign,
since they interact with the still-unresolved fare-intercept bounds and are not run here).

## 2. Fresh seeds

**2001-2015** (15 seeds, matching `CALIBRATION_SEEDS`' and `adaptive_pilot_v2`'s own count).
Every candidate x every seed = **9 x 15 = 135 runs** for the main campaign.

## 3. Observation definitions -- the APPROVED ones, not the old clock/transport/capital roles

Astra's COMPLETION_REVIEW.md item 6: "diagnostics under the old clock, transport estimator or
initial-capital parameter vector do not validate an altered calibration specification." This
campaign collects:
- The three retained calibration moments (`discouraged_share`, `transport_budget_share`,
  `long_term_share`) exactly as `adaptive_pilot_v2` already does -- UNCHANGED, since the
  canonical D11 pre-matching stock convention and `data/moments.csv`'s targets are not
  altered by this batch.
- **NEW**: the k=0 PRIMARY long-term-share candidate (`scripts/observation_layer.py`'s
  `episode_clock(k=0)` + `long_term_candidate_share()`), plus k=1, k=3, k=infinity and
  cumulative-active-months as labelled sensitivities -- requires full per-agent tracing
  (`trace_agent_ids` set to ALL agents for this campaign, not the usual small handful), a
  materially larger `trace_history` than any prior run in this repository has collected.
- **NEW**: the equal-person-then-equal-month transport candidate
  (`transport_person_window_estimate(weighting="equal_person")`) alongside the existing
  pooled trip-mean, from the SAME per-agent trace.
- **ALL FOUR** capital diagnostics (`capital_all_mean`, `capital_all_q50`,
  `capital_non_employed_mean`, `capital_non_employed_q50`) -- per the Deliverable-3 finding
  that the mean and median can disagree sharply, collected from the start this time, not
  added after the fact.
- `distance_gradient_slope`: computed and recorded (informational only, not a stopping
  criterion, per the existing rule -- unchanged).

**Full per-agent tracing at this scale is a real, new cost** (not present in
`adaptive_pilot_v2`, which traces zero or a handful of agents): `trace_history` grows by
roughly `n_agents x n_steps` rows per run. At `n_agents=500` (baseline scale, unlike the
demo's 100) and 9,000 steps, that is 4.5 million trace rows PER RUN -- Section 5's runtime
estimate does not include the added serialisation/memory cost of this, which has not been
benchmarked; flagged as a real, unestimated risk, not silently absorbed into the headline
number.

## 4. Reference-verification check

The existing 15,000-step reference is unvalidated against a longer window (flagged by Astra,
not previously acted on). **Two points get an extended 30,000-step reference run**: C5 (the
anchor) and C9 (the joint grid's fastest-converging-least corner, `search_cost_per_trip`=1.25x,
`firm_kappa`=1.25x, i.e. the point furthest from the anchor in the direction already known to
be slower). Each at all 15 fresh seeds (2001-2015): **2 x 15 = 30 runs at 30,000 steps.**

**Acceptance check**: for each of the three retained calibration moments and all four capital
diagnostics, compute the PAIRED (same-seed) difference between the 15,000-step and
30,000-step readings, then report BOTH the mean difference across the 15 seeds AND its
standard deviation across those same 15 seeds -- per Astra's instruction, an observed gap at
one seed (or even a nonzero mean across seeds smaller than its own seed-to-seed spread) is not
by itself proof of continued deterministic drift; the SE of the paired difference is the
correct comparison, not the raw difference alone. **The 15,000-step reference stays labelled
UNVALIDATED until this check runs and is reported.**

## 5. Computational cap and unresolved-candidate treatment

Unchanged from the existing specification: 9,000-step cap for the main campaign's adaptive
evaluation; `nan` loss (not a penalty) for any candidate the local-trend rule never accepts by
that cap; mandatory disclosure of how much of the checked neighbourhood was unresolved; every
candidate still gets a fixed-9,000-step reading recorded and validated regardless of the
adaptive rule's own decision (Deliverable 3's Table A/B convention, carried forward).

## 6. Runtime estimate, re-derived from MEASURED throughput

**Measured this session, not assumed**: `adaptive_pilot_v2`'s own collection pass
(`bounded_precalibration_specification.md`) ran 4 candidates x 15 seeds = 60 runs to 15,000
steps each, in 1,395s wall-clock at `N_JOBS=6` (`scripts/adaptive_burn_in_pilot.py`).
Per-run cost at 6-way parallelism: `1395s / (60 runs / 6 workers) = 1395 / 10 = 139.5s` per
15,000-step run -> **0.0093 s/step**, single-worker-equivalent throughput on this machine.

| component | runs | steps/run | single-worker seconds | wall-clock at N_JOBS=6 |
| --- | --- | --- | --- | --- |
| Main campaign (C1-C9 x 15 seeds) | 135 | 9,000 | 135 x 9,000 x 0.0093 = 11,300s | ~1,883s (~31 min) |
| Reference verification (C5, C9 x 15 seeds) | 30 | 30,000 | 30 x 30,000 x 0.0093 = 8,370s | ~1,395s (~23 min) |
| **Total** | **165** | -- | **19,670s** | **~3,278s (~55 min)** |

**Explicitly NOT included in this estimate** (flagged, not silently absorbed): the added
memory/serialisation cost of full-population per-agent tracing (Section 3) at baseline scale
(500 agents), which has not been benchmarked and could be materially larger than the bare
step-time throughput above suggests -- a real risk to re-check with a short smoke test before
committing to the full 165-run campaign, not assumed away here. **Do not carry this
estimate into a differently-sized campaign without re-deriving it from a fresh throughput
measurement at that campaign's own trace-collection settings.**

## 7. What this campaign would decide

Whether the neighbourhood around the published starting point (C1-C9) shows the same
capital-criterion pattern Table A/B found at the single fitted point checked so far (passes
cleanly) or starts to show the mean-capital failure seen in the slow `firm_kappa` exploration-
box extremes; whether the 15,000-step reference itself is settled against a 30,000-step
check; and gives the first real candidate readings for the k=0 primary long-term-share clock
and the equal-person transport estimator at baseline population scale, not just the 100-agent
illustrative run in `scripts/demo_observation_layer_run.py`.

**Not decided by this campaign, and not authorised to be launched by this document**: any
choice among the C.8 burn-in protocol candidates (current local-trend rule / fixed 9,000-step
/ longer fixed horizon / disclosed capital-bar relaxation) -- this campaign's OUTPUT would
inform that choice, not make it. No recalibration, held-out validation, or policy campaign
follows automatically from running this manifest.
