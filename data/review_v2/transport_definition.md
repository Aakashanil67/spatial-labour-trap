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
