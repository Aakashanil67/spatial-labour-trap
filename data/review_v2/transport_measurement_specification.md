# Transport measurement specification, consolidated 2026-09-14

**Status: a consolidated review output, not an adopted calibration target.**
`transport_budget_share` in `configs/baseline.yaml`/`data/moments.csv` is unchanged.
No held-out convergence run or full recalibration has been performed. This file
pulls together `transport_definition.md`, `transport_candidate_estimates.md`, and
this round's design-based uncertainty and population work into one reference; it
does not introduce new numbers beyond what those files (and the scripts behind them)
already establish.

## What is SETTLED for this specification (carried forward, not reopened this round)

| dimension | setting | why |
| --- | --- | --- |
| Excursion definition | **round-trip** | Matches the model's own existing interpretation of its flat transport-cost anchor -- Banerjee and Sequeira's R12.50 figure in `configs/baseline.yaml` is explicitly a return fare (`src/calibrate.py`). One-direction retained as a reporting comparison only. |
| Weighting | **NHTS person `Weight`** | Person weighting is materially non-neutral (unweighted vs. weighted means differ by ~6%); unweighted is a diagnostic only. |

## What is PROPOSED (new this round, not yet decided)

| dimension | proposal | evidence |
| --- | --- | --- |
| Population (both numerator and wage denominator) | **ages 15-64** | Matches the `discouraged_share`/`long_term_share` convention elsewhere in this project. 19 of 4,655 travellers and 364 of 20,867 wage observations fall outside this range (verified live). The broader (unrestricted) age range is reported as a sensitivity, not silently dropped. |

## What remains explicitly OPEN (preserved, not resolved)

- **Driver `Q433bPay` codes 5/6, Scenario A vs. B** -- both are reported side by side
  everywhere in this specification; neither is chosen. See `transport_definition.md`
  for the underlying instrument-vs-`.dta` discrepancy.
- **The exact frequency assumption** (search days/week) -- shown to move the point
  estimate by only ~5.5% across a bounded, realistic range (1-7 days/week), so it is
  not a first-order concern, but no single value is adopted as final.
- The excursion-definition and weighting PROPOSALS above are carried forward from the
  prior round as the working default for this specification, not re-litigated here,
  but they remain proposals pending a decision, not settled facts.

## Observation and averaging specification, added 2026-09-14 (Astra review, finding 2)

**Correction first.** Earlier text in this project (`transport_definition.md`,
`DECISIONS_PENDING.md` Question 4, `REVIEW_HANDOFF.md` section 6.5) described
`Q47Travlooking` as a "reference day"/"single reported travel day" screening question
and used that description to justify a person-window mean as automatically matching
the survey's design. **`Q47Travlooking` (question 4.7) actually asks about job-search
or business-starting travel over the previous Monday-to-Sunday WEEK**, per Astra's
citation of the official NHTS 2020 CAPI questionnaire, PDF page 33. This pass
attempted to re-fetch that PDF directly to verify independently and was blocked by the
host's bot-protection (an Incapsula challenge page was returned instead of the PDF) --
the correction below is made on Astra's specific page citation, not independently
re-confirmed against the primary document this pass.

**Stated explicitly, without overclaiming what the design identifies:**

1. **Conditioning event**: `Q47Travlooking==Yes` -- the respondent made at least one
   job-search or business-starting trip in the reference WEEK (not day).
2. **Respondent contribution**: for a `Yes` respondent, the routed questions
   (`Q416bWalk` through the `Q429b`-`Q432b` listed-mode block, or `Q433bPay`/
   `Q434bCost` for drivers) describe ONE recorded journey -- for the listed-mode/
   hitchhike group, up to four legs of one journey. There is no field asking "how many
   such trips did you make this week" and no repeated per-trip cost grid. So each
   in-scope respondent contributes exactly one journey-cost observation, regardless of
   how many job-search trips they may have made in the reference week.
