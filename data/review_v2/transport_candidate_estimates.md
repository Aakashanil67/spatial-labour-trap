# Decision-ready candidate transport-cost estimates, 2026-09-14 -- review output only

**For the current, consolidated point estimates, design-based uncertainty and
15-64-population proposal, see `transport_measurement_specification.md` -- it
supersedes this file's uncertainty and frequency-description sections (marked below)
without changing this file's point estimates or coverage figures.**

## What this is, and what it is not

This is a set of candidate person-level transport-cost estimates, computed from ALL
administered legs (not leg-1 only), using the NHTS person-level `Weight`, with every
open assumption this review has flagged disclosed as a labelled dimension rather than
picked silently. **It does not resolve any of the open decisions listed in
`transport_definition.md`'s "What is not yet done" section, and it does not touch
`transport_budget_share` in `configs/baseline.yaml`/`data/moments.csv`.** Its purpose
is to make the concrete consequences of each open choice visible together, so a
decision (Aakash's, not this script's) can be made informed by actual numbers.

Reproducible from `scripts/build_transport_candidate_estimates.py`
(`python -m scripts.build_transport_candidate_estimates`, requires `THESIS_DATA_ROOT`),
which writes `transport_candidate_estimates.csv`,
`transport_candidate_frequency_sensitivity.csv`, and
`transport_wage_ratio_candidates.csv`.

## Primary approach vs. diagnostic, stated explicitly

- **Weighting: the NHTS person `Weight` is PRIMARY.** Unweighted means are reported
  as a diagnostic only (`unweighted_mean_rand_diagnostic`), not as a co-equal
  alternative.
- **Excursion definition: `round_trip` is PRIMARY**, consistent with the model's own
  existing interpretation of its flat transport-cost anchor -- Banerjee and
  Sequeira's R12.50 figure in `configs/baseline.yaml` is explicitly a **return** fare
  (see `src/calibrate.py`), not a one-direction fare. `one_direction` is retained as
  an explicit reporting comparison, not as a co-equal candidate.

## Frequency is a single physical schedule, CORRECTED 2026-09-14

**A real bug in the previous version of this file is fixed here.** Weekly and monthly
fares were previously converted using a divisor that did not depend on the excursion
definition at all, so a weekly bus fare produced the *same* per-trip figure under
`one_direction` and `round_trip` -- unlike the per-single/per-return fields, which
correctly differed by a factor of 2. The fix: `freq_days_per_week` is a single physical
quantity -- how many search DAYS a job seeker travels per week, where each search day
is one round trip (two one-direction legs) -- and every conversion, for every payment
period, derives from this one number. A weekly fare divided by `freq_days_per_week`
gives the round-trip cost of one search day directly; the one-direction cost is always
exactly half of the round-trip cost for the same leg, **by construction**, for every
period code (not just single/return trip).

**Automated consistency check** (`scripts/build_transport_candidate_estimates.py::check_round_trip_is_twice_one_direction`,
also regression-tested in `tests/test_transport_candidate_estimates.py`): confirms
`round_trip == 2 * one_direction` holds exactly for every one of the 4,556 resolved
records at the primary frequency and driver Scenario A.

## Coverage: directly supported vs. requires a frequency assumption

Every candidate reports **four** coverage figures rather than one: unweighted and
weighted shares of the population resolved using only per-single/per-return legs (plus
zero-fare legs) -- **"directly supported", no frequency assumption needed at all** --
and unweighted and weighted shares of the population that additionally needed a
per-week or per-month leg -- **"requires frequency assumption"**. The residual is
"unresolved" (ambiguous/DNK/internal-inconsistency/per-year legs, excluded from every
candidate here).

| excursion | driver scenario | directly supported (weighted) | requires frequency (weighted, additional) | unresolved (weighted) |
| --- | --- | --- | --- | --- |
| round_trip | A | 96.8% | 1.2% | 2.0% |
| round_trip | B | 98.0% | 1.2% | 0.7% |

The overwhelming majority of the estimate's coverage requires no frequency assumption
at all -- the per-week/per-month population is small (about 71 people combined), which
is also why the frequency sensitivity below is modest.

## Primary grid: excursion definition x driver scenario, primary frequency

| excursion definition | driver scenario | weighted mean (PRIMARY) | weighted median | unweighted mean (diagnostic) |
| --- | --- | --- | --- | --- |
| **round_trip** | A | **R39.45** | R20.00 | R42.00 |
| **round_trip** | B | **R38.94** | R20.00 | R41.36 |
| one_direction (comparison) | A | R19.72 | R10.00 | R21.00 |
| one_direction (comparison) | B | R19.47 | R10.00 | R20.68 |

Full detail in `transport_candidate_estimates.csv`. Two things worth noting:

- **The driver-scenario choice moves the primary (round_trip) estimate by under 2%**
  (R39.45 -> R38.94) -- the disputed driver population (80 of 4,655, 1.7%) is small
  relative to the whole.
- **Weighting moves the estimate materially** (R42.00 unweighted vs. R39.45 weighted
  under round_trip/A, about 6%) -- confirming the person weights are not neutral
  across the transport-cost distribution, which is exactly why weighting is treated
  as primary rather than optional here.

