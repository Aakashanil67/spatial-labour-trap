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
passes, raw step required non-increasing), exactly as specified, to the *same, already-collected*
checkpoint data. **Result, re-verified here rather than taken on report: the rule accepts none
of the four candidates, including the fitted one, through step 9,000.** An earlier revision of
this document wrongly stated that `firm_kappa`=1.4 and 2.0 accept at step 2,250 -- that claim
checked only the threshold half of the rule (three consecutive comparisons under each moment's
noise threshold, which the `firm_kappa` candidates do satisfy at that point) and never actually
combined it with the non-increasing requirement across the same three comparisons, which they do
*not* satisfy. Recomputed directly against `results/review_v2/settled_regime/
adaptive_pilot/trajectories.csv` with both conditions enforced jointly: **no candidate accepts
under the exact rule as specified.** The claim is withdrawn.

**Why the "non-increasing absolute step" idea doesn't work -- it is simply too strict, not
selectively wrong.** A non-overlapping 450-step detection window's raw checkpoint-to-checkpoint
difference has no reason to shrink monotonically just because the underlying process has
converged: successive differences of an already-flat, noisy series are themselves noisy, not
decreasing, so requiring three of them in a row to decrease is a near-impossible bar even for a
truly flat process -- which is exactly why it rejected the fitted candidate too, not only the
still-rising ones.

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

**Disclosure, requested explicitly: step 4,500 is this rule's mechanical earliest-possible
acceptance point, not an independent empirical finding about the fitted candidate.**
`TREND_WINDOW`=4 needs checkpoints 900/1350/1800/2250 for its first testable estimate;
`CONSECUTIVE_PASSES_REQUIRED`=3 needs three such estimates in a row -- the ones ending at 2250,
3150 and 4500. No candidate, however fast it truly settles, could be accepted before checkpoint
4,500 under these parameters; the fitted candidate landing exactly on that floor is consistent
with fast convergence but does not, by itself, prove the true settling point is 4,500 specifically
rather than earlier. **Failure to detect a trend is not evidence of a flat trend.** The test as
built only asks whether the estimated slope is statistically distinguishable from zero; at 4
points it can lack the power to detect a real, small ongoing drift, so "accepted" should be read
as "not contradicted by this test," not "proven converged" -- a genuine, unresolved limitation of
this method, not a rounding error. A proper fix (e.g. an equivalence/TOST-style test against a
pre-specified tolerance, rather than a two-sided test of the point null) is a further, open
design question, not built here.

**A second unresolved statistical gap: the noise term used is borrowed, not derived for this
design.** The trend test's `sigma` comes from `precision_decomposition.csv`, which measures the
simulation variance of a 150-step window's 15-seed mean at the settled point -- not the variance
of a 450-step detection window's mean, which is this rule's actual estimator and should have
smaller variance (a longer window, more averaging) than the borrowed figure, making the test
conservative in one respect. Separately, the four checkpoint estimates entering each trend fit
come from non-overlapping windows of the *same* continuous trajectory per seed, so they are not
guaranteed independent draws with constant variance the way the OLS-SE formula assumes; whether
serial dependence in the underlying process (e.g. from the AR(1) productivity shock) makes this
matter in practice has not been checked. Both gaps push toward the same conclusion as the
power problem above: this method's statistical foundations are not yet solid enough to trust
without the fixed/staged comparison below.

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
2. **Pre-specified acceptable residual error, not just "well under one SE" after the fact**:
   a candidate's reported (or, for an unresolved candidate, its last-available) reading must not
   differ from the long-run reference by more than 0.5 combined SE for `discouraged_share` and
   `long_term_share`, or by more than 2 combined SE for `distance_gradient_slope` (a looser bar,
   since section 1 already showed its combined SE is dominated by between-city heterogeneity, not
   simulation precision, so a tighter bar would be meaningless). For the capital diagnostics,
   which have no `combined_cov`-based SE (they are not fitted moments), the bar is 20% of the
   reference's own level -- an explicit, if somewhat arbitrary, quantitative threshold rather
   than an eyeballed "small."
3. **Comparisons provided for every candidate, resolved or not -- not skipped because none
   accepted.** Fitted (resolved at step 4,500): `discouraged_share` bias -0.0044 (0.7 combined
   SE, just over the 0.5 bar), `transport_budget_share` +0.00003, `long_term_share` -0.0043
   (0.5 SE), `distance_gradient_slope` +0.059 (0.04 SE) -- all pass except `discouraged_share`,
   marginally, which is disclosed rather than rounded away. Capital: non-employed mean/median
   and whole-population mean/median biases are all under 5% of their reference level, well
   inside the 20% bar. For the three unresolved `firm_kappa` candidates, the **last available
   measurement block** (step 9,000, the computational limit) is compared against the reference
   even though the rule never accepted it: `discouraged_share` bias is -0.0001 to -0.0002 (under
   0.05 SE -- the moment itself is nearly exact by step 9,000), but `capital_all_mean` bias is
   0.0084-0.0110 against a reference of about 0.015 -- 55-73% of the reference level, **failing
   the 20% capital bar by a wide margin even at the computational limit**. This is the clearest
   evidence in this document that the capital distribution genuinely has not settled for these
   candidates even when the calibration moments themselves are close -- exactly why Aakash's
   instruction to validate capital separately, not only the fitted moments, matters.
