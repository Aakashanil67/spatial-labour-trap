# transport_budget_share: routing reconstruction, and withdrawal of the missingness claim

## Withdrawal

A prior pass of this review claimed that 2,247 of 4,655 job-search travellers (48.3%) had their
travel mode and cost entirely unanswered, and that excluding them (rather than the current
code's implicit zeroing) would move `transport_budget_share` from 0.1058 to 0.1844. **This claim
is withdrawn.** Checked against the live NHTS 2020 person file and reconciled with the existing
B9 routing audit (which this pass should have consulted before asserting a new finding, and did
not): those 2,247 people are exactly 1,997 walkers, 27 cyclists and 223 drivers (1,997 + 27 + 223
= 2,247, exactly), identified through the survey's own upstream routing questions
(`Q416bWalk`, `Q417bCylce`, `Q418bDrive`), not left unanswered. `Q429bMode1Trv`/`Q429b3Cost1`
(the "listed mode" cost block this project's code reads) legitimately shows "Unspecified" for
these people because the skip pattern routes them away from that block entirely, into their own
walk/cycle/drive questions instead. Treating that skip as missingness, and "excluding" the
group as though they were non-responders, was the error -- not the current code's treatment of
them (which, for walkers and cyclists, is actually correct: they are genuine zero-fare cases).

## The verified routing partition (`transport_routing.csv`)

| group | n | how identified |
| --- | --- | --- |
| walk | 1,997 | `Q416bWalk` = Yes |
| cycle | 27 | `Q417bCylce` = Yes (among those who did not walk) |
| drive | 223 | `Q418bDrive` = Yes (among those who did not walk or cycle) |
| hitchhike | 310 | `Q419bHitchh` = Yes (among those who did not walk, cycle or drive) |
| listed mode | 2,098 | none of the above -- routed to `Q428bModeofTrv`/`Q429bMode1Trv` |

Sums to 4,655 exactly. Hitchhikers are *not* routed away from the listed-mode cost block --
their `Q429bMode1Trv` carries a real value (predominantly "Car/Bakkie passenger",
"Local minibus taxi", or "through a lift club"), so they are grouped with the listed-mode
population for cost purposes, not with walk/cycle/drive.

## The verified missingness breakdown (`transport_missingness.csv`)

**SUPERSEDED, 2026-09-13, corrected further 2026-09-14. The figures in this section use a
leg-1-only reading, a since-withdrawn resolution of the `Q433bPay` category-list discrepancy, and
predate the numeric-zero/DNK classifier fixes. They are kept below for the record but are not
current. See "Journey-level rebuild" and "`Q433bPay` reconciliation" further down for the current
figures (2,169-2,239 zero / 2,390 usable / 12 ambiguous / 14-84 nonresponse depending on the
still-open Scenario A/B choice), which is what `transport_missingness.csv` now reports.**

- **2,183 of 4,655 (46.9%) are genuine zero fares**: 1,997 walkers, 27 cyclists, and 159 people
  in the hitchhike-or-listed-mode group who report `Q429b2Pay1` = "Do not pay" (verified: their
  `Q429b3Cost1` categorical value is correctly "Not applicable" in every case checked, not some
  stray numeric sentinel).
- **92 of 4,655 (2.0%) are genuine nonresponse** -- a real cost was expected but not recorded:
  85 among the 223 drivers (70 pay "per year" and 10 via "package trips/buying points" with no
  numeric `Q434bCost` ever captured for either group; 5 more have `Q434bCost` itself
  "Unspecified" despite a non-annual, non-package payment period), and 7 among the
  hitchhike-or-listed-mode group (a named travel mode but `Q429b3Cost1` = "Unspecified").
- **2,380 of 4,655 (51.1%) have a usable numeric cost figure, but its payment period has not
  yet been converted to a consistent basis.** 138 of the 223 drivers (`Q434bCost` paired with
  `Q433bPay`: 77 per single trip, 42 per return trip, 16 per week, 3 per month). 2,242 of the
  hitchhike-or-listed-mode group (`Q429b3Cost1` paired with `Q429b2Pay1`: 1,767 per single trip,
  447 per return trip, 20 per week, 9 per month, 2 per year, 4 "do not know" -- the last treated
  as unusable pending further checking, not yet decided).

## What is not yet done, and why no corrected `transport_budget_share` is reported here

Per the instruction not to update the calibration target until the reconstruction is verified,
no new point estimate is computed in this note. What remains, matching the execution plan's own
P2.3 task list almost exactly:

1. **Choose the excursion definition before converting.** Does "the day's job-search transport
   cost" mean one direction or a round trip? The single-trip and return-trip figures are not the
   same estimand, and the model side needs to match whichever is chosen. Not decided here.
2. **Convert week/month/year figures to the chosen daily/single-trip basis**, using a stated
   working-days convention consistent with (or explicitly reconciled against) the wage side's
   own 21.7-day convention -- not necessarily the same divisor, since a job-search trip frequency
   is not the same thing as a working-month length, and conflating them was flagged as a risk in
   the plan's own text.
3. **Decide how to treat the 92 genuinely nonresponse cases and, separately, the 85 drivers with
   no usable cost** (dominated by "pays per year" with no captured amount) -- report the observed
   pattern, a defensible primary procedure (e.g. exclude from the mean-cost estimator, or a
   stated imputation), and a sensitivity check against the alternative, per the plan's explicit
   instruction that listwise deletion is not automatically unbiased.
4. **Decide the weighting/averaging estimand** (person-mean vs trip-mean, per the plan's own
   averaging fixture) once the population is settled.

Only once these are decided does a defensible reconstructed `transport_budget_share` exist to
compare against the current 0.1058.

## Update, 2026-09-13: verified against the official NHTS 2020 CAPI instrument, per instruction

Fetched and read the actual fielded questionnaire (`NHTS_Jan_Mar2020`, DataFirst catalogue 886,
`https://www.datafirst.uct.ac.za/dataportal/index.php/catalog/886/download/12143`, the same
instrument this 2020 microdata was collected under). Two things confirmed, one discrepancy found.

**Confirmed: hitchhikers are routed into the listed-mode cost block, exactly as reconstructed
above.** The instrument's own enabling condition for `Q428bModeofTrv` (4.28b, "how many mode(s)
of travel...") fires when the walk/cycle/drive/hitchhike question set are all "No" *or* when
`Q419bHitchh` (hitchhike) is "Yes" -- hitchhikers get both their own routing question and the
listed-mode cost block, matching the `hitchhike_and_listed_mode` grouping in
`transport_missingness.csv`.

**WITHDRAWN, 2026-09-13 (later same day). The claim immediately below -- that the `Q433bPay`
category-list discrepancy was a PDF-extraction artifact -- is wrong and is withdrawn.** It was
based on a page-by-page reading of the PDF that missed the instrument's own printed category list
for this exact question, and on treating the `.dta`'s attached value-label dictionary as
self-evidently authoritative without checking it against a second, independent instrument source.
Astra checked the same PDF visually and found that page 38 explicitly prints only 6 categories for
`Q433bPay` -- ending in codes 5="DO NOT PAY" and 6="DO NOT KNOW", not "per year"/"package trips" --
and that page 39's enabling condition for `Q434bCost` is `Q433bPay.InList(1,2,3,4)`, i.e. the
instrument itself never lets an interviewer capture a cost for codes 5 or 6. Both of those readings
are correct; my "truncation" explanation ignored them. The original text is left below, struck
through in spirit but not deleted, for the record. **See the "Q433bPay reconciliation" section
below for the corrected treatment: this is now an open, unresolved discrepancy between the
instrument and the exported value labels, not a resolved one.**

~~**An apparent discrepancy in `Q433bPay`'s category list, checked and resolved as a PDF-extraction
artifact, not a data problem.** The rendered instrument text (page 38 of the fetched PDF) appeared
to list only 6 categories for the driver payment-period question -- Per single trip, Per return
trip, Per week, Per month, DO NOT PAY, DO NOT KNOW -- with no "per year" or "package trips"
option, which would have conflicted with the earlier live-data finding that 70 of 223 drivers
report a "per year" period. Checked directly against the fielded `.dta`'s own value labels
(`pyreadstat` variable-value-label read of `nhts-2020-person.dta`): `Q433bPay` in fact carries all
8 categories -- 1:Per single trip, 2:Per return trip, 3:Per week, 4:Per month, **5:Per year**,
**6:Package trips/Buying points**, 8:Not applicable, 9:Unspecified -- the PDF's rendered
"DO NOT PAY"/"DO NOT KNOW" interviewer-facing labels correspond to the exported "Not
applicable"/"Unspecified" codes, and the PDF text extraction simply truncated the on-screen list at
6 of 8 items. The live-data "70 per year" finding is confirmed correct; no correction to
`transport_missingness.csv` is needed.~~

## `Q433bPay` reconciliation, 2026-09-13: unresolved, not silently recoded

Reconciling the instrument (page 38-39) against the `.dta` value labels directly, rather than
trusting either source alone, surfaces a real discrepancy and a piece of evidence that favours
one reading -- but does not settle it.

**What the instrument says (Astra's reading, checked against the same PDF and confirmed here).**
`Q433bPay` (4.33b, "How did %rostertitle% make the payment of the cost used to drive to his/her
destination?") is printed with exactly 6 categories: 1 Per single trip, 2 Per return trip, 3 Per
week, 4 Per month, 5 DO NOT PAY, 6 DO NOT KNOW. `Q434bCost` (4.34b, the paired cost question)
carries the enabling condition `Q433bPay.InList(1,2,3,4)` -- it is never administered when
`Q433bPay` is 5 or 6, which is exactly the pattern the live data shows (all 80 drivers coded 5 or
6 have `Q434bCost` missing, never a captured amount).

**What the `.dta` says.** `pyreadstat`'s value-label read of `Q433bPay` gives 1-4 the same labels,
then 5:"Per year", 6:"Package trips/ Buying points", 8:"Not applicable", 9:"Unspecified" -- no
"Do not pay" or "Do not know" label anywhere on this variable.

**New evidence this pass: `Q433bPay`'s sibling question is labelled correctly.** `Q315Pay`
(3.15, the analogous driver payment-period question for education-related trips -- same
instrument design, same printed 6-category list ending in DO NOT PAY/DO NOT KNOW) carries value
labels in the *same* `.dta` file that DO match its own instrument definition: 1-4 as usual, then
5:"Do not pay", 6:"Do not know", 8:"Not applicable", 9:"Unspecified". `Q425Pay` (4.25, the
work-travel version of the same question) is labelled 5:"Per year", 6:"Package trips/Buying
points" -- the same pattern as `Q433bPay`. So within this one file, one driver-pay variable
(`Q315Pay`) has labels that agree with its own instrument text, and two others (`Q425Pay`,
`Q433bPay`) have labels that instead match the *listed-mode* payment-period questions
(`Q3182Pay1`, `Q429b2Pay1`, etc., which genuinely do offer "per year" and "package trips" as
options for passengers, per pages 29/36 of the instrument). This is consistent with a label-set
mix-up during data processing -- `Q425Pay` and `Q433bPay` appear to have had the listed-mode
label set attached to them instead of their own -- but it is evidence pointing toward that
explanation, not proof of it. It could equally be that the fielded CAPI application (the live
software respondents were actually interviewed on) differed from the printed instrument export
in front of me, and drivers genuinely could report "per year"/"package trips."

**Not resolved. Two scenarios, both carried forward.**

| | Scenario A (labels as exported) | Scenario B (instrument as printed; labels mismatched) |
| --- | --- | --- |
| Driver code 5 (n=70) | "Per year", no captured cost -> genuine nonresponse | "Do not pay" -> legitimate zero fare |
| Driver code 6 (n=10) | "Package trips", no captured cost -> genuine nonresponse | "Do not know" payment period -> genuine nonresponse (different reason, same bucket) |
| Driver legitimate zero fares | 0 | 70 |
| Driver genuine nonresponse | 80 | 10 |

`transport_missingness.csv` reports both scenarios explicitly in its `detail` column and does not
pick one. Anyone using this file for a point estimate must decide between them first; the 70-case
swing (31% of all 223 drivers) is too large to leave implicit. A decisive check would need the
official DataFirst codebook/data dictionary for this release (a third, independent source), which
has not been fetched this round.

## Journey-level rebuild of zero / positive / ambiguous / missing, 2026-09-13

The hitchhike-and-listed-mode group's missingness was previously classified using only the first
reported travel leg (`Q429bMode1Trv`/`Q429b2Pay1`/`Q429b3Cost1`). But `Q428bModeofTrv` can be
1-4: a job-search trip can use up to four different modes in sequence, each with its own
mode/payment-period/cost triple (`Q429b*` through `Q432b*`), and a leg-1-only reading silently
drops information about legs 2-4. Rebuilding the classification using all four legs, live against
the NHTS 2020 person file:

- **2,238, not 2,242, first-leg observations carry a usable numeric cost.** The earlier count
  (1,767 + 447 + 20 + 9 + 2 = 2,245, minus a stated "4 do not know") did not correctly separate
  "payment period stated but the cost value itself is `9999` (Unspecified)" from a genuine
  numeric answer. There are 2,238 first legs with a real number, 7 with a named period but an
  unspecified cost, and 4 with the payment period itself recorded as "do not know" -- these last
  two groups are qualitatively different (unspecified amount vs. unspecified whether/how paid)
  and are kept separate below rather than merged into one "nonresponse" figure as before.
- **Eighteen respondents whose first leg is "do not pay" (legitimate zero) go on to pay on a
  later leg of the same journey.** A leg-1-only reading zeroes these 18 people's transport cost
  entirely. Their journeys are not internally contradictory -- e.g. a free lift or a walk for the
  first stretch, then a paid minibus taxi for a later one is an ordinary multi-leg trip -- but
  they were miscoded as zero fares by the earlier single-leg logic. Detail: 17 of the 18 pay on
  leg 2 only; one person (record id 59019 in the live file) pays on both leg 3 and leg 4 of a
  4-leg journey; one person (id 108421) pays on legs 2 and 3 and reports "do not pay" again on
  leg 4. All 20 of these paid-leg observations happen to be coded "per single trip", so no
  cross-period mixing is needed to classify them as positive, even though no monetary total is
  computed for them (see the provisional-reconstruction section below).

**CORRECTED AGAIN, 2026-09-14 -- two further classifier bugs, both confirmed against Astra's
independent source check.** Neither changes the total (still 2,408); both move records between
buckets.

1. **Numeric-zero handling.** A leg can be free in two different ways: `pay==7` ("do not pay",
   an implied/skip-pattern zero -- the cost field is then genuinely not applicable) and a named
   payment period (codes 1-4) paired with a reported cost of exactly R0 (an *answered* zero). The
   classifier previously read cost fields only for their sentinel codes (`8888`/`9999` etc.) and
   let a literal `0` fall through to "positive", which is wrong -- R0 is not a positive cost. Two
   journeys move from fully-costed-positive to zero once this is fixed (both have their numeric
   zero on leg 1: one coded "per single trip", one "per return trip").
2. **DNK-as-unresolved.** The classifier previously let a positive leg silently override a "do not
   know" payment-period leg elsewhere in the same journey into "fully costed". That is wrong: a
   DNK leg's cost is genuinely unknown -- it could have been free or paid -- so a positive leg
   elsewhere makes the journey's *total* not fully known, the same as an unspecified-cost leg
   would. No journey in this dataset currently has both a positive leg and a DNK leg (the 2
   partially-observed journeys below are both positive+ambiguous, not positive+DNK), so this fix
   does not move any counts here, but it is now enforced and covered by a regression test
   (`tests/test_transport_review_classification.py`) rather than left as an unnoticed gap.

**Corrected journey-level classification, n=2,408 (hitchhike + listed-mode, all four legs
considered together):**

| class | n | definition |
| --- | --- | --- |
| legitimate zero, of which: | 143 | every administered leg resolves to a known zero (stated "do not pay" or a named period with cost==0) |
| &nbsp;&nbsp;involving a numeric (answered) zero leg | 2 | at least one zero leg is a named-period R0 answer, not a stated "do not pay" |
| positive (usable), of which: | 2,254 | at least one leg has a confirmed numeric cost (2,236 on leg 1 + 18 reclassified from a later leg) |
| &nbsp;&nbsp;fully costed | 2,252 | every administered leg resolves to a known value (zero fare or positive cost), at least one positive |
| &nbsp;&nbsp;partially observed | 2 | at least one leg has a confirmed positive cost, but at least one other administered leg is unresolved (unspecified cost, internal inconsistency, or DNK) -- the journey involved real payment but its total is not fully known |
| ambiguous | 7 | some leg has a named mode/period but an unspecified cost value, and no leg reaches a confirmed positive cost |
| missing / nonresponse | 4 | the only administered leg's payment period itself is "do not know" |

The fully-costed/partially-observed split matters for any future point estimate: a partially
observed journey's *known* leg cost is real data (it should not be dropped as missing), but its
*journey total* is not observable without an assumption about the unresolved leg, which is a
different problem from the 7 purely ambiguous journeys where no leg total is known at all.
Likewise, the numeric-zero split matters for interpretation, not for the estimate itself: both
kinds of zero are equally R0 for a point estimate, but a stated "do not pay" and an answered R0
are different response patterns worth keeping visible.

This replaces the earlier leg-1-only figures (159 zero / 2,242 usable / 7 nonresponse, which also
silently merged in the 4 "do not know" cases rather than reporting them separately) in
`transport_missingness.csv`. The driver and walk/cycle rows are unaffected by this specific
journey-level rebuild -- drivers are asked a single pay/cost pair with no multi-leg structure
(though drivers have their own, separately corrected, numeric-zero fix -- see below), and
walkers/cyclists never reach the `Q428bModeofTrv` block at all (confirmed from the instrument's
enabling condition, recorded above).

**Driver numeric-zero fix, 2026-09-14.** The same bug affected the driver classifier: two drivers
report a named payment period (codes 1-4) with `Q434bCost` reported as exactly R0. These were
previously folded into the "usable numeric cost" (positive) count; they are now counted as
legitimate zero fares instead. Driver `legitimate_zero` moves from 0 to 2; `usable_numeric_cost`
(now consistently meaning strictly positive) moves from 138 to 136.

**Total reconstruction, combining the transport-side rebuild with the driver-side `Q433bPay`
ambiguity (Scenario A / B from above), UPDATED 2026-09-14 for the numeric-zero corrections:**

| | Scenario A | Scenario B |
| --- | --- | --- |
| Legitimate zero fares | 2,169 / 4,655 (46.6%) | 2,239 / 4,655 (48.1%) |
| Usable numeric cost (strictly positive) | 2,390 / 4,655 (51.3%) | 2,390 / 4,655 (51.3%) |
| Ambiguous (named period, unspecified cost) | 12 / 4,655 (0.3%) | 12 / 4,655 (0.3%) |
| Genuine nonresponse | 84 / 4,655 (1.8%) | 14 / 4,655 (0.3%) |

("Legitimate zero fares" here includes both stated "do not pay" and numeric R0 answers; see the
per-group breakdown above and in `transport_missingness.csv` for the split.)

## Provisional payment-conversion figures, review output only -- the canonical target is unchanged

Per instruction, `transport_budget_share` in `configs/baseline.yaml`/`data/moments.csv` has not
been touched, and no single reconstructed point estimate is reported here. What follows is a
review-only breakdown, in `data/review_v2/transport_provisional_reconstruction.csv`, of the
*unconverted* cost figures by stated payment period -- i.e. only conversions that require no
assumption at all.

- **CORRECTED, 2026-09-14: the claim that per-single-trip costs need no conversion "under any
  excursion definition" was wrong and is withdrawn.** A per-single-trip figure is only
  adjustment-free if the excursion is itself defined as a one-direction trip. If the excursion is
  instead defined as a return journey, a per-single-trip fare understates it by roughly half,
  absent a stated (and not yet made) doubling assumption. The correct statement is: the
  per-single-trip figures require no conversion **once the excursion definition is fixed to
  one-direction**, and remain the numerically largest usable sub-population regardless (1,761
  first-leg observations with a strictly positive cost, mean R29.50, median R17 -- one further
  record with a numeric R0 cost moved to the legitimate-zero count on 2026-09-14), but "no
  adjustment under every definition" is false and should not have been asserted.
- **Per-return-trip, per-week, per-month and per-year observations are reported as raw figures
  only, with no divisor applied.** Halving a return-trip fare to approximate one direction
  assumes fare symmetry; converting a weekly/monthly figure to a daily or per-trip basis needs a
  stated trip-frequency assumption. Both remain open decisions (excursion definition, conversion
  factor -- see "What is not yet done" above), so no combined figure is computed. The per-month
  group in particular (n=9, mean R640, median R440) spans a very wide range (R190-R2,200) and a
  mechanical /21.7 divide -- reusing the wage side's working-days convention without checking it
  fits a job-search trip frequency -- is exactly the risk the plan already flags; it is not
  applied here.
- **CORRECTED, 2026-09-14: the driver per-period means reported previously (R223.55 single-trip,
  R909.56 return-trip, R920.53 weekly) were wrong, and the "inter-city travel" explanation offered
  for their skew is withdrawn as unsupported.** The scratch script that produced those figures
  excluded only the placeholder sentinel `-998` from `Q434bCost`, which never occurs in the data,
  instead of the field's actual sentinel codes (confirmed live against
  `meta.variable_value_labels`: 8888 = Not applicable, 9999 = Unspecified). Five records carry
  `Q434bCost == 9999` and were counted as a literal R9,999 fare, which alone accounts for most of
  the inflation. Astra reproduced the originally reported means exactly with those five records
  included, confirming the mechanism. **CORRECTED AGAIN, 2026-09-14 (same day): two of the
  originally reported n's also included a numeric-zero record (`Q434bCost==0`) as if it were a
  positive fare** -- those 2 records are now counted as legitimate zero fares instead (see above).
  With both corrections applied (now handled explicitly and field-specifically in
  `scripts/build_transport_review_tables.py`): **per-single-trip mean R97.87 (n=76), per-return-trip
  mean R266.66 (n=41), per-week mean R353.12 (n=16, unaffected -- neither numeric-zero record fell
  in this period)**. Still somewhat right-skewed relative to their medians (R80, R200, R300
  respectively), which is unremarkable for cost data and needs no special explanation; the previous
  inter-city-travel story was invented to explain an artifact, not a real feature of the data, and
  should not be repeated. Codes 1-4 only; the disputed codes 5/6 (Scenario A/B above) remain
  excluded from this table entirely rather than assigned to either scenario by default.
- **Restricted population, stated explicitly**: all figures above are conditional on
  `Q47Travlooking==Yes` (travelled while job-searching on the reference day) and a usable payment
  record for at least one leg; this is the same conditioning already documented for
  `transport_budget_share`'s numerator in `target_dictionary.csv` and is not a new restriction.

No frequency assumption, excursion definition, or driver-code-5/6 scenario choice has been made.
The next step remains exactly what "What is not yet done" above already lists: those four
decisions, in order, before any single `transport_budget_share` reconstruction can be compared
against the current 0.1058.

## Reproducibility, 2026-09-14

`transport_missingness.csv` and `transport_provisional_reconstruction.csv` are no longer produced
by uncommitted scratch scripts. Both regenerate from `scripts/build_transport_review_tables.py`
(`python -m scripts.build_transport_review_tables`, requires `THESIS_DATA_ROOT`), which handles
each field's sentinel codes explicitly and per-leg (leg 1 and legs 2-4 of the listed-mode block do
not share a sentinel convention, and the driver fields use a third convention again -- see the
script's own docstring), and distinguishes fully-costed from partially-observed journeys and
numeric zero from positive cost, rather than leaving those distinctions implicit in prose. Running
it reproduces every number in this document.
