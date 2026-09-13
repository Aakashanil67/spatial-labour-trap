# Bounded pre-calibration specification

Presented before any further pilot implementation, per Aakash's instruction of 2026-09-13,
updated the same day once Aakash reviewed it and approved one bounded development round.
Status as of this revision: sections 1-3 corrected and re-verified against real data; section 4's
redesigned convergence rule is **built, corrected once more after an independently-found
development failure, and verified against both the existing development trajectories and a
fresh capital-diagnostics collection pass -- all four quantitative development criteria pass**;
section 5 proposes the held-out validation design, **not yet launched**, pending confirmation
given its added cost; section 6 specifies unresolved-candidate handling for an eventual
integrated search. Nothing here is integrated into `calibrate.py`, and `firm_kappa`'s calibration
bounds stay at (0.2, 2.0) -- kept, not narrowed for computational convenience.

---

## 1. The transient-window bug, confirmed and fixed

`scripts/assess_identification.py`'s `_window_config(base, burn_in, window_length)` computed
`n_steps = burn_in + window_length`. Reused for both the settled window (correct: a 150-step
window starting *after* a 2,250-step burn-in genuinely is steps 2251-2400) and the transient
window (wrong: `configs/baseline.yaml`'s own published config is `burn_in_steps=50,
n_steps=150` -- the window is steps 51-150, a **100-step** window, not a 150-step one running to
step 200). Every "transient_51-150" figure this analysis previously reported was actually computed
over steps 51-200.

**Fixed** (`scripts/assess_identification.py`, commit pending): the transient window is now built
directly from `configs/baseline.yaml`'s own `n_steps`/`burn_in_steps`, not through the
burn-in-plus-length helper. Corrected `precision_decomposition.csv`, transient window only
(settled-window figures were never affected -- that computation was always correct):

| moment | sim share of variance (was, wrong window) | sim share of variance (corrected, true 51-150) |
| --- | --- | --- |
| `distance_gradient_slope` | 2.3% | 1.9% |
| `discouraged_share` | 84.5% | 82.3% |
| `transport_budget_share` | 4.6% | 4.6% |
| `long_term_share` | 56.6% | 58.1% |

The qualitative story is unchanged (`distance_gradient_slope` negligible, `discouraged_share`
dominant, `transport_budget_share` negligible, `long_term_share` substantial), and every number
moves by at most 2.6 percentage points. The bug did not overturn a conclusion, but the earlier
figures were not what they were labelled, and are corrected here rather than left standing.

---

## 2. Target correspondence and uncertainty treatment, target by target

**P2.1 is a partial desk audit, stated as such, not a completed source audit.** It reviewed the
existing notebooks' own code and documentation; three of its four findings (missingness
conflation, missing age filter, geography undocumented) are still unconfirmed against the actual
microdata, since this session has no `THESIS_DATA_ROOT` access. The fourth -- the spatial
target's denominator -- is now independently confirmed, below.

### `discouraged_share`, `long_term_share` (QLFS)

Model counterpart correspondence checked and holds: `long_term_share`'s denominator (`u`, the
model's SEARCHING stock) matches QLFS's narrow Unemployed universe, which itself excludes
discouraged workers, exactly as QLFS's own category does. Uncertainty is Kish-approximated
(no PSU/rotation field in any of the four extracts, confirmed by the design-variable audit in
notebook 03) -- a known, documented approximation, not newly found here. Age (15+ vs 15-64) and
geography remain open per P2.1's existing findings; not re-litigated in this specification.

### `transport_budget_share` (NHTS)

Two findings stand from P2.1, unresolved pending live data: the missingness conflation
(`Unspecified` and `Not applicable` cost sentinels both treated as zero) and the complete
absence of an age filter. Neither is corrected here -- both need `THESIS_DATA_ROOT` access to
quantify and fix, which this session does not have.

### `distance_gradient_slope` (Baez and Kshirsagar 2026) -- denominator mismatch CONFIRMED, not merely suspected

Checked directly against the paper's own text (`Literature/baez_full.txt` in the thesis repo,
lines 799-801, and Table 5b's own title, p.38 printed): *"We present similar regressions using
the share of working-age adults employed, drawn from the 2011 census (Table 5b)."* Table 5b is
titled "Spatial Correlates of Share of the **Adult Population** Employed." This is unambiguous:
the paper's dependent variable is the working-age **population** employment share (denominator:
every working-age adult), not a labour-force employment share (denominator: only those employed
or searching). `src/moments.py`'s `distance_gradient_slope()` is necessarily labour-force-based,
since the model has no non-labour-force agent type at all -- every agent is employed, searching,
or discouraged.

**The mismatch cannot be cleanly corrected with the available source.** Decomposing the
paper's own measure: `Employed/Population = (Employed/LabourForce) x (LabourForce/Population)`,
i.e. the reported slope is `e'(x)*p(x) + e(x)*p'(x)` where `e(x)` is the model's own estimand
(labour-force-based employment rate at travel-time percentile `x`) and `p(x)` is the
labour-force participation rate at that percentile. Recovering `e'(x)` from the paper's reported
`d(E/Pop)/dx` alone requires knowing `p(x)` and `p'(x)` separately -- information the paper does
not report, and no participation-by-distance profile appears anywhere in the extracted text
(`Literature/baez_full.txt` checked directly for "participat", "activity rate", "NEET" and
"not economically active" -- no matches beyond one unrelated aggregate figure).

**Recommendation (not decided; presented as three ranked options):**

1. **Demote it from a fitted MSM target to an external, out-of-sample check**, alongside
   Banerjee and Sequeira's already-analogous role. This is the most defensible option given
   what has accumulated around this one moment across the review: a unit mismatch already
   corrected once (D6), a near-flat local identification direction along `firm_radius` (section
   3), the largest share of the objective despite the worst fit at the published optimum (51.4%
   of the objective, 17.7% of target, per `calibrate.py`'s own docstring), and now a confirmed
   estimand mismatch with no available correction. Cost: the calibration becomes three parameters
   fitted against three moments plus this demoted parameter's role in the estimated set needs
   re-examining (see section 3's caveat on target-set-conditionality).
2. **Keep it as a target, document the mismatch as an accepted approximation with a stated,
   unsigned direction of bias** (if participation falls with distance from the CBD, which is
   plausible but not evidenced here, the paper's slope would be *steeper* than the model's own
   labour-force-based one, since it conflates the compositional and employment-rate channels in
   the same direction) -- cheapest, but reports a moment against a target that measures something
   the model structurally cannot represent, understated only as a caveat.
3. **Find or construct an independent South African participation-by-distance profile** to
   correct the paper's slope before using it as a target -- the most rigorous option, and the
   most expensive; not attempted here, and would need its own source audit before it could be
   trusted any more than the current mismatch.

---

## 3. Identification, rescaled and checked for robustness -- conditional on the target set and weights used

The earlier local-identification check computed `J'WJ`'s eigenvalues from a raw-unit Jacobian --
comparing curvature "per unit of `search_cost_per_trip`" (a quantity whose entire calibration box
is 0.0045 wide) against curvature "per unit of `firm_radius`" (box width 3.0) is not a fair
comparison, for exactly the reason `calibrate.py`'s own docstring already warns a weight matrix's
raw diagonal magnitude is not evidence about identification. Corrected: each parameter's Jacobian
column is rescaled by its own calibration-box width (`DEFAULT_BOUNDS`), so every column now reads
"moment change if this parameter traverses its whole search box" -- a common, comparable scale.

**Rescaling changes the number by about 200x, but not the qualitative conclusion.** Raw condition
number: 24,483,235. Box-width-rescaled condition number: 122,356 -- two orders of magnitude
smaller, confirming the raw-unit comparison substantially overstated how ill-conditioned the
system is, exactly as expected once `firm_radius`'s 3.0-wide box and `search_cost_per_trip`'s
0.0045-wide box are put on the same footing. It remains large: `firm_radius` is still the
near-flat direction, not a artefact of unit choice.

**Robustness sweep (0.02, 0.05, 0.10 relative step) -- the direction is stable, the magnitude is
not, and that pattern is itself informative:**

| relative step | rescaled smallest eigenvalue | rescaled condition number | smallest-eigenvalue eigenvector (search_cost, firm_radius, firm_kappa) |
| --- | --- | --- | --- |
| 0.02 | 28.8 | 63,410 | (-0.17, **0.98**, -0.00) |
| 0.05 | 13.1 | 122,356 | (-0.04, **-1.00**, -0.00) |
| 0.10 | 0.61 | 2,331,000 | (-0.04, **1.00**, -0.00) |

The near-null direction is overwhelmingly `firm_radius` at every step size tested (component
magnitude 0.98-1.00, `search_cost_per_trip` and `firm_kappa` both near zero throughout) --
**this part of the finding is robust**, not an artefact of the 5% step originally chosen. The
smallest eigenvalue itself, however, shrinks monotonically as the step grows (28.8 -> 13.1 ->
0.61), not scattering randomly -- which is consistent with, not contradictory to, the
already-documented flat region along this axis (`DECISIONS.md`, "`firm_radius`=4.1 and 6.0
produced identical histories"): a larger perturbation is probing further into a genuinely
extended plateau and correctly finding even less curvature there, rather than the estimate
becoming noisier. **The headline number (122,356, at the 5% step) should be read as an
order-of-magnitude finding, not a precise one** -- resolving it further would need either a
higher-order finite-difference scheme or more replicate seeds per evaluation, neither attempted
here.

**This check is conditional, not absolute, and is stated as such going forward:** identification
here means identification *given* the four moments in `data/moments.csv`, *given* the settled
window (2251-2400), and *given* the settled-window weight matrix built from section 1's corrected
`combined_cov`. Changing any of the three -- dropping `distance_gradient_slope` per section 2's
recommendation, choosing a different window, or a different weighting scheme -- changes the
information matrix and can change which direction (if any) is poorly identified. None of this
claims a parameter is intrinsically unidentifiable outside this specific setup.

### 3b. Reassessed against the retained, corrected 3-moment set -- DECIDED: `distance_gradient_slope` removed from fitted targets

Aakash chose option 1 from section 2: `distance_gradient_slope` is removed from the fitted
target set and retained only as a qualitative external benchmark (explicitly *not* described as
independent quantitative validation, given the confirmed population/labour-force mismatch).
Reassessing identification against the retained three moments (`discouraged_share`,
`transport_budget_share`, `long_term_share`) -- same fitted point, same settled window, same
`CALIBRATION_SEEDS`/`WEIGHT_SEEDS`, computed by slicing `MOMENT_KEYS` down to the retained three
before rebuilding `data_cov`/`sim_cov`/the weight matrix (a diagnostic-only slice; `calibrate.py`
itself is untouched):

| | 4-moment set (with `distance_gradient_slope`) | 3-moment set (retained only) |
| --- | --- | --- |
| rescaled condition number | 122,356 | 835,641 |
| `firm_radius` Jacobian entries (3 moments) | -- | 0.0008, 0.0003, 0.0053 |
| smallest eigenvector, `firm_radius` component | 0.999 | 0.999 |

**`firm_radius` is not merely weakly identified by the retained set -- it is identified by
essentially none of it.** `distance_gradient_slope` was the *only* moment carrying any signal
about `firm_radius` in the original 4-moment sensitivity table (section 3 of the settled-regime
assessment); with it removed, `firm_radius`'s Jacobian entries against all three retained
moments are three orders of magnitude smaller than `search_cost_per_trip`'s or `firm_kappa`'s,
and the condition number worsens by roughly 7x. This is the expected, mechanical consequence of
removing the one moment that gave this parameter any traction, not a new finding about the
retained moments themselves.

**Recommendation: fix `firm_radius` at 2.5, report a sensitivity range, do not carry the old
fitted value forward.** Three reasons, not one: (a) the old fitted value (1.6411) was chosen to
fit `distance_gradient_slope`, a moment no longer in the target set -- carrying it forward would
silently keep that moment's influence after removing it from the objective it influenced; (b)
2.5 is `configs/baseline.yaml`'s own pre-calibration default, not a value invented for this
recommendation; (c) 2.5 sits at the midpoint of the range where `firm_radius` has *any* behavioural
effect at all -- below roughly 1.0 the catchment starts binding meaningfully, above roughly 4.0
(`cbd_radius`'s diameter) every firm is reachable from every search position and the parameter
saturates (`DECISIONS.md`, "firm_radius=4.1 and 6.0 produced identical histories"). Sensitivity
range: report the retained three moments and, once it exists, the policy comparison's headline
outcome across `firm_radius` in {1.0, 1.75, 2.5, 3.25, 4.0} -- the original 4-moment sensitivity
table already showed the retained moments barely move across this range (`discouraged_share`
0.3618-0.3621), so this sweep is expected to demonstrate robustness rather than to select a
value, and should be reported as such. One check not yet done: whether `firm_radius` affects
`employment_share` through the vacancy-constrained mechanism P1.1 found (vacancies, not searcher
count, set the hire rate) -- relevant to the future policy engine, not resolved here.

---

## 4. Redesigned convergence-validation method -- second correction, development-verified

The first pilot's rule failed for two reasons: a cross-sectional moment's own noise blocked the
fast candidate, and a small absolute step didn't distinguish true convergence from a
not-yet-accelerated climb. Astra independently applied a first proposed fix (three consecutive
passes, raw step required non-increasing) to the *same, already-collected* checkpoint data and
found it still fails: it accepts `firm_kappa`=1.4 and 2.0 at the earliest possible checkpoint
(step 2,250) and never accepts the fitted candidate through step 9,000. **Verified independently
here, against `results/review_v2/settled_regime/adaptive_pilot/trajectories.csv` -- no new
simulation needed to catch this.**

**Why the "non-increasing absolute step" idea doesn't work.** A non-overlapping 450-step
detection window's raw checkpoint-to-checkpoint difference has no reason to shrink monotonically
just because the underlying process has converged: successive differences of an already-flat,
noisy series are themselves noisy, not decreasing. Conversely, a genuinely still-rising S-curve
can pass through a locally decelerating stretch (as `firm_kappa`=1.4's `discouraged_share`
increments do, briefly, around step 2,250) long before it is anywhere near its true limit. Raw
step size cannot tell these apart in either direction.

### The corrected rule: a local trend test against known noise, not a raw-step test

At each checkpoint, for each of the three stopping-decision moments (`discouraged_share`,
`transport_budget_share`, `long_term_share` -- `distance_gradient_slope` stays excluded from the
*decision*, see below), fit an OLS slope of the moment's checkpoint-averaged value against step
index over the last `TREND_WINDOW`=4 checkpoints, and test the slope against zero using that
moment's own **externally known** simulation standard error (section 1's corrected
`precision_decomposition.csv`), not the regression's own residual variance (only 4 points --
far too few degrees of freedom to estimate its own noise). Convergence is accepted once this
joint (all three moments) flatness test passes for 3 consecutive checkpoints in a row.

**Verified against the existing development data before any new simulation was run** (`scripts/
adaptive_burn_in_pilot.py`'s corrected `apply_stopping_rule`, applied to
`adaptive_pilot/trajectories.csv`'s checkpoint averages):

| candidate | accepted at (corrected rule) | expected |
| --- | --- | --- |
| fitted | **step 4,500** | fast, early -- matches |
| `firm_kappa`=0.9 | unresolved through 9,000 | matches (far from settled, per the horizon campaigns) |
| `firm_kappa`=1.4 | unresolved through 9,000 | matches |
| `firm_kappa`=2.0 | unresolved through 9,000 | matches |

This is the corrected rule, checked against the same data the flawed one failed on, before any
held-out collection -- exactly the sequencing Aakash asked for.

### Method (final, for the next collection pass)

- **Stopping-decision moments**: `discouraged_share`, `transport_budget_share`, `long_term_share`.
  `distance_gradient_slope` is excluded from the decision (structurally unsuited -- it is read
  once per checkpoint, never window-averaged, so its own noise at 15 seeds is the same order as
  the flatness threshold), **but is still computed, recorded and validated at every checkpoint
  and in the final report.**
- **Validation quantities, always recorded regardless of the stopping decision**: the four
  calibration moments, plus the capital distribution's whole-population mean and median *and*
  its non-employed-only mean and median (`scripts/diagnose_window_stability.py`'s
  `_capital_quantile_row`, reused) -- both populations, not only the non-employed one, per
  Aakash's instruction that excluding a quantity from the stopping rule must not exempt it from
  validation.
- **Detection window**: 450 steps. **Checkpoints**: 900, 1350, 1800, 2250, 3150, 4500, 6300, 9000.
  **Computational limit**: 9,000 steps. **Measurement block**: a fresh 150 steps immediately
  after acceptance, never the window used to detect convergence -- all unchanged from the first
  pilot.
- **Convergence rule**: the trend test above -- 3 consecutive checkpoints of a joint (all three
  stopping moments), OLS-slope-against-known-noise flatness test.
- **Unresolved-candidate treatment**: a candidate that never satisfies the rule by step 9,000 is
  UNRESOLVED. Its last available window is still recorded and validated against the long-run
  reference, but must not be scored as a converged, poor-fitting point.

### Quantitative acceptance criteria for this development pass

1. The fitted candidate must be ACCEPTED (not unresolved) by step 9,000. **Met**: accepted at
   step 4,500.
2. Every `firm_kappa` candidate tested (0.9, 1.4, 2.0) must NOT be accepted at any checkpoint
   whose reported value differs from the long-run reference by more than the reference's own
   combined SE -- i.e. no repeat of the first rule's failure mode (accepting early with a value
   5-6x off). **Met by construction**: none of the three is accepted at all through step 9,000,
   so this criterion cannot be violated; had one accepted early, its reported-vs-reference bias
   would additionally need checking (not required here, since none accepted).
3. `distance_gradient_slope` and all four capital-distribution quantities (whole-population and
   non-employed, mean and median) must be reported with their bias against the reference for
   every candidate, resolved or not. **Met**: collection pass run
   (`results/review_v2/settled_regime/adaptive_pilot_v2/`, 1,395s wall clock). For the fitted
   candidate (the only resolved one, so the only one with a `reported` value to bias-check):
   `discouraged_share` bias -0.0044, `transport_budget_share` +0.00003, `long_term_share`
   -0.0043 -- all well under one combined SE. `distance_gradient_slope` bias +0.059 against a
   combined SE of about 1.42 -- trivially within noise, consistent with section 1's finding that
   this moment's simulation precision is fine regardless of the window. Capital diagnostics:
   non-employed mean bias -0.00004, non-employed median -0.00037, whole-population mean -0.00020,
   whole-population median -0.00066 -- all small relative to their own level (~0.015). For the
   three unresolved `firm_kappa` candidates, every reference value (including the four capital
   quantities) is recorded even though there is no reported value to compare it against --
   satisfying "validated even when excluded from the decision," not merely asserted.
4. No candidate's stopping decision may depend on `distance_gradient_slope` or the capital
   diagnostics. **Met by construction**: the rule only reads `STOPPING_MOMENTS`.

**All four criteria pass.** The corrected rule and the capital-diagnostic collection are both
verified on the development set. Per Aakash's sequencing instruction, held-out validation may
now proceed -- see section 5's proposed design, not yet launched pending confirmation given its
added cost.

### Additional collection cost (Aakash's instruction to account for it explicitly)

`results/review_v2/settled_regime/adaptive_pilot/trajectories.csv` has no capital measurements
-- `scripts/adaptive_burn_in_pilot.py`'s first version tracked only the four calibration moments.
Adding capital-distribution tracking requires re-simulating every (candidate, seed) pair from
scratch: this script steps `CityModel` directly rather than going through the cached
`run_moments_many` pipeline, so nothing here is cache-eligible, and the corrected rule needs the
full checkpoint series regenerated regardless of the rule change alone. Cost: the same order as
the first pilot's measured 1,488 seconds (4 candidates x 15 seeds x 15,000-step trajectories at
6-way parallelism) plus the added per-checkpoint capital-quantile computation, which is cheap
(rank statistics over 500 agents) relative to the simulation itself -- expected total in the same
1,500-1,600 second range, not a materially larger cost. This collection has been run as part of
this specification (see the addendum at the foot of this document for the completed numbers).

---

## 5. Validation discipline: development vs held-out, and checking the reference itself

**Development set**: the 60 trajectories already collected in the first pilot
(`results/review_v2/settled_regime/adaptive_pilot/trajectories.csv`; `CALIBRATION_SEEDS`, 4
candidates: fitted, `firm_kappa` in {0.9, 1.4, 2.0}). Used only to check the redesigned rule's
mechanics against known behaviour -- not as the final validation, since a rule tuned and checked
against the same data it is validated on is not an independent test.

**Held-out set, not yet collected**: a fresh, disjoint seed block (not `CALIBRATION_SEEDS`,
`VALIDATION_SEEDS`, `WEIGHT_SEEDS`, or this session's own ad hoc 3001-3050 diagnostic block --
a new block reserved specifically for this validation and not reused elsewhere), crossed with
parameter combinations beyond the single-`firm_kappa`-axis sweep the first pilot used: at least
one joint perturbation (e.g. `firm_kappa` and `search_cost_per_trip` both away from their fitted
values together, not one at a time) and, since `initial_search_capital` is now a fixed
initialisation setting rather than an estimated parameter, a check of whether the *initialisation
scheme* (all-searching vs the mixed-state transplant from P1.2) changes how the rule behaves --
plausible, since a mixed-state start begins closer to its long-run distribution and might accept
sooner than an all-searching one at the same parameters.

**Checking the reference itself, not assuming step 15,000 is settled.** The first pilot's
"ground truth" was a single window (13,501-15,000) with no check that the process had actually
stopped moving by then -- exactly the mistake the whole review has been catching elsewhere (P1.2,
the settled-window search). Before trusting it as ground truth, the held-out pass must compare
that window against a materially later one (e.g. 28,501-30,000) for at least the slowest
candidate (`firm_kappa`=2.0, whose own decay-rate extrapolation already suggested a horizon well
past 9,000) and confirm the two references agree within simulation noise. If they do not, the
reference horizon extends further before any bias figure against it is trusted.

**Status: development phase is done and all four quantitative criteria pass (section 4). Held-out
collection is proposed below, not yet launched.**

**Proposed held-out design, costed:**

- **Seeds**: a fresh block, 5001-5015 (15 seeds, matching `CALIBRATION_SEEDS`' count) -- disjoint
  from `CALIBRATION_SEEDS` (1-15), `VALIDATION_SEEDS` (1001-1050), `WEIGHT_SEEDS` (2001-2050) and
  this session's own ad hoc diagnostic block (3001-3050).
- **Candidates**: the fitted point (repeat, on fresh seeds, as an independence check); a joint
  perturbation (`firm_kappa`=0.9 *and* `search_cost_per_trip` at its own lower bound
  simultaneously -- not one parameter at a time, per Aakash's instruction); one initialisation-
  scheme check (the fitted point under P1.2's mixed-state transplant instead of all-searching,
  to test whether a start closer to the long-run distribution changes how fast the rule accepts).
- **Reference verification**: for the slowest candidate only (the joint `firm_kappa`/
  `search_cost_per_trip` perturbation), extend the trajectory to 30,000 steps and compare the
  window 13,501-15,000 against 28,501-30,000. If they agree within simulation noise, the
  15,000-step reference is confirmed adequate for the other candidates too; if not, every
  candidate's reference window extends to match.
- **Computational cap**: unchanged, 9,000 steps for the stopping decision itself; the reference
  verification's 30,000-step extension applies only to building trust in the reference, not to
  the cap a real search would use.
- **Cost estimate**: 5 candidates x 15 seeds x 15,000 steps, plus one candidate extended to
  30,000 steps for the reference check -- roughly 1.3x the development pass's measured 1,395
  seconds for the base collection, plus the 30,000-step extension (roughly 2x one candidate's
  share, since cost scales close to linearly with horizon) -- an estimated 2,000-2,400 seconds
  (33-40 minutes) at 6-way parallelism. Not launched in this specification; needs confirmation
  given the added time on top of everything already run today.

---

## 6. Handling unresolved candidates during an actual future calibration search

Aakash asked this be addressed explicitly: how unresolved candidates are handled during
calibration, without silently excluding parts of the parameter space. Not implemented (no
`calibrate.py` change), specified for when integration is eventually approved.

**The wrong approach, ruled out:** assigning an unresolved candidate a large but finite penalty
loss. This is exactly what Aakash's original instruction forbids -- "treat candidates that reach
the limit as convergence unresolved, not automatically as poor-fitting models." A penalty makes
Nelder-Mead actively steer away from the region, and a reader of the eventual thesis would never
learn that the search avoided that region *because it was slow to measure*, not because it fits
badly. If the true optimum sits in a slow-to-converge region (plausible for large parts of
`firm_kappa`'s box, per the settled-regime assessment), a penalty-based rule would silently
exclude exactly the region most in need of disclosure.

**Recommended approach, modelled on an existing precedent in this codebase.**
`calibrate.py`'s `simulate_moments` already propagates `nan` rather than a false zero when
`distance_gradient_slope` is undefined at a degenerate parameter point -- "a nan moment means
this parameter point can't be scored at all, not that it scores zero." Unresolved candidates
should get the same treatment: the loss at an unresolved point is `nan`, not a number, distinct
from both a good fit and a bad one.

- **Latin hypercube stage**: an LHS point that comes back unresolved is recorded in full (its
  parameter vector, and its last available checkpoint reading) but excluded from the pool of
  points eligible to seed a Nelder-Mead restart, since there is no trustworthy loss to rank it
  by. The *fraction* of the 200 LHS points that were unresolved, and their approximate location
  in parameter space (e.g. what range of `firm_kappa` they cluster in), is recorded and reported
  -- not discarded silently.
- **Nelder-Mead stage**: a candidate landing on or near a previously unresolved region during
  the search itself needs a defined move, not a crash. The standard, defensible choice is to
  treat a `nan` loss the way an infeasible point is treated in constrained Nelder-Mead variants:
  the simplex reflects or shrinks away from it without ever comparing it on equal footing to a
  resolved point's real loss. This needs implementing and testing before any real search runs
  it -- not done here.
- **Reporting requirement, non-negotiable per Aakash's instruction:** whatever the final
  mechanism, the calibration's own output must record, and the eventual thesis text must state:
  total candidates evaluated, how many were unresolved, and an explicit sentence to the effect
  that "candidates in region X were unresolved under the Y-step computational cap and could not
  be scored; the true optimum could lie there, and this is a stated limitation of the search, not
  a resolved non-issue." This is a disclosure requirement, not an optional caveat.
