# Approved specification, 2026-09-15

Reconciles Aakash's 2026-09-15 instruction (which incorporates Astra's
`COMPLETION_REVIEW.md` amendments) against `observation_estimation_proposal.md`'s original
proposal, resolving every contradiction Astra flagged into one implementation-ready
specification. **This is the approved specification implemented this batch by
`scripts/observation_layer.py`, `scripts/qlfs_joint_covariance_protocol.py`, and the RNG
pairing change in `src/model.py`/`src/agents.py`.** No canonical target in `data/moments.csv`
or `configs/baseline.yaml` is changed by this document or by this batch.

---

## 1. Initial capital -- fixed initialisation setting, not estimated

**Approved:** `initial_search_capital` is a documented initialisation setting, OUTSIDE the
estimated parameter vector, at its currently documented value: **1.4962** (the published fit,
per `DECISIONS_PENDING.md` line 261-262's G1 record: *"initial_search_capital treated as a
fixed initialisation setting (value 1.4962, the published fit, pending the eventual
recalibration's own choice)"*).

**Corrects `observation_estimation_proposal.md` Section 7**, which listed
`initial_search_capital` as "Estimated parameter... previously reported near its upper bound"
-- Astra's COMPLETION_REVIEW.md item 1 correctly identified this as contradicting the
already-recorded G1 decision. That listing is superseded by this document.

**Not done, per instruction:** no transient-window estimation is restored; no calibration
bound is widened. Initial-condition robustness is the ALREADY-RECORDED window-stability
finding (`DECISIONS_PENDING.md` lines 170-228): the three real calibration moments converge
by window 901-1050; the capital mean converges by window 2251-2400; the CURRENT provisional
window (2,250 steps) already sits inside the range validated for the three moments and is
close to, but at, the capital-mean threshold. **Demonstrating negligible initial-condition
influence at the selected window remains a baseline-validation question for the validation
manifest (Section 6 below), not something this document re-derives** -- failure to
demonstrate it is a baseline-validation problem, not grounds to reopen the transient window.

---

## 2. Transport fare structure -- `c(d) = a + b*d`, `a` estimated, `b` fixed

**Approved:** the flat component `a` (`search_cost_per_trip`) is ESTIMATED; the distance
slope `b` (`transport_cost_rate`) is FIXED, at its EXISTING value (0.000145 rand/grid-unit/
trip-equivalent, in wage units) as the PRIMARY scenario, with **zero, half, and double** that
value as declared sensitivity scenarios: `b in {0, 0.0000725, 0.000145, 0.00029}`.

**Corrects `observation_estimation_proposal.md` Section 5**, which proposed imposing
`a + 20*b = R12.50` as a constraint AFTER estimation -- Astra's COMPLETION_REVIEW.md item 2
correctly identified this as internally contradictory (an estimated `a` cannot simultaneously
satisfy a fixed-sum constraint) and magnitude-inconsistent (R12.50's wage-unit equivalent
implies a MUCH smaller aggregate cost than the corrected candidate target requires -- worked
below). That proposal is WITHDRAWN, not merely amended.

**R12.50 is a contextual route observation, not a binding constraint.** It informs the
PRIMARY scenario's `b` value (already the existing baseline value, unchanged) and provides
context for `a`'s admissible range (below), but does not independently identify both
components, and is not imposed as a fare ceiling at any distance.

### Admissible intercept bounds, computed to accommodate the corrected aggregate target

**Arithmetic, shown explicitly (not delegated as an inconsequential detail):**
- `daily_wage = WAGE / DAYS_PER_MONTH = 1 / 21.7 = 0.046083` (wage units; `src/moments.py`).
- Corrected candidate aggregate target (NHTS-side, unaffected by any model-side formula
  choice): `transport_budget_share` in **[0.1972, 0.1997]** (ages 15-64, driver Scenario A/B,
  `transport_measurement_specification.md`).
- Implied target average round-trip cost (wage units) = target ratio x daily_wage:
  **[0.009088, 0.009202]**.
- `E[distance_to_cbd]`: **CORRECTED** -- `uniform(township_distance_min=8,
  township_distance_max=20)` (mean 14) draws each TOWNSHIP CENTRE's distance
  (`_draw_township_centres()`, `n_townships=4` draws), not each individual agent's distance;
  an agent is then placed near a randomly assigned township centre with a Gaussian offset
  (`township_spread=2.0`) and `distance_to_cbd = max(0, raw_distance - cbd_radius)`
  (`cbd_radius=2.0`). An earlier version of this arithmetic used 14 directly, conflating the
  two. Measured empirically instead of re-derived analytically (5 seeds, `n_agents=500`,
  `configs/baseline.yaml`, mean `distance_to_cbd` over all agents at step 1-2): **11.35 to
  16.06 across seeds, average 12.19** -- used as `E[distance] ~= 12` below.
- At each `b` sensitivity scenario, the implied CENTRAL value of `a` solving
  `a + b*E[distance] = target` (a naive point, not a claim about the estimated value under
  general-equilibrium feedback through trip decisions and matching):

  | `b` scenario | `b * E[distance]` (E[distance]=12) | implied `a` (target range) |
  | --- | --- | --- |
  | 0 (zero) | 0 | 0.009088 - 0.009202 |
  | 0.0000725 (half) | 0.00087 | 0.008218 - 0.008332 |
  | 0.000145 (existing, PRIMARY) | 0.00174 | 0.007348 - 0.007462 |
  | 0.00029 (double) | 0.00348 | 0.005608 - 0.005722 |

**Recommended admissible bounds for `a`: [0.001, 0.02].** Comfortably spans every scenario's
naive central value (0.0056-0.0092, corrected) with roughly 2x headroom on each side, since
MSM estimation needs room to move away from this naive point once trip-decision and matching
feedback are accounted for, and since the bounds must remain valid across all FOUR `b`
scenarios, not just the primary one -- the correction above moves the naive central values by
only a few ten-thousandths (E[distance] fell from the wrongly-assumed 14 to ~12), well inside
this bound's existing headroom, so the recommended bounds themselves are UNCHANGED by the
correction. For comparison: the current baseline value (0.003, set under the OLD, uncorrected
0.1058 target) sits inside these bounds but well below every scenario's naive central value --
consistent with the target having moved substantially (0.1058 to ~0.1972-0.1997) since that
value was last fitted.

**Not done, per instruction:** no equation is imposed after estimation; R12.50 is not treated
as an independent identification of both `a` and `b`; no particular fitted outcome for `a` is
guaranteed or required by these bounds.

---

## 3. Search-duration clock -- k=0 primary

**Approved:** the uninterrupted active-search episode, **k=0**, is the PRIMARY clock: any
month without an active search trip ends the current episode. k=1, k=3, k=infinity, and
cumulative active-search months are retained as separately labelled SENSITIVITIES, not
folded into one range and not swapped in as primary if they happen to fit better.

**Corrects `observation_estimation_proposal.md` Section 3**, which listed the k-family as a
sensitivity SET without naming a primary -- Astra's COMPLETION_REVIEW.md item 3 correctly
identified that a sensitivity set is not a calibration specification.

**Justification (a modelling convention, not a claim about respondent behaviour):**
interpretability and a clearly defined reset event. The questionnaire does not resolve pause
treatment either way (confirmed against the full instrument, `DECISIONS_PENDING.md` Question
5) -- k=0 is chosen for being the least ambiguous convention to implement and explain, not
for fitting better. **A material, disclosed consequence:** reclassifying a `belief_inactive`
SEARCHING step as D (Section 4's mapping) ends a k=0 episode immediately on that step. If the
model then cannot reproduce a long-term-search-duration target under k=0, that is evidence
about the model/observation specification -- it must be reported as such, not used as a
reason to silently switch to a more forgiving k.

**Implemented in `scripts/observation_layer.py::episode_clock()`** (k parametrised),
`cumulative_active_months()` (the distinct estimator). See Section 5 below for the exact
observation-point/timing convention both use.

---

## 4. Observed E/U/D states -- mapping, timing, and the completed-month convention

**Approved mapping** (`observation_estimation_proposal.md` Section 2, UNCHANGED in substance
by this pass -- carried forward, not reopened):

| model state | this-step condition | observed | QLFS analogue |
| --- | --- | --- | --- |
| `EMPLOYED` | -- | E | `Status`=1 |
| `SEARCHING` | trips_this_step >= 1 | U | `Status`=2 |
| `SEARCHING` | `belief_inactive_this_step` | D | `Status`=3, "no jobs available" |
| `DISCOURAGED` | -- | D | `Status`=3, "lack of transport money" |
| *(none)* | -- | *(not represented)* | `Status`=4, Other NEA |

Stylised approximation, explicitly: the QLFS reason-code correspondence for the two D
channels is suggestive, not causal proof (`observation_estimation_proposal.md` Section 2's
own caveat, unchanged).

**Observation point, specified exactly (Astra's COMPLETION_REVIEW.md item 3's specific
request), resolving a genuine timing conflict:** `CityModel.step()` records its canonical D11
aggregate stocks (`u_t`, `disc_t`, `l_t`, `self.history`) BEFORE trip decisions (step 4, ahead
of step 5's `step_searching`), but the approved E/U/D mapping needs `belief_inactive_this_step`
(set IN step 5) to distinguish U from D. **Resolution: the E/U/D observation layer is
evaluated POST-MATCHING (after step 6), the SAME point `CityModel.trace_history` already
uses.** This is not an arbitrary third convention -- it is chosen because:
1. It is the only point at which `belief_inactive_this_step` is both SET (post step 5) and
   FINAL for the step (matching, step 6, never touches it).
2. Evaluating post-matching correctly shows an agent hired this step as EMPLOYED, matching
   `trace_history`'s own existing, deliberate, already-documented choice ("a step where an
   agent gets hired should show state=EMPLOYED at that step, not SEARCHING").
3. It reuses an existing, already-tested instrumentation point rather than adding a new one.

**The existing D11 pre-matching aggregate stocks (`self.history`'s `u`/`disc`/`l`) are KEPT
SEPARATE and UNCHANGED** -- they remain the calibration input and the matching-function's own
stock definition, per instruction ("keep matching-function stocks separately defined where
necessary"). The new E/U/D series is an ADDITIONAL, differently-timed observation of the same
underlying run, not a replacement.

**The completed-month duration convention is preserved**: `episode_clock()` and
`cumulative_active_months()` (`scripts/observation_layer.py`) both credit COMPLETED PRIOR
steps as of each step's own (post-matching) observation -- the same "credited after
measurement" convention `months_jobless` already uses (a continuously non-employed agent
reads N-1 at its Nth consecutive observation; first classified long-term, at the existing
12-month threshold, on the 13th such observation). Verified against
`DECISIONS_PENDING.md` Question 5's worked example in
`tests/test_observation_layer.py::TestEpisodeClock`/`TestCumulativeActiveMonths`, with the
resulting one-step offset from the worked example's NAIVE (non-offset) table explicitly
documented and tested, not silently introduced.

---

## 5. Transport averaging -- equal-person, then equal-month

**Approved formula** (`observation_estimation_proposal.md` Section 4, corrected arithmetic
per Astra's COMPLETION_REVIEW.md item 4): for each measurement month, the equal-weighted mean
of each traveller's own per-trip mean cost that month; those per-month cross-sectional means
are then averaged equally across measurement months. Implemented as
`scripts/observation_layer.py::transport_person_window_estimate(weighting="equal_person")`.

**Corrected worked-example arithmetic**: the three-agent, two-month fixture's equal-month
figure is `(40/3 + 5) / 2 = 55/6 ~ 9.166667`, not the previously mis-rounded 9.165 --
verified exactly in `tests/test_observation_layer.py::TestTransportPersonWindowEstimate::
test_worked_example_matches_astras_corrected_arithmetic`.

**Zero-cost traveller vs. non-traveller, explicit**: a zero-cost traveller (>=1 trip, R0
spend) contributes a real 0 to its month's per-agent mean and counts toward that month's
traveller count; a non-traveller (0 trips) contributes NO row at all and is not part of that
month's denominator.

**Empty traveller-months, explicit**: a measurement month with zero travellers is EXCLUDED
from the across-month average (`n_months_empty` reported separately), never treated as a
zero-cost observation. An undefined conditional mean is not an observed zero.

**Trip weighting is a named SENSITIVITY SCENARIO, not a bound.** Astra's COMPLETION_REVIEW.md
item 4 demonstrated numerically that neither weighting scheme is shown to bound the true
weekly-screen estimand (a schedule-dependent counterexample gives an inclusion-weighted true
mean of 50, outside both the equal-person (20) and trip-weighted (15) values in that example),
and that trip-weighting is not even uniformly the larger of the two (the plan's own original
fixture: person-mean 20 > trip-weighted 15). Both corrections are verified directly in
`tests/test_observation_layer.py::TestTransportPersonWindowEstimate::
test_trip_weighted_is_not_uniformly_an_upper_bound` and
`test_astras_counterexample_equal_person_and_trip_weighted_can_coincide`.
`transport_person_window_estimate(weighting="trip_weighted")` computes it ON MODEL HISTORIES
(not from NHTS, which cannot supply per-person trip counts) -- the sensitivity is a model-side
scenario, exactly as the review specified.

**Observation-selection sensitivity is kept separate from fare-frequency conversion**
(unchanged correction from the prior repair batch): the weighting choice above answers "how
do monthly travellers get aggregated," a different question from "how many search
days/week does a payment period cover" (the existing `transport_candidate_frequency_
sensitivity_15_64.csv` grid). Neither substitutes for the other.

---

## 6. Randomness -- streams retained, agent/month pairing implemented and frozen

**Approved and IMPLEMENTED this batch:** the existing shock/separation stream SEPARATION
(`_shock_rng`, `_separation_seed_component` in `src/model.py`) is retained unchanged. The
separation draw itself is now keyed by (separation-seed component, agent, month) via
`CityModel.paired_separation_draw()`, replacing the prior SEQUENTIAL `separation_random`
stream, which could not guarantee agent #k receives the same potential draw in the same
month across two policy arms whose employment levels have diverged. See `src/model.py`'s
`__init__` docstring and `paired_separation_draw()`'s own docstring for the full mechanism;
`tests/test_spatial.py`'s 7 new pairing tests for verification (determinism, cross-arm
agreement, independence from activation order and from advancing the model's other RNG
streams, per-agent/per-month variation, spread, and rejection of a non-seeker id).

**Implementation note, found and fixed within this batch, not left as a latent cost:** the
first working version keyed each draw via SHA-256 + a fresh `stdlib_random.Random()`
construction per call, benchmarked at ~15us/call versus the old sequential stream's ~0.3us --
a ~50x cost that measurably slowed the full test suite (630s vs. the usual ~200s for the fast
suite) and would have materially inflated the validation manifest's runtime estimate. Replaced with a grid indexed by an explicit `unique_id -> row` map (JobSeeker unique_ids are
not 0-based -- Firms are created first and claim the lowest ids), grown lazily ONE MONTH-
COLUMN AT A TIME from a persistent `np.random.Generator` with amortised (doubling) capacity --
same pairing guarantee, ~1000x cheaper per lookup. Two bugs caught and fixed within this same
batch, not left latent: (1) an initial fixed-size-at-`__init__` version (sized to
`config.n_steps+1`) raised `IndexError` under `tests/test_model.py`'s pattern of calling
`.step()` directly more times than `config.n_steps` (which only bounds `CityModel.run()`'s own
loop, not `.step()` itself) -- fixed by growing lazily instead of pre-sizing. (2) growing by
more than one column per call would silently break the "same (agent, month) value regardless
of query order/batching" guarantee, since numpy fills a multi-column draw row-major
(interleaved across agents within one call) -- verified directly (not just reasoned about) by
comparing sequential per-step queries against an out-of-order query pattern on the same model,
identical results. Incidentally, the original SHA-256 version's replacement also fixed a real,
previously-undetected sequential-vs-parallel non-determinism in `tests/test_runner.py::
test_run_many_preserves_seed_order` (root cause not fully diagnosed, superseded rather than
chased further, since the array-based design is independently the better implementation on
performance grounds alone).

**This design is FROZEN as of this commit** -- per instruction, not revisited once any
calibration or policy-comparison run begins. The shared productivity path (`_shock_rng`) is
unchanged; only the separation draw's generation mechanism changed. This is a genuine
behaviour change to realised trajectories under a fixed seed (the draw VALUES change), not a
change to the separation hazard's statistical properties.

**Order restored per COMPLETION_REVIEW.md item 6**: this decision is made and frozen BEFORE
any final calibration baseline, matching the existing plan's P3.4 placement -- not deferred to
the policy-comparison phase as the previous handoff's framing implied.

---

## 7. Reconciled parameter-role table

Supersedes `observation_estimation_proposal.md` Section 7 in full.

| role | item | value / bounds | status |
| --- | --- | --- | --- |
| Fixed initialisation setting (NOT estimated) | `initial_search_capital` | 1.4962 (published fit) | Approved, Section 1 |
| Estimated parameter | `search_cost_per_trip` (`a`) | bounds **[0.001, 0.02]** | Approved, Section 2 |
| Fixed (NOT estimated), disclosed assumption | `transport_cost_rate` (`b`) | primary 0.000145; sensitivity {0, 0.0000725, 0.00029} | Approved, Section 2 |
| Estimated parameter | `firm_kappa` | unchanged, bounds (0.2, 2.0) per existing box -- not revisited this pass | Carried forward |
| Fixed, disclosed assumption | `firm_radius` | 2.5, with the already-proposed spatial sensitivity sweep | Carried forward (`bounded_precalibration_specification.md`); NOT yet formally re-confirmed against a recalibration run under the new 2-estimated-parameter spec (search_cost_per_trip, firm_kappa only) -- flagged as a genuine remaining check in the validation manifest (Section 8) |
| Fixed input, live decision | `separation_rate` | 0.0296 (unchanged), stays FIXED this batch | **Not freed.** New transition moments (below) remain diagnostic-only pending the state-mapping/comparability decision -- see Section 8 |
| Diagnostic moment (NOT fitted) | `discouraged_share` (E/U/D candidate) | via `scripts/observation_layer.py` | New this pass; not adopted into `data/moments.csv` |
| Diagnostic moment (NOT fitted) | `long_term_share` (k=0 candidate + sensitivities) | via `scripts/observation_layer.py` | New this pass; not adopted |
| Diagnostic moment (NOT fitted) | `employment_share`, `u_to_e_quarterly`, `e_to_non_e_quarterly` | `qlfs_candidate_moments.csv`, `qlfs_joint_stock_transition_covariance.csv` | Unchanged status: diagnostic, per instruction not to silently free `separation_rate` or adopt these |
| Diagnostic only, not fitted (DECIDED, unchanged) | `distance_gradient_slope` | qualitative benchmark only | Carried forward |