3. **Treatment of multiple journeys within the week**: not observed. The survey
   identifies neither the true weekly trip count nor whether the recorded journey is
   representative of a typical trip that week. Any statement about "the" cost of a
   week's job-search travel, or a conversion to a daily/monthly figure, requires an
   explicit, separately stated frequency assumption -- already tracked as the open
   "search days/week" sensitivity above, now understood as a genuine identification
   gap rather than a detail to be reconciled against a (mistaken) single-day design.
4. **Zero-cost travellers**: walkers, cyclists, and anyone whose recorded journey
   resolves to "do not pay" contribute a genuine zero to the person-level cost
   observation described in point 2 -- they are NOT the same as point 5.
5. **People making no trip**: respondents with `Q47Travlooking==No` are excluded from
   this population entirely; they contribute no observation (neither a zero nor a
   missing value) to `transport_budget_share`'s numerator, matching the target
   dictionary's existing conditioning statement.
6. **Averaging across simulation time**: the model computes `transport_budget_share()`
   over a multi-month simulation window, summing spend and trips across all months and
   all agents before dividing (a TRIP-mean across the whole window; see below). The
   survey instead provides one cross-sectional week per respondent, with no repeated
   observation of the same person over time. The model's within-window trip-mean and
   the survey's between-person mean of one-journey-per-person are therefore not
   observationally identical constructs even before the trip-mean/person-mean
   estimand question is resolved -- the survey has no time dimension to average over at
   all, only a population dimension.

**What IS identified from this design, stated positively**: a person-weighted mean (or
median) of "the cost of the one job-search journey NHTS happened to record for this
person," over the population that travelled while searching in the reference week.
This is exactly the person-mean the candidate reconstruction computes. What is NOT
identified: a trip-count-weighted (trip-mean) estimator, a true weekly total per
person, or a estimate of how representative the recorded journey is of that person's
other job-search trips (if any) in the same week.