## Frequency-assumption sensitivity: a bounded range, not just 5-vs-7

**The previous version of this file only tested 5-vs-7 days/week and implicitly
suggested that comparison represented "the" sensitivity to frequency.** It is
corrected here with a genuinely bounded grid, `FREQUENCY_GRID = [1, 2, 3, 5, 7]`
search days/week -- from much less frequent search (once a week) to daily:

| freq (days/week) | round_trip weighted mean | one_direction weighted mean |
| --- | --- | --- |
| 1 (infrequent) | R41.46 | R20.73 |
| 2 | R40.20 | R20.10 |
| 3 | R39.78 | R19.89 |
| 5 (primary, borrowed from wage-side convention) | R39.45 | R19.72 |
| 7 (daily) | R39.30 | R19.65 |

Full detail in `transport_candidate_frequency_sensitivity.csv`. **CORRECTED
2026-09-14: the swing across this range is approximately 5.5%** (5.48% precisely,
computed relative to the freq=7 end; recomputed under the 15-64 primary population in
`transport_candidate_frequency_sensitivity_15_64.csv`), not the "under 5%" figure
stated here previously -- the frequency assumption still does not matter much for
this aggregate, but the earlier rounding understated the swing slightly.

## Candidate transport-to-wage ratio: SUPERSEDED by design-based uncertainty

**The bootstrap uncertainty below is superseded, 2026-09-14, by a design-based
jackknife -- see `transport_measurement_specification.md` and
`transport_wage_ratio_design_uncertainty.csv` for the current figures.** It resampled
the cost and wage populations INDEPENDENTLY, which understates the true sampling
variance: the two samples share 1,113 households, and independent resampling ignores
both that shared-household correlation and PSU-level clustering. The corrected,
design-based SE (0.015-0.023 depending on population) is 60-140% larger. The point
estimates below are still correct (unchanged by the uncertainty correction) and are
kept for the record; the CI/SE columns should not be used.

Built by applying the SAME wage-side methodology already used for the canonical
`transport_budget_share` moment (see `notebooks/moments/02_transport_budget_share.ipynb`):
weighted median monthly wage over NHTS respondents with a usable `Q410Salary` +
`Q411Payperiod`, converted to a daily rate at 21.7 working days/month, reproduced live
here (n=20,867, weighted median R4,300.00, daily wage R198.16 -- exact match to the
notebook's own figures). The numerator is the primary (round_trip, weighted) candidate
transport-cost mean from above.

| driver scenario | point estimate | ~~95% bootstrap CI (superseded)~~ | ~~bootstrap SE (superseded)~~ |
| --- | --- | --- | --- |
| A | **0.1991** | ~~[0.1846, 0.2214]~~ | ~~0.0094~~ |
| B | **0.1965** | ~~[0.1815, 0.2184]~~ | ~~0.0094~~ |

**Sample definitions, stated explicitly:**
- Transport-cost numerator: job-search travellers (`Q47Travlooking==Yes`) across
  walk/cycle/drive/hitchhike/listed-mode, all administered legs, round-trip basis,
  weighted by NHTS `Weight`; unresolved journeys (ambiguous/DNK/internal-inconsistency/
  per-year legs) excluded -- 97.9-99.4% weighted coverage depending on driver scenario
  (see the coverage table above).
- Wage denominator: n=20,867 NHTS respondents with a valid `Q410Salary` and a stated
  `Q411Payperiod`, weighted, median taken (not mean, to match the model's single-wage
  numeraire interpretation, exactly as the canonical moment already does).

**This candidate ratio (~0.197-0.199) is roughly double the current canonical
`transport_budget_share` value of 0.1058.** The gap is largely mechanical: the
canonical target's numerator currently sums all four raw `Q429b3Cost1`-`Q432b3Cost4`
columns per person without any payment-period conversion (treating a per-week or
per-month fare as if it were a single-day cost) and treats ambiguous/DNK costs as
R0 rather than excluding them -- both are known, already-documented open findings in
`target_dictionary.csv`, not new discoveries here. The `one_direction` comparison
ratio (dividing the one_direction candidate mean by the same daily wage) works out to
roughly 0.0995-0.0982, much closer to the current 0.1058 -- consistent with the
canonical numerator's mixed-basis sum landing closer to a one-direction-like unit than
a return-trip unit by accident, not by design. **None of this is proposed as a
replacement value.** It is reported so that the size and likely direction of a future
correction is visible ahead of the actual measurement-specification decision.

## What remains genuinely open

The excursion definition and person weighting are now treated as SETTLED (round-trip,
weighted) for the purposes of this specification -- see
`transport_measurement_specification.md`. **2026-09-14: ages 15-64 is proposed as the
primary population** for both the transport numerator and the wage benchmark (full
detail and point estimates in `transport_measurement_specification.md`); this remains
a PROPOSAL, not an adopted decision. The driver Scenario A/B choice, the exact
frequency assumption (shown to matter little in aggregate, ~5.5% across the tested
range), and whether/how to adopt any of this as `transport_budget_share` all remain
open. No `transport_budget_share` value is reported or implied as a replacement for
the current 0.1058.