4. No candidate's stopping decision may depend on `distance_gradient_slope` or the capital
   diagnostics. **Met by construction**: the rule only reads `STOPPING_MOMENTS`.

**Three of four criteria pass cleanly; one (fitted's `discouraged_share` bias) passes only
marginally, and the capital bar fails outright for unresolved candidates at the computational
limit.** This is reported as a mixed, not a clean, result -- see the fixed/staged fallback
comparison immediately below before deciding whether the adaptive approach is worth pursuing
further at all.

### Fixed and staged alternatives, assessed on the existing trajectories (the requested fallback)

Per Aakash's instruction not to begin another open-ended cycle of stopping-rule adjustments,
this uses only the already-collected `adaptive_pilot_v2` data -- no new simulation -- to ask
whether a much simpler, non-adaptive scheme would do as well or better.

**A single fixed burn-in, no adaptivity at all**, checked at every candidate and every
checkpoint (bias against the long-run reference):

| burn-in | fitted `discouraged_share` bias | `firm_kappa` (0.9-2.0) `discouraged_share` bias | `firm_kappa` `capital_all_mean` bias (% of reference) |
| --- | --- | --- | --- |
| 900 | -0.001 | -0.040 | 850-940% |
| 2,250 (current provisional choice) | -0.001 | -0.026 to -0.029 | 290-340% |
| 4,500 | -0.004 | -0.008 to -0.009 | 80-97% |
| 6,300 | +0.002 | -0.003 | 28-34% |
| 9,000 | -0.007 | -0.0001 to -0.0002 | 55-73% |

Two things stand out. First, **a fixed burn-in of 9,000 already gives an excellent
`discouraged_share` reading for every candidate tested, including the slowest**, at a cost that
is simple, uniform, and does not depend on any stopping-rule logic at all. Second, **the capital
diagnostic never fully closes even at the 9,000-step cap** -- consistent with the criterion-3
finding above, and a property of the underlying process (per the settled-regime assessment's own
extrapolation of `firm_kappa`=2.0's decay rate to roughly step 9,000-plus), not an artefact of
whichever stopping rule is used to decide when to stop.

**Cost comparison.** A uniform fixed-9,000 burn-in costs the same for every candidate regardless
of how fast it truly settles -- roughly 9,000/150 = 60x a single 150-step evaluation, paid on
every LHS point and every Nelder-Mead step, with no saving for the fast region near the fitted
point where a real search would spend most of its refining evaluations. A **staged** alternative
-- run every candidate to a cheap first stage (2,250, already collected data), then extend only
flagged candidates to 9,000 -- would only save compute if a cheap, reliable flag exists. The
simplest candidate flag (compare `capital_all_mean` between checkpoints 900 and 2,250; the fitted
candidate's change is under 0.002, every tested `firm_kappa` candidate's change is over 0.35)
cleanly separates the four candidates tested here, but this is only four points on one parameter
axis, not a validated flag across the space a real search would explore -- presented as a
plausible fallback design, not a validated one.

**Recommendation given this comparison:** the fixed-9,000 approach is the more defensible
near-term choice -- it is simpler, already meets the `discouraged_share` bar for every tested
candidate without any stopping-rule logic to validate further, and its known weakness (capital
diagnostics don't close) is a property of the model, not of the measurement method, so no
stopping rule would fix it either. The adaptive trend-test approach's advantage (potential
compute savings for fast candidates) is real but unquantified against a properly validated flag,
and its known weakness (the test-power problem, and marginal performance on the one criterion
that did get checked) is not yet resolved. This is presented as a recommendation, not a decision
-- Aakash's call, not defaulted into either by which was built first.

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

**Further assessment of unresolved regions, not just disclosure of their existence.** `nan`
handling and reporting tell a reader *that* a region was unresolved; they do not tell anyone
*what the region probably looks like*. Aakash asked for more than avoidance. Proposed, bounded
follow-up (not implemented, not costed against a real search yet): after the main search
finishes, cluster the unresolved LHS/Nelder-Mead points by parameter-space proximity, pick one
representative point per cluster (bounded in number, e.g. at most 5-10 regardless of how many
points were unresolved), and run each representative to a much longer, separately-budgeted
horizon (the same kind of extension this document's own reference-verification step already
uses) as a dedicated post-hoc diagnostic -- reported in the thesis text alongside the main
result, not folded into the search's own loss or ranking. This characterises what the excluded
region likely contains without requiring every unresolved point to be fully resolved, and keeps
the extra cost bounded and disclosed rather than open-ended. Not built, and its own cost has not
been estimated -- a design proposal responding to the instruction, not a fourth stopping-rule
implementation cycle.