**Worked fixture (the plan's own averaging fixture, applied to this exact design).**
Two survey respondents, each reporting one journey: person A pays R10, person B pays
R30 (both `Q47Travlooking==Yes`, one journey recorded each, as design point 2
requires -- NHTS provides no basis for saying person A made three trips and person B
made one, since no trip-count field exists). The person-mean is (10+30)/2 = R20. A
model agent who takes 3 trips at some cost and another who takes 1 trip at another
cost would, under the model's current trip-mean definition, NOT reproduce R20 from
underlying per-trip costs of R10/R30 unless trip counts happen to be equal -- this is
the same fixture already in `DECISIONS_PENDING.md` Question 4, restated here to show
it applies regardless of the (corrected) weekly vs. daily reference-period question.

**The weekly-to-monthly model approximation -- CORRECTED 2026-09-15 (Astra
`REVIEW_FOLLOWUP.md`): the frequency-sensitivity grid does NOT already solve this; the
2026-09-14 text above conflated two different operations and is withdrawn.** The
"search days/week" grid (`transport_candidate_frequency_sensitivity_15_64.csv`) is a
**fare-conversion** operation: it allocates a weekly/monthly PAYMENT figure over an
assumed number of journeys to get a cost per journey. That is a different problem from
**observation selection**: deciding which of the model's monthly-traveller agents
should be treated as playing the role of "a person NHTS's weekly screen would have
caught and recorded." Changing the fare divisor does not specify which agents qualify
as weekly travellers, and this problem exists even if every NHTS fare were already
reported per single trip with no conversion needed at all -- frequent and infrequent
travellers have different probabilities of appearing in a one-week screen despite both
travelling during the same model month, and nothing in the frequency grid addresses
that. See `observation_estimation_proposal.md` (added this pass) for the actual
observation-selection proposal: monthly-traveller participation is used as an explicit,
disclosed approximation to weekly-traveller participation, with a bounded sensitivity
between equal per-traveller weighting and trip-frequency-weighted participation,
rather than treating the fare-conversion grid as if it already resolved this.

**Not changed by this correction**: no code in `src/moments.py` is modified here (the
averaging-convention fix remains a G5-gated, undecided change per
`DECISIONS_PENDING.md` Question 4/`REVIEW_HANDOFF.md` 6.5); note that
`transport_budget_share()`'s own docstring in `src/moments.py` still asserts the
model "match[es] how the NHTS-derived empirical target conditions on a reported
travel day" -- that comment is also inaccurate per this correction and should be
fixed alongside the eventual averaging-convention implementation change, not as a
standalone edit to protected model source in this review-only pass.

## Point estimates: candidate transport-to-wage ratio

Sample definitions, stated explicitly:
- **Numerator**: round-trip transport cost for job-search travellers
  (`Q47Travlooking==Yes`, walk/cycle/drive/hitchhike/listed-mode), all administered
  legs, person-weighted (NHTS `Weight`), primary frequency assumption (5 search
  days/week). Journeys with any unresolved leg (ambiguous/DNK/internal-inconsistency/
  per-year) are excluded, not imputed -- coverage stated below.
- **Denominator**: weighted median monthly wage among NHTS respondents with a valid
  `Q410Salary` and a stated `Q411Payperiod`, converted to a daily rate at 21.7 working
  days/month (the same methodology already used for the canonical
  `transport_budget_share` moment, reproduced live here, not re-derived).

| population | driver scenario | point estimate | design-based 95% CI (percentile bootstrap) | bootstrap SE |
| --- | --- | --- | --- | --- |
| **15-64 (PROPOSED primary)** | A | **0.1997** | [0.1823, 0.2269] | 0.0117 |
| **15-64 (PROPOSED primary)** | B | **0.1972** | [0.1802, 0.2243] | 0.0115 |
| broader age (sensitivity) | A | 0.1991 | [0.1822, 0.2266] | 0.0117 |
| broader age (sensitivity) | B | 0.1965 | [0.1798, 0.2237] | 0.0116 |

Full detail in `transport_wage_ratio_design_uncertainty.csv`. Point estimates are
UNCHANGED from the prior round (the uncertainty correction below does not move
them). The population and driver-scenario choices both move the point estimate by
under 1.5%, and -- once the uncertainty calculation itself is corrected (see below)
-- also move the SE only marginally (0.0115-0.0117 across all four rows). **The
previous claim that the population choice caused a large, systematic difference in
uncertainty is withdrawn**; that appearance was an artefact of the withdrawn
jackknife's instability, not a real population effect -- see below.

**This candidate ratio (~0.197-0.200) remains roughly double the current canonical
`transport_budget_share` value of 0.1058**, for the reasons already documented in
`transport_candidate_estimates.md` (the canonical numerator sums raw cost columns
without payment-period conversion and treats ambiguous/DNK costs as R0). Not proposed
as a replacement value.

## Sampling uncertainty: design-based survey bootstrap, WITHDRAWN AND CORRECTED 2026-09-14

**The stratified delete-1 jackknife (JK1) used earlier this round is withdrawn, not
merely superseded.** The prior write-up treated a joint household-level jackknife as
the fix for independent resampling; it was a genuine improvement on that one point
(preserving the shared-household structure) but introduced a different, more serious
problem: the ratio's denominator is a **weighted median**, and ordinary delete-1
jackknife variance estimation is not generally valid for quantiles (Efron 1982; Shao
& Wu 1989). A median's influence function is not smooth -- removing one PSU either
leaves the median completely unchanged (if the PSU held none of the pivotal
observations) or moves it by a large, discrete jump (if it did). Astra's independent
check confirmed this concretely: the wage median changed in only **9 of 6,039**
replicates under the 15-64 population and **25 of 6,039** under the broader-age
population. The jackknife variance formula sums squared deviations across all
replicates; with the overwhelming majority contributing exactly zero and a handful
contributing large, noisy jumps, the resulting "SE" is not a trustworthy estimate of
sampling variance -- its size relative to the earlier independent bootstrap proves
nothing about its accuracy.

**Three specific claims from the withdrawn write-up are retracted:**
1. That the jackknife SE being larger than the earlier independent-bootstrap SE
   "confirmed" the jackknife was more accurate. A larger SE from an invalid method is
   not evidence of anything; validity depends on whether the method suits the
   statistic, not on the number it produces.
2. That shared-household dependence between the cost and wage samples "necessarily"
   inflates the ratio's variance. Dependence can inflate OR deflate variance depending
   on the sign of the within-household correlation between a person's transport cost
   and their household's wage -- that correlation was never estimated, so no
   direction should have been asserted.
3. That the SE difference between the 15-64 and broader-age populations was explained
   by "reduced between-PSU variability" from the age restriction. That explanation was
   built on numbers now known to be unreliable and is withdrawn along with them; the
   corrected bootstrap SEs below barely differ by population (0.0115-0.0117), so there
   was no real effect to explain in the first place.

**Replacement: a stratified WITH-REPLACEMENT PSU bootstrap ("survey bootstrap"),
valid for nonsmooth statistics including quantiles** (Rao & Wu 1988; Field & Welsh
2007). Each replicate independently draws n_h PSUs WITH replacement from the n_h PSUs
observed in stratum h; a PSU drawn m times has its records' weights multiplied by m
(0 if not drawn). Cost and wage weights are built from the SAME per-replicate PSU
draw across both samples, so a shared household's cost and wage records still move
together -- the one part of the withdrawn jackknife's design that was correct is
preserved here.

**Verified against a reference implementation.** The jackknife IS valid for a smooth
statistic -- the cost-side weighted mean -- so a cost-only jackknife (wage held fixed
at its full-sample value) gives a trustworthy figure: SE = 0.00905 (15-64) / 0.00902
(broader age), reproducing Astra's reported figures exactly. Running the new
bootstrap under the same wage-fixed isolation converges to a closely matching figure
(0.00880-0.00918 across the four rows, within ordinary Monte Carlo noise of the
trusted reference), confirming the bootstrap machinery is correctly calibrated before
trusting its full joint result. See `transport_wage_ratio_bootstrap_verification.csv`.

**Inspected replicate-median behaviour.** Across 2,000 bootstrap replicates, the
resampled wage median takes on 22-24 distinct values with a genuinely spread,
multi-modal distribution (e.g. under the 15-64/Scenario B design: 738 replicates at
R4,345, 419 at R4,000, 330 at R4,200, and 19 further distinct values) -- a
qualitatively different, far richer picture than the jackknife's near-degenerate
5-values-in-6,039-replicates pathology. See
`transport_wage_ratio_bootstrap_median_distribution.csv`.

**Inspected interval stability.** SE and the 95% percentile CI are stable across
replicate counts (1,000-4,000) and random seeds, moving only within ordinary Monte
Carlo noise:

| n_boot | seed | SE | 95% CI |
| --- | --- | --- | --- |
| 1,000 | 100 | 0.0122 | [0.1782, 0.2264] |
| 2,000 | 200 | 0.0114 | [0.1793, 0.2236] |
| 2,000 | 201 | 0.0116 | [0.1797, 0.2242] |
| 4,000 | 300 | 0.0113 | [0.1804, 0.2246] |

Full detail in `transport_wage_ratio_bootstrap_stability.csv`. B=2,000 (seed 42) is
used for the primary reported figures.

**Documented approximations** (no design information is available to resolve these
further from the files at hand):
1. No official NHTS replicate weights exist in the public-use file (confirmed: no
   jk/rep/brr/fay/bootstrap/pweight/fpc-named column in either file's metadata) --
   this bootstrap is CONSTRUCTED here from `Stratum`+`Psuno_seg`, not looked up, and
   may not exactly match whichever internal variance-estimation design StatsSA itself
   uses.
2. No finite-population correction is applied -- the standard with-replacement
   assumption for national household surveys where PSUs are a small fraction of the
   frame, not independently verified here since the overall sampling fraction is not
   published in the files available.
3. The simple with-replacement-PSU bootstrap is used rather than the more elaborate
   Rao-Wu rescaling bootstrap, for transparency and because every stratum has at
   least 29 PSUs (median 58.5) -- large enough that the two variants' small-sample
   corrections are expected to differ negligibly. This is the standard large-n_h
   justification for the simplification, not independently proven here.

**The corrected bootstrap SE (0.0115-0.0117) is close to, and only modestly above,
the earlier independent-resampling bootstrap SE (0.0094) and the trusted cost-only
reference SE (~0.009).** Unlike the withdrawn jackknife figures, this is a coherent,
internally consistent picture: joint (design-aware) resampling adds a modest amount
of variance on top of the cost-only reference, roughly consistent in direction and
magnitude with genuine PSU-level clustering and median-related sampling variability,
without the earlier method's spurious inflation or its unsupported population-effect
story.

**What these checks do NOT establish -- CORRECTED 2026-09-14 (Astra review, finding
3).** The cost-only jackknife reference check and the replicate-median/interval-
stability diagnostics above are internal-consistency and numerical-stability checks:
they confirm the bootstrap machinery is calibrated against a trusted smooth-statistic
reference and is not numerically unstable. They do NOT establish that the resulting
percentile CI has correct coverage under the actual NHTS sampling design. This
implementation is an explicit simple with-replacement PSU bootstrap, not the Rao-Wu
rescaled procedure (see approximation 3 below); the "does the CI have correct
coverage" question would need either a design-based simulation study or the survey's
own official variance-estimation replicate weights, neither of which is available
here. This is retained as a documented, useful review-stage estimate with stated
limitations, not upgraded to a validated-coverage claim.

## Frequency sensitivity, CORRECTED description

**Previously described as "under 5%"; the tested range's swing is approximately
5.5%** (5.48% precisely, under the 15-64 primary population, round-trip basis,
computed as the range between the freq=1 and freq=7 estimates relative to the
lower/freq=7 end). Full grid in `transport_candidate_frequency_sensitivity_15_64.csv`.
This is a specification-sensitivity check (how much the point estimate would move
under a different, equally defensible search-frequency assumption), and is kept
categorically separate from the design-based sampling uncertainty above -- the two
are not combined into a single interval.

## Coverage: directly supported vs. requires a frequency assumption

**Regenerated exactly for the 15-64 primary population, 2026-09-14** (previously
assumed, not computed, to be qualitatively similar to the broader-age figures). Full
detail in `transport_candidate_coverage_15_64.csv`.

| driver scenario | directly supported (weighted) | requires frequency (weighted, additional) | unresolved (weighted) | n (of 4,636 age-eligible) |
| --- | --- | --- | --- | --- |
| A | 96.79% | 1.24% | 1.97% | 4,539 resolved |
| B | 98.03% | 1.24% | 0.73% | 4,607 resolved |

These are close to, but not identical to, the previously-reported broader-age figures
(96.77%/98.04% direct, 1.99%/0.72% unresolved on the 4,655-person population) -- the
19 excluded travellers move the denominator slightly without changing the qualitative
picture. This is a THIRD, separate kind of sensitivity from sampling uncertainty and
frequency-assumption sensitivity -- it describes how much of the population a given
candidate specification can actually resolve at all, not how uncertain or how
assumption-dependent the resolved estimate is.

## Summary: three distinct kinds of uncertainty/sensitivity, kept separate

1. **Sampling uncertainty** (design-based survey-bootstrap SE/CI, joint PSU/stratum
   resampling of numerator and denominator together): reflects the survey's sample
   size and design (clustering, shared households) -- would remain even if every open
   specification choice were resolved.
2. **Specification sensitivity** (driver Scenario A/B, frequency assumption, age
   population): reflects genuinely open analytical choices -- would shrink to zero if
   a single choice were adopted for each.
3. **Coverage** (directly-supported vs. frequency-dependent vs. unresolved): reflects
   how much of the population any given specification can actually classify at all --
   a data-completeness question, not an uncertainty question.

None of these are combined into a single number or interval anywhere in this
specification. No canonical target update, held-out convergence run, or full
recalibration has been performed.
