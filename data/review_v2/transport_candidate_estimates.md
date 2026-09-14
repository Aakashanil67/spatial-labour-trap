# Decision-ready candidate transport-cost estimates, 2026-09-14 -- review output only

## What this is, and what it is not

This is a small, explicitly labelled grid of candidate person-level transport-cost
estimates, computed from ALL administered legs (not leg-1 only), using the NHTS
person-level `Weight`, with every open assumption this review has flagged disclosed as
a labelled dimension of the grid rather than picked silently. **It does not resolve
any of the open decisions listed in `transport_definition.md`'s "What is not yet
done" section, and it does not touch `transport_budget_share` in
`configs/baseline.yaml`/`data/moments.csv`.** Its purpose is to make the concrete
consequences of each open choice visible together, so a decision (Aakash's, not this
script's) can be made informed by actual numbers rather than in the abstract.

Reproducible from `scripts/build_transport_candidate_estimates.py`
(`python -m scripts.build_transport_candidate_estimates`, requires `THESIS_DATA_ROOT`),
which writes `transport_candidate_estimates.csv` and
`transport_candidate_frequency_sensitivity.csv`.

## What "journey total" means here

For the hitchhike/listed-mode population, a candidate total sums every administered
leg's contribution under the chosen assumptions (zero-fare legs contribute R0, a
positive leg contributes its converted cost). A journey is included in a given
candidate's average **only if every administered leg converts cleanly** under that
candidate -- any leg that is ambiguous, an internal inconsistency, "do not know," or
coded "per year" (n=1, too sparse to convert reliably) excludes the whole journey from
that candidate, rather than being silently treated as zero or dropped-and-ignored.
This is why **coverage** (the share of the full 4,655-person population actually
contributing to a given mean) is reported alongside every number below, not assumed to
be 100%. Drivers follow the same rule against their single pay/cost pair. Walkers and
cyclists contribute a fixed R0 (true zero fare by construction, no conversion
involved).

## What varies across the grid, and why

| dimension | values | disclosed status |
| --- | --- | --- |
| excursion definition | `one_direction` (per-single-trip cost as-is, per-return-trip halved) vs. `round_trip` (per-single-trip doubled, per-return-trip as-is) | **Not decided.** Both reported; see `transport_definition.md`. |
| driver `Q433bPay` codes 5/6 | Scenario A (both genuine nonresponse, excluded) vs. Scenario B (code 5 = legitimate zero, code 6 = nonresponse) | **Not decided.** See the Q433bPay reconciliation in `transport_definition.md`. |
| weighting | NHTS person `Weight` vs. unweighted | Both reported side by side; no single choice adopted. |
| week/month trip-frequency assumption | primary: 5 trips/week, 21.7 days/month (the wage side's own convention -- **borrowed, explicitly NOT verified to fit a job-search trip frequency**); alternative: 7 trips/week, 30 days/month | **Not decided**, and deliberately varied in a separate sensitivity table (below) rather than fixed once and hidden. |

## Primary grid (excursion definition × driver scenario, primary frequency assumption)

| excursion definition | driver scenario | coverage | unweighted mean | weighted mean | weighted median |
| --- | --- | --- | --- | --- | --- |
| one_direction | A | 4,556 / 4,655 (97.9%) | R21.24 | R19.97 | R10.50 |
| one_direction | B | 4,626 / 4,655 (99.4%) | R20.92 | R19.72 | R10.00 |
| round_trip | A | 4,556 / 4,655 (97.9%) | R42.00 | R39.45 | R20.00 |
| round_trip | B | 4,626 / 4,655 (99.4%) | R41.36 | R38.94 | R20.00 |

Full detail in `transport_candidate_estimates.csv`. Three things worth noting about
this table, not to be read past:

- **The excursion definition roughly doubles the estimate** (R19.97 vs. R39.45
  weighted mean, one_direction vs. round_trip, holding the driver scenario fixed at
  A) -- entirely mechanical, since round_trip treats every per-single-trip
  observation (the largest sub-population, 1,761 positive-cost observations) as
  needing doubling. This is the single largest source of variation in this grid and
  is exactly why it is not picked here.
- **The driver-scenario choice moves the estimate by under 2%** (R19.97 -> R19.72
  under one_direction) -- much smaller than the excursion-definition effect, because
  the disputed driver population (80 of 4,655, 1.7%) is small relative to the whole,
  even though the scenario choice is a large swing (0 vs. 70 driver zero fares) within
  that subgroup.
- **Weighting moves the estimate by 6-7%** (R21.24 unweighted vs. R19.97 weighted
  under one_direction/A) -- the person weights are not uniform across the transport
  cost distribution, so ignoring them is not neutral.

## Frequency-assumption sensitivity

| excursion definition | frequency assumption | weighted mean |
| --- | --- | --- |
| one_direction | 5/week, 21.7 days/month (primary) | R19.97 |
| one_direction | 7/week, 30 days/month (alternative) | R19.83 |
| round_trip | 5/week, 21.7 days/month (primary) | R39.45 |
| round_trip | 7/week, 30 days/month (alternative) | R39.30 |

Full detail in `transport_candidate_frequency_sensitivity.csv` (Scenario A only; the
driver-scenario choice barely interacts with the frequency choice since disputed
driver records never carry a week/month payment period). The frequency assumption
moves the aggregate estimate by under 1% either way, because the week/month
sub-population is small (29 people combined, against 1,761+445 single/return-trip
observations) -- **this does not mean the frequency question is unimportant to
resolve**, only that its effect on THIS particular aggregate happens to be small; a
target that weighted the week/month population more heavily (e.g. a
frequency-specific breakdown) would be more sensitive to it.

## What remains genuinely open

Everything this grid varies remains genuinely undecided: the excursion definition,
the driver Scenario A/B choice, whether to weight, and the trip-frequency assumption.
This file makes their consequences visible; it does not choose among them. No
`transport_budget_share` value is reported or implied as a replacement for the
current 0.1058.
