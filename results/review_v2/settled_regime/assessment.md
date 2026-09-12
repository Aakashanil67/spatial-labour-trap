# Bounded pre-calibration assessment of the provisional 2,250-step burn-in

Aakash chose burn-in = 2,250 steps (the conservative option from
`results/review_v2/window_stability/`) as provisional, not locked, and asked for four checks
before any recalibration runs. All four use `src.moments.compute_moments` through
`src.runner.run_moments_many` -- the exact calibration pipeline, not a reimplementation -- so
nothing here can diverge from what a real calibration run would compute. Seeds 3001+, disjoint
from `CALIBRATION_SEEDS` (1-15), `VALIDATION_SEEDS` (1001-1050) and `WEIGHT_SEEDS` (2001-2050).

Scripts: `scripts/assess_settled_regime.py` (items 1, 2, 4, and the local-sensitivity half of
item 3) and `scripts/diagnose_window_stability.py --vary-param` (the warm-up half of item 3).
Data: `results/review_v2/settled_regime/*.csv` and `results/review_v2/settled_regime/vary_*/`.

## Headline finding: firm_kappa's convergence speed is not a corner-case problem

**This is the finding that most needs a decision, not a note.** Checked whether any plausible
setting of the three parameters that remain estimated needs longer than 2,250 steps to settle
(`--vary-param`, seeds 1001-1003, 3,600-step horizon). `search_cost_per_trip` and `firm_radius`
converge at essentially the same speed as the fitted point across their *entire* bound range --
no warm-up concern from either. `firm_kappa` is different in kind, not degree:

