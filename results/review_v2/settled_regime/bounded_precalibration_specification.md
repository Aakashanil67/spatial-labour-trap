# Bounded pre-calibration specification

Presented before any further pilot implementation, per Aakash's instruction of 2026-09-13. This
is a design document, not new code: sections 1-3 correct and re-verify prior analysis (already
rerun, with real corrected numbers below); section 4 specifies a redesigned convergence-validation
method that has **not been built or run**; section 5 sets the validation discipline that method
must follow. Nothing here is integrated into `calibrate.py`, and `firm_kappa`'s calibration bounds
stay at (0.2, 2.0) -- kept, not narrowed for computational convenience.

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

---

## 4. Redesigned convergence-validation method -- specification only, not built

The first pilot's rule failed for two reasons (recorded in `DECISIONS_PENDING.md`): a
cross-sectional moment's own noise blocked the fast candidate, and a small absolute step didn't
distinguish true convergence from a not-yet-accelerated climb. This section fixes both, and adds
what Aakash's review asked for: the capital distribution enters validation, and excluding a
moment from the *stopping decision* does not exempt it from being *checked*.

### Method

- **Stopping-decision moments**: `discouraged_share`, `transport_budget_share`, `long_term_share`
  only. `distance_gradient_slope` is excluded from the stopping decision (its per-checkpoint
  noise is structurally unsuited to a consecutive-small-step test, per the first pilot's
  diagnosis), **but is still computed, recorded and validated at every checkpoint and in the
  final report** -- never silently dropped.
- **Validation quantities, all candidates, all checkpoints, always recorded regardless of the
  stopping decision**: the four calibration moments, plus the capital distribution's mean and
  median among non-employed agents (the two quantities the window-stability work showed converge
  at very different speeds) -- both reported against the long-run reference (section 5), whether
  or not they drove the stopping decision.
- **Detection window**: unchanged, 450 steps.
- **Checkpoints**: unchanged, 900, 1350, 1800, 2250, 3150, 4500, 6300, 9000.
- **Convergence rule, corrected**: for each stopping-decision moment, require the
  checkpoint-to-checkpoint change to be no larger than that moment's own simulation SE of the
  mean (section 1's corrected `precision_decomposition.csv`) for **three consecutive comparisons**
  (not two), **and** the sequence of absolute changes itself must be non-increasing across those
  three comparisons (a genuine flattening, not a locally quiet stretch inside a still-rising
  trajectory). Accepted at the last of the three checkpoints.
- **Computational limit**: unchanged, 9,000 steps.
- **Measurement block**: unchanged, a fresh 150 steps immediately after acceptance, never the
  window used to detect convergence.
- **Unresolved-candidate treatment**: unchanged in spirit, restated precisely -- a candidate that
  never satisfies the rule by step 9,000 is tagged UNRESOLVED. Its last available window is still
  recorded and still validated against the long-run reference (so the report can show *how far
  off* an unresolved candidate's last reading was, which is itself informative), but it must not
  be scored as a converged, poor-fitting point in any downstream use.

### Acceptance criteria for this method itself (not yet met -- to be checked in the next pilot pass)

1. On the *development* trajectories (the existing 60 runs, `CALIBRATION_SEEDS`, already
   collected -- see section 5), the fast (fitted) candidate must be accepted, and accepted early
   (by checkpoint 2250 at the latest).
2. Every slow `firm_kappa` candidate (0.9, 1.4) must either be accepted at a checkpoint whose
   reported value is within one combined-SE of the long-run reference (section 5's re-verified
   reference, not assumed), or remain unresolved through step 9,000 -- not accepted early with a
   materially wrong reported value, which is exactly the first rule's failure mode.
3. `firm_kappa`=2.0 is expected to remain unresolved; this is an acceptable outcome, not a
   pilot failure, and must be reported as unresolved rather than silently coerced into a value.
4. `distance_gradient_slope` and the two capital-distribution quantities must be reported with
   their bias against the reference for every candidate, resolved or not.

### Expected cost

Development (reusing existing trajectories, section 5): zero additional simulation cost --
the redesigned rule is applied to data already collected. The *held-out* validation pass (fresh
seeds, additional parameter combinations, per section 5) is new compute: at minimum the same
scale as the first pilot (4-6 candidates x 15 seeds x 15,000-step trajectories, roughly 1,500-2,500
seconds wall clock at 6-way parallelism, based on the first pilot's measured 1,488s for 4
candidates) -- more if the reference-verification check in section 5 requires trajectories longer
than 15,000 steps for the slowest candidates.

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

**Not yet done**: none of section 5's held-out collection has been run. This specification
presents the design; the next step, on approval, is to build the redesigned rule (section 4),
apply it to the existing development trajectories, and only then collect and check the held-out
set above -- in that order, not skipping to a fresh pilot run before the rule has been checked
against data already in hand.
