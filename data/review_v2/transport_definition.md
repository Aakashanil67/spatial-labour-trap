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

**SUPERSEDED, 2026-09-13 (later same day). The figures in this section use a leg-1-only reading
and a since-withdrawn resolution of the `Q433bPay` category-list discrepancy. They are kept below
for the record but are not current. See "Journey-level rebuild" and "`Q433bPay` reconciliation"
further down for the corrected figures (2,165-2,235 zero / 2,394 usable / 12 ambiguous / 14-84
nonresponse depending on the still-open Scenario A/B choice), which is what
`transport_missingness.csv` now reports.**

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

**Corrected journey-level classification, n=2,408 (hitchhike + listed-mode, all four legs
considered together):**

| class | n | definition |
| --- | --- | --- |
| legitimate zero | 141 | every administered leg is "do not pay" |
| positive (usable) | 2,256 | at least one leg has a confirmed numeric cost (2,238 on leg 1 + 18 reclassified from a later leg) |
| ambiguous | 7 | some leg has a named mode/period but an unspecified cost value, and no leg reaches a confirmed positive cost |
| missing / nonresponse | 4 | the only administered leg's payment period itself is "do not know" |

This replaces the earlier leg-1-only figures (159 zero / 2,242 usable / 7 nonresponse, which also
silently merged in the 4 "do not know" cases rather than reporting them separately) in
`transport_missingness.csv`. The driver and walk/cycle rows are unaffected by this rebuild --
drivers are asked a single pay/cost pair with no multi-leg structure, and walkers/cyclists never
reach the `Q428bModeofTrv` block at all (confirmed from the instrument's enabling condition,
recorded above).

**Total reconstruction, combining the transport-side rebuild with the driver-side `Q433bPay`
ambiguity (Scenario A / B from above):**

| | Scenario A | Scenario B |
| --- | --- | --- |
| Legitimate zero fares | 2,165 / 4,655 (46.5%) | 2,235 / 4,655 (48.0%) |
| Usable numeric cost | 2,394 / 4,655 (51.4%) | 2,394 / 4,655 (51.4%) |
| Ambiguous (named period, unspecified cost) | 12 / 4,655 (0.3%) | 12 / 4,655 (0.3%) |
| Genuine nonresponse | 84 / 4,655 (1.8%) | 14 / 4,655 (0.3%) |

## Provisional payment-conversion figures, review output only -- the canonical target is unchanged

Per instruction, `transport_budget_share` in `configs/baseline.yaml`/`data/moments.csv` has not
been touched, and no single reconstructed point estimate is reported here. What follows is a
review-only breakdown, in `data/review_v2/transport_provisional_reconstruction.csv`, of the
*unconverted* cost figures by stated payment period -- i.e. only conversions that require no
assumption at all.

- **Per-single-trip costs need no conversion under any excursion definition**: 1,762 first-leg
  observations, mean R29.49, median R17. This is the only sub-population whose reported number is
  already directly usable regardless of how the excursion (one-direction vs. return) question is
  eventually decided.
- **Per-return-trip, per-week, per-month and per-year observations are reported as raw figures
  only, with no divisor applied.** Halving a return-trip fare to approximate one direction
  assumes fare symmetry; converting a weekly/monthly figure to a daily or per-trip basis needs a
  stated trip-frequency assumption. Both remain open decisions (excursion definition, conversion
  factor -- see "What is not yet done" above), so no combined figure is computed. The per-month
  group in particular (n=9, mean R640, median R440) spans a very wide range (R190-R2,200) and a
  mechanical /21.7 divide -- reusing the wage side's working-days convention without checking it
  fits a job-search trip frequency -- is exactly the risk the plan already flags; it is not
  applied here.
- **Driver per-period costs (codes 1-4 only, n=143) are reported the same way**, restricted to
  the unambiguous codes; the disputed codes 5/6 (Scenario A/B above) are excluded from this table
  entirely rather than assigned to either scenario by default. Driver costs are noticeably
  higher and more right-skewed than passenger costs at every payment period (e.g. per-single-trip
  mean R223.55 vs. median R80, against R29.49/R17 for passengers) -- plausibly a mix of short
  local trips and longer, inter-city job searches among car owners, not investigated further this
  round.
- **Restricted population, stated explicitly**: all figures above are conditional on
  `Q47Travlooking==Yes` (travelled while job-searching on the reference day) and a usable payment
  record for at least one leg; this is the same conditioning already documented for
  `transport_budget_share`'s numerator in `target_dictionary.csv` and is not a new restriction.

No frequency assumption, excursion definition, or driver-code-5/6 scenario choice has been made.
The next step remains exactly what "What is not yet done" above already lists: those four
decisions, in order, before any single `transport_budget_share` reconstruction can be compared
against the current 0.1058.