| firm_kappa | discouraged_share at step 3,301-3,451 | capital mean at step 3,301-3,451 | settled? |
| --- | --- | --- | --- |
| 0.2 (lower bound) | 0.39 | 0.015 | yes, by ~step 900 |
| 0.224 (fitted) | 0.34 | 0.015 | yes, by ~step 900 |
| 0.5 | 0.045 | 0.114 | no |
| 0.9 (baseline.yaml's original default) | 0.025 | 0.257 | no |
| 1.4 | 0.023 | 0.288 | no |
| 2.0 (upper bound) | 0.022 | 0.307 | no, and still falling steeply |

Every value tested above about 0.3-0.5 -- roughly the top 80-90 per cent of `firm_kappa`'s
current (0.2, 2.0) box -- is nowhere near settled at step 3,301, let alone 2,250. The mechanism:
higher `firm_kappa` means firms post vacancies far more aggressively, so almost every seeker is
hired almost immediately (`n_non_employed` is exactly 0 for hundreds of steps at kappa=2.0);
discouragement and long-term unemployment can only start accumulating once the fixed separation
rate (0.0296) trickles a non-employed pool into existence, which takes a very long time when
hiring is this fast. At kappa=2.0's most extreme point, the decay rate implies full convergence
somewhere on the order of step 9,000, not 2,250 -- and that region is also economically
degenerate (`long_term_share` is exactly 0 throughout the window tested, since there is
essentially no unemployed stock to measure a duration share on).

**Why this matters for the search, not just the diagnostic.** The Latin hypercube stage samples
roughly uniformly across the *whole* box before Nelder-Mead ever starts refining. A large
majority of those 200 draws will land at `firm_kappa` values where 2,250 steps of burn-in is not
remotely enough, so their reported moments would describe an early transient rather than
anything the fitted parameter point represents -- which is exactly the failure mode this whole
exercise exists to catch, just showing up in a parameter's *exploration* range rather than in
the choice of window for the *fitted* point.

**Not decided here.** Three ways to resolve it, each with a real cost, and none obviously right
without Aakash's input: (a) narrow `firm_kappa`'s calibration bounds to a range that settles
inside an affordable horizon (e.g. something like (0.2, 0.5), which would need its own
justification, not just computational convenience); (b) use a much longer burn-in for the whole
search, which the kappa=2.0 extrapolation suggests could mean thousands of steps, ballooning the
per-evaluation cost far past the roughly-a-day estimate given for the fixed-window recalibration;
(c) an adaptive scheme that runs longer only when a candidate's own diagnostics show it hasn't
settled, which is more implementation work and a new source of things to get wrong. This is
flagged for Aakash's decision, not resolved by picking one.

## 1. Initial-condition differences against the moments' own accuracy requirements

Reused the window-stability sweep's cross-multiplier ranges (`results/review_v2/window_stability/
moment_summary.csv`), now benchmarked against each moment's own precision rather than an
arbitrary tolerance -- specifically, the simulation standard error of the mean at the 15-seed
averaging the calibration actually uses (computed directly below, section 2). At window
2251-2400: `discouraged_share`'s cross-multiplier range (0.00087) is 17 per cent of its own
15-seed simulation SE (0.0052); `transport_budget_share`'s (0.00037) is 31 per cent of its SE
(0.0012); `long_term_share`'s (0.0037) is 56 per cent of its SE (0.0066) -- smaller than the
noise floor the search itself runs on, but not by as wide a margin as the other two.
`distance_gradient_slope` cannot be benchmarked this way from the multiplier sweep, since that
sweep used a single seed per point; section 2 below handles it properly with 50 replicate seeds
instead. Bottom line: for the three moments this comparison can be made for, the residual
initial-condition dependence at the provisional window is smaller than the ordinary simulation
noise the calibration already has to tolerate at every evaluation, and by a comfortable margin
for two of the three.

## 2. Simulation precision, all four moments, transient window vs settled window

50 replicate seeds, same fitted parameters (`initial_search_capital` now fixed, not varied),
transient window (51-150) and provisional settled window (2251-2400):

| moment | simulation SE of mean @ 15 seeds (settled) | data SE (`moments.csv`) | ratio |
| --- | --- | --- | --- |
| `distance_gradient_slope` | 0.231 | 1.4048 | 0.16 |
| `discouraged_share` | 0.0052 | 0.0023 | 2.25 |
| `transport_budget_share` | 0.0012 | 0.0055 | 0.21 |
| `long_term_share` | 0.0066 | 0.0054 | 1.22 |

**`distance_gradient_slope`'s simulation precision is adequate, once the right average is
used.** The window-stability report's "cannot be assessed" was about a *single* uninstrumented
cross-section; averaged over the 15 seeds the calibration actually uses, simulation noise is
only 16 per cent of the empirical target's own uncertainty -- a real answer to item 2, not a
restated limitation. `discouraged_share` and `long_term_share` are the opposite: simulation
noise at 15 seeds is *larger* than (`discouraged_share`, 2.25x) or comparable to
(`long_term_share`, 1.22x) their own data SE. This is not a new problem the settled window
creates -- the transient window's ratios are the same to two decimal places (2.22 and 1.14) --
and the existing MSM weight construction already folds simulation variance into the combined
covariance for exactly this reason. It is worth stating plainly rather than leaving implicit:
for these two moments, the search's own Monte Carlo noise, not the survey's sampling
uncertainty, is the binding precision constraint, at either window.

**Does the settled window shift the moments' values, independent of noise?** Yes, for one:
`distance_gradient_slope`'s mean moves from -0.963 (transient) to -0.422 (settled), a
0.54-point shift against a simulation SE of about 0.23 -- roughly 2.3 SEs, a real change, not
noise. `discouraged_share` also shifts (0.130 to 0.352, expected and already documented in
`DECISIONS_PENDING.md` question 1) and `long_term_share` and `transport_budget_share` barely
move (0.79 vs 0.79; 0.091 vs 0.091). None of this is a new finding for the three time-averaged
moments -- it restates what's already recorded -- but the `distance_gradient_slope` shift is: a
recalibration against the settled window will target a materially different gradient value than
the one the published fit was compared against, on top of everything already known about that
moment's weak identification.

## 3. Local sensitivity of the three remaining parameters, settled window

8 seeds per point, settled window, values spanning each parameter's calibration bounds:

- **`search_cost_per_trip`** moves both `discouraged_share` (0.324 to 0.425 across the bounds)
  and `transport_budget_share` (0.069 to 0.167) substantially -- clearly identified in the
  settled regime, not just the transient one.
- **`firm_radius`** moves almost nothing except `distance_gradient_slope` across its *entire*
  bound range (`discouraged_share` 0.3621/0.3618/0.3620 at the low/fitted/high bound;
  `long_term_share` 0.7973/0.7964/0.7969) -- this reconfirms the already-documented flat
  identification region (`DECISIONS.md`, "firm_radius=4.1 and 6.0 produced identical
  histories") in the settled regime too. Not a new problem, not fixed by the window choice
  either.
- **`firm_kappa`** moves `discouraged_share` (0.390 to 0.012) and `long_term_share` (0.842 to
  0.000) enormously across its bounds -- strong identification in principle, but the region
  giving that movement (values above about 0.5) is exactly the region section headline above
  shows is not settled at any affordable horizon tested.

## 4. Window length after burn-in, and a later window

15 seeds, burn-in 2,250, window lengths 150/300/600 steps, plus a later 150-step window at
burn-in 4,500 (same seeds, same trajectories continued further, not independent draws):

`discouraged_share`, `transport_budget_share` and `long_term_share` are stable across every
window length tested and at the later window (differences of 0.001-0.003, well inside the
15-seed sampling noise) -- **150 steps, the current convention, is already long enough to
average these three moments**, and moving to a later burn-in changes nothing for them.
Precision does improve modestly going from 150 to 300 steps (`discouraged_share`'s seed SD
drops from 0.0154 to 0.0096) with little further gain from 300 to 600 -- a 300-step window
would be a defensible, cheap upgrade if extra precision on these three is wanted, though not a
necessary one.

`distance_gradient_slope` is the exception, and section 2's shift is not fully resolved by this
check either: comparing the *same* 15 seeds' trajectories at step 2,400 against step 4,650 (a
paired, not independent, comparison) gives a mean difference of -0.575 with a standard error of
0.320 -- a t-statistic of about 1.8, suggestive of continued drift in the same direction as
section 2's transient-to-settled shift, but not decisive at this sample size. **Honest
conclusion: this moment's cross-sectional value may still be moving somewhere past step 2,400,
and 15-50 replicate seeds cannot resolve that cleanly either way** -- it would take either many
more replicate seeds or a purpose-built estimator (e.g. one that pools several cross-sections
from the same run rather than reading only the final step) to settle, and neither has been
built here.

## Summary against the four requested checks

1. **Initial-condition differences vs accuracy requirements:** done for three of four moments;
   all comfortably or moderately inside the calibration's own simulation-noise floor.
2. **`distance_gradient_slope` simulation precision:** adequate at the calibration's standard
   15-seed averaging (16 per cent of the empirical SE) -- resolves the window-stability
   report's open question with a number, not a restated caveat. Whether its *value* has fully
   stopped moving with the window is a separate, still-open question (section 4).
3. **Sensitivity/identification of the remaining three parameters, and warm-up under plausible
   settings:** `search_cost_per_trip` is fine. `firm_radius`'s pre-existing weak identification
   persists unchanged. `firm_kappa` is well identified but needs a decision -- see the headline
   finding above.
4. **Window length and a later window:** 150 steps is already adequate for three of the four
   moments; 300 steps would buy a modest, optional precision gain. `distance_gradient_slope`'s
   window-length question is not fully resolved (section 4).
