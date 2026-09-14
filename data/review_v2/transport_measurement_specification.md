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

| population | driver scenario | point estimate | design-based 95% CI | jackknife SE |
| --- | --- | --- | --- | --- |
| **15-64 (PROPOSED primary)** | A | **0.1997** | [0.1697, 0.2297] | 0.0153 |
| **15-64 (PROPOSED primary)** | B | **0.1972** | [0.1676, 0.2269] | 0.0151 |
| broader age (sensitivity) | A | 0.1991 | [0.1550, 0.2431] | 0.0225 |
| broader age (sensitivity) | B | 0.1965 | [0.1530, 0.2400] | 0.0222 |

Full detail in `transport_wage_ratio_design_uncertainty.csv`. The population choice
moves the point estimate by under 0.3%; it moves the DESIGN-BASED UNCERTAINTY
noticeably more (SE 0.0151-0.0153 under 15-64 vs. 0.0222-0.0225 under the broader
range) -- restricting age removes some of the between-PSU variability along with the
excluded observations. The driver-scenario choice moves the point estimate by under
1.5% throughout, consistently smaller than the population effect on uncertainty.

**This candidate ratio (~0.197-0.200) remains roughly double the current canonical
`transport_budget_share` value of 0.1058**, for the reasons already documented in
`transport_candidate_estimates.md` (the canonical numerator sums raw cost columns
without payment-period conversion and treats ambiguous/DNK costs as R0). Not proposed
as a replacement value.

## Sampling uncertainty: design-based, not independent resampling

**A real correction from the prior round.** The previous bootstrap resampled the cost
(traveller) and wage populations independently -- an inadequate default, because the
two samples share 1,113 households (verified live: 3,955 traveller households,
16,064 wage households, 1,113 in both). This specification instead joins the NHTS
2020 GEOGRAPHY file (`nhts-2020-geog.dta`: `Uqno`, `Psuno_seg`, `Stratum`) to the
person file on `Uqno` -- a unique household join, 0 unmatched person records, 6,039
PSU/segment identifiers, 90 strata (all confirmed live, matching an independent
source check exactly) -- and builds a **stratified delete-1 jackknife (JK1) over
PSU/segments**: each replicate drops one PSU, reweights the surviving PSUs in that
PSU's stratum by n_h/(n_h-1), and recomputes the weighted cost mean AND the weighted
wage median TOGETHER from the same replicate's weights, so a shared household moves
both sides of the ratio together rather than independently.

**Documented approximations** (no design information is available to resolve these
further from the files at hand):
1. No official NHTS replicate weights exist in the public-use file (confirmed: no
   jk/rep/brr/fay/bootstrap/pweight/fpc-named column in either file's metadata) --
   this jackknife is CONSTRUCTED here from `Stratum`+`Psuno_seg`, not looked up, and
   may not exactly match whichever internal variance-estimation design StatsSA itself
   uses.
2. No finite-population correction is applied -- the standard with-replacement
   assumption for national household surveys where PSUs are a small fraction of the
   frame, not independently verified here since the overall sampling fraction is not
   published in the files available.
3. Every stratum has at least 29 PSUs (median 58.5), so no stratum-collapsing was
   needed for the jackknife to be well-defined -- unlike some survey designs, this
   was not a live concern here.

**The design-based SE (0.015-0.023 depending on population) is 60-140% larger than
the previous independent-resampling bootstrap SE (0.0094).** This is the expected
direction: naive independent resampling ignores both PSU-level clustering (people in
the same primary sampling unit are more alike than a simple random sample would
assume) and the shared-household correlation between the cost and wage sides, both of
which inflate the true sampling variance. The previous bootstrap SE should be treated
as understated and is superseded by the figures in this section, not read alongside
them as an equally valid alternative.

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

Carried forward unchanged from `transport_candidate_estimates.md` (computed on the
broader-age population; the 15-64 restriction changes the denominator slightly but
not the qualitative picture): roughly 97-98% of the population is resolved using only
per-single/per-return legs (no frequency assumption needed at all), ~1.2% additionally
needs a per-week/per-month leg (frequency-dependent), and the remainder is unresolved
(ambiguous/DNK/internal-inconsistency/per-year legs, excluded from every candidate
rather than imputed). This is a THIRD, separate kind of sensitivity from sampling
uncertainty and frequency-assumption sensitivity -- it describes how much of the
population a given candidate specification can actually resolve at all, not how
uncertain or how assumption-dependent the resolved estimate is.

## Summary: three distinct kinds of uncertainty/sensitivity, kept separate

1. **Sampling uncertainty** (design-based jackknife SE/CI): reflects the survey's
   sample size and design (clustering, shared households) -- would remain even if
   every open specification choice were resolved.
2. **Specification sensitivity** (driver Scenario A/B, frequency assumption, age
   population): reflects genuinely open analytical choices -- would shrink to zero if
   a single choice were adopted for each.
3. **Coverage** (directly-supported vs. frequency-dependent vs. unresolved): reflects
   how much of the population any given specification can actually classify at all --
   a data-completeness question, not an uncertainty question.

None of these are combined into a single number or interval anywhere in this
specification. No canonical target update, held-out convergence run, or full
recalibration has been performed.
