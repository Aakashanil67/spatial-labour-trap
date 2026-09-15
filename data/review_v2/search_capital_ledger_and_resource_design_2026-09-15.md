# Search-capital ledger and a bounded Option-C resource-design investigation (corrected, second pass)

15 September 2026, corrected same day. `DESIGN_A_REVIEW.md` independently re-checked the first
version of this document against the model's own transition order, found a genuine timing/algebra
error in the affordability derivation, a mutually incompatible pair of constraints (a single flat
transfer cannot simultaneously flip the budget bound at the target fares AND respect global
scarcity at every agent's actual fare), a payment-timing/eligibility mismatch against the stated
observation convention, an under-evidenced behavioural assumption, a wrong fixed/estimated
parameter count, and an incomplete policy-budget treatment. **This is a corrected, in-place
replacement of the first version's Sections 4-10 (Sections 1-3 -- the `search_capital` definition
and the paid-trip mapping check -- are retained with one claim softened per the review's point 4,
noted where it occurs). Nothing in this document changes `src/`, `configs/`, or any canonical
target. No new simulation campaign was run.** Every quantitative claim below is either closed-form
algebra, or the output of a standalone, independently-executed verification script
(`data/review_v2/verify_design_a_ledger_2026-09-15.py`, writing
`search_capital_design_verification_2026-09-15.json`, both committed alongside this document) --
never an expected value copied from the review without being independently re-derived. The current
model and its budget-bound finding are preserved throughout.

## 1. `search_capital`, defined precisely (unchanged from the first version)

**What it is, in the model as implemented**: `search_capital` is a job-seeker's currently-available,
liquid, JOB-SEARCH-EARMARKED budget. It has exactly one legitimate use in the model (paying
`cost_per_trip` for a search trip) and exactly one legitimate source under the CURRENT
specification (`household_inflow`, credited only while `DISCOURAGED`). It is:

- **NOT total household wealth.** It has no role in consumption, housing, or any other spending;
  the model tracks no other asset or liability.
- **NOT a general savings account.** It earns no interest, accepts no discretionary deposits, and
  is not drawn down for anything but search trips.
- **NOT automatically replenished by wage income.** `step_employed()`/`resolve_hire()` never touch
  `search_capital` (verified directly in `src/agents.py`) -- an employed agent's capital is FROZEN
  at exactly its value at the moment of hire, for the entire employment spell, however long.

This is closer to a ring-fenced "job-search allowance" than to a wealth stock. **`REVIEW_AND_
RECOMMENDATION.md`'s own caveat, restated**: this is a possible, code-consistent modelling choice,
not something the code alone proves is the empirically correct interpretation, nor a justification
for every existing funding restriction. What follows treats it as the working definition to reason
from, not as an established fact about real job seekers.

## 2. The baseline EVENT ledger, in the model's own step order

**Corrected 2026-09-15 (second pass)**: the first version presented a table of terminal
OBSERVATION-CATEGORY rows (E/U/D-soft/D-hard). `DESIGN_A_REVIEW.md` Section 3 is explicit that
terminal-category rows are not enough -- several events cross categories WITHIN one step (a hard-D
agent can re-enter, search, and be hired all in the same step; a newly-separated agent can search
and be hired in the same step), and a design proposal needs the actual EVENT SEQUENCE, not just
the start/end labels. This section replaces the category table with the event sequence
`CityModel.step()` actually executes (`src/model.py`), worked through five concrete numeric
examples covering exactly the cases the review named: inactivity, hard-D re-entry, separation,
ordinary trip-taking, and same-month hiring.

**The seven-step order, exactly as coded**: (1) separations (`EMPLOYED->SEARCHING`, capital
untouched); (2) re-entry (`DISCOURAGED`: `capital += g`; flips to `SEARCHING` if `capital >= r`);
(3) capital-exhaustion check (a `SEARCHING` agent that cannot afford one trip, using capital as it
stands after step 2, becomes `DISCOURAGED`, capital untouched at the transition); (4)
`u_t`/`v_t`/`l_t`/`disc_t` stocks recorded (D11, pre-matching); (5) `months_jobless` credited; (6)
trip decision and payment (`step_searching()`: `capital -= n_{i,t} * c_i`); (7) matching
(`resolve_hire()`: state -> `EMPLOYED`, capital untouched).

**Where any new transfer credit is placed matters, and is fixed here explicitly**: any credit this
document proposes is applied WITHIN step 6, immediately AFTER the trip payment is subtracted and
STRICTLY BEFORE step 7's matching runs. This is a structural property, not a claim: this step's own
credit is computed and added after this step's own trip cost has already been subtracted, so it
can never retroactively finance the very trip that triggered it (checked by the ORDER OF OPERATIONS
in `verify_design_a_ledger_2026-09-15.py::ledger_path()`, not merely asserted in prose).

### 2.1 Five worked event sequences (illustrative numbers; `c=0.007405`, `phi=0.75`, `h_i=phi*c_i`
### -- `phi` and the trip-activity eligibility rule are defined and justified in Section 4)

**(a) Inactivity (D-soft).** Capital `0.02000`, `SEARCHING`. Step 6: `decide_trips()` returns `0`
(belief-inactive). No payment, no credit (the trip-activity rule requires `n_{i,t}>=1`). `k_{t+1}
= 0.02000` (static).

**(b) Hard-D re-entry with same-step search.** Capital `0.03300`, `DISCOURAGED`, entering the step.
Step 2: `capital += g(0.008)` -> `0.04100`; `0.04100 >= r(0.035)` -> flips to `SEARCHING`. Step 3:
`0.04100 >= c(0.007405)` -> passes, stays `SEARCHING`. Step 6: `decide_trips()` returns `1` (now
capital-solvent) -> pay: `0.04100 - 0.007405 = 0.033595`; credit (trip-activity, `n>=1`): `+
0.00555375 = 0.03914875`. Step 7: not hired this step (illustrative). Final: `SEARCHING`,
classified `U`, `k_{t+1} = 0.03914875`. This is exactly the compound event the review names: "a
hard-D agent can receive `g`, resume search, incur trip costs, receive `h`... within one step."

**(c) Separation, same-step search, same-step hire.** Capital `0.05000` (frozen from a previous
hire), `EMPLOYED`, entering the step. Step 1: separation draw fires -> `SEARCHING`, capital
unchanged (`0.05000`). Step 3: `0.05000 >= c` -> passes. Step 6: `decide_trips()` returns `1` ->
pay: `0.05000 - 0.007405 = 0.042595`; credit: `+ 0.00555375 = 0.04814875`. Step 7: matching hires
this agent this step -> `resolve_hire()`: state -> `EMPLOYED`, `months_jobless -> 0`, **capital
untouched by `resolve_hire()`, so it freezes at `0.04814875` -- INCLUDING this same step's
credit.** This is the review's second named compound event, and it fixes the payment-timing
question directly: under the TRIP-ACTIVITY eligibility rule adopted below (Section 4), a same-step
hire DOES receive the credit for the trip it made before being hired, even though its terminal,
post-matching observation category for this step is `E`, not `U`.

**(d) Ordinary trip-taking (continuing `U`).** Capital `0.03000`, `SEARCHING`. Step 6:
`decide_trips()` returns `1` -> pay: `0.03000 - 0.007405 = 0.022595`; credit: `+ 0.00555375 =
0.02814875`. Not hired this step. Final: `SEARCHING`, `U`, `k_{t+1} = 0.02814875`.

**(e) Multi-trip active month.** Capital `0.05000`, `SEARCHING`. Step 6: `decide_trips()` returns
`2` -> pay: `0.05000 - 2*0.007405 = 0.03519`; credit is paid ONCE per active month regardless of
trip count (Section 4 states why), not per trip: `+ 0.00555375 = 0.04074375`. Net change this
step: `-0.00925625`, matching `c*(phi-n)` at `n=2` exactly (`search_capital_design_verification_
2026-09-15.json`'s `4_multi_trip_net_change...` block, independently re-derived, not copied).

All five numbers above are reproduced by `verify_design_a_ledger_2026-09-15.py` (the same `phi`,
same fare, same arithmetic), not merely asserted in this prose.

## 3. The paid-trip-to-active-search mapping, checked

`scripts/observation_layer.py::classify_observation()` defines `U` as: `SEARCHING` AND
`trips_this_step >= 1`. Because the model has exactly one search action (paying for a trip), this
mapping is EXACT as a description of the model's own internal mechanism -- there is no other
channel through which a `JobSeeker` can search.

**CORRECTED 2026-09-15 (second pass), per `DESIGN_A_REVIEW.md` Section 4's closing paragraph**:
the first version of this document claimed this makes the model's `U` stock "structurally biased
toward UNDER-counting active search relative to QLFS." **That overstates what is established.**
Real job seekers do have search channels the model cannot represent (phone calls, online
applications, an already-planned-commute walk-in), and this IS a genuine coverage limitation on
the mapping between model-`U` and QLFS's "actively searching" category. But a coverage limitation
is not, by itself, evidence of a NUMERICAL BIAS in every fitted model share -- the model's other
parameters are estimated jointly against the observed target, and a systematic coverage gap could
be partly absorbed elsewhere in the fit rather than showing up as a clean directional bias in the
final calibrated shares. **The corrected claim**: the mapping is exact for the model's own
mechanism, and a strict subset of QLFS's real definition when compared externally; whether or in
which direction that produces a numerical bias in a fitted share is NOT established here and is
not claimed.

This remains checked here, not fixed here, for the same reason as before: `k=0` stays the current
comparison convention, explicitly distinguished from a claim that QLFS respondents themselves apply
a zero-tolerance, trip-gated rule. No free-search channel, clock switch, or target redefinition is
proposed.

## 4. The corrected transfer design: one explicit rule, resolving the reported incompatibility by
## a disclosed reparametrisation, not a hidden fix

### 4.1 The incompatibility, reported explicitly, as instructed

The first version proposed a SINGLE FLAT currency parameter `g_s`, required to satisfy TWO
conditions at once: (i) large enough to flip the budget bound's 13-consecutive-month infeasibility
at the target-compatible fares (needing `g_s` of roughly `0.0024`-`0.0058`, corrected in Section
4.2 below), and (ii) smaller than EVERY agent's own fare across the WHOLE admissible
`search_cost_per_trip` range `[0.001, 0.02]`, including agents very close to the CBD at the low end
of that range. `DESIGN_A_REVIEW.md` reports, and this document independently re-verifies (Section
5 of `verify_design_a_ledger_2026-09-15.py`'s output, using the review's own reported minimum
fares from this project's actual 500-agent development configurations at `search_cost_per_trip=
0.001`): the smallest fares any real agent in those configurations actually faces are
`0.001524986`, `0.001432336`, `0.001276179` across the three development seeds -- an order of
magnitude below the `~0.004`-`0.006` a single flat transfer would need to be to do anything useful
at the target fares. **These two requirements are mutually incompatible for a single fixed
currency constant. This is reported explicitly, as a genuine incompatibility, not resolved by
picking a new number that happens to avoid the conflict.**

### 4.2 The resolution: a disclosed reparametrisation, not a hidden fix

Per the review's own guidance ("changing the domain or parameterisation is a disclosed
specification choice, not a hidden implementation fix" -- and "`h<c` is a sufficient condition for
decline in every active month, not a necessary condition for every endogenous multi-trip path"),
**this document redefines the transfer from a fixed currency amount to a fixed PROPORTION of the
agent's own out-of-pocket cost**: `h_i = phi * c_i^{oop}`, where `c_i^{oop}` is agent `i`'s
out-of-pocket cost this trip (equal to the gross fare `c_i` absent any transport subsidy; Section
7 below defines it under a subsidy) and `phi in [0, 1)` is a single, dimensionless fraction.

**This dissolves the incompatibility by construction, not by choosing new numbers to hide it**:
`h_i = phi * c_i^{oop} < c_i^{oop}` holds for ANY `c_i^{oop} > 0` whenever `phi < 1` -- true for
every agent's own fare, at every point in the admissible range, automatically, without checking a
global minimum separately. The design QUESTION becomes: is there a single `phi < 1` that ALSO
satisfies the (corrected, Section 4.3) affordability requirement at every target-compatible fare?
Answered numerically, not assumed: **yes** -- `phi = 0.75` exceeds the required threshold at all
three target fares with margin (Section 4.3), and is independently confirmed against the actual
minimum fares above (`h_i` at `phi=0.75`: `0.00114`, `0.00107`, `0.00096` respectively -- each
strictly below its own `c_min`, verified in
`search_capital_design_verification_2026-09-15.json`'s `5_actual_fare_domain_check_a_0_001`
block).

**Behavioural role of `phi`**: a household or informal-network resource-sharing rate -- the
fraction of a job seeker's own out-of-pocket search cost that continues to be covered by family or
informal support WHILE the seeker is actively making the effort to search. `phi < 1` throughout
means the household never covers the WHOLE cost -- some scarcity always remains on an active month
with a positive out-of-pocket cost (worked in Section 5).

### 4.3 The affordability derivation, corrected for payment timing

**CORRECTED 2026-09-15 (second pass), per `DESIGN_A_REVIEW.md` Section 1**: the first version's
derivation implicitly credited the 13th month's transfer as financing the 13th month's own trip. It
does not -- the transfer for month `m` is credited AFTER month `m`'s trip is paid (Section 2), so
only `m-1` transfers have arrived by the time trip `m` must be funded. Corrected derivation, for a
continuously-active, one-trip-per-month path (the cheapest sustained path, matching how the
original budget bound was itself framed):

```
balance_before_trip_m = x - (m-1) * (c - h),  where h = phi * c
```

Funding trip 13 requires `x - 12*(c-h) >= c`. Since `x < B = max(r,c)+g` (the unchanged re-entry
bound), a NECESSARY (not sufficient -- the realised `x` may be lower) condition for there to exist
ANY starting balance near the upper bound that can sustain the streak is obtained at `x`'s supremum:

```
phi > (13 - B/c) / 12
```

-- re-derived and asserted directly in `verify_design_a_ledger_2026-09-15.py::required_phi()`, not
copied from the review's own numbers. Using `r=0.035`, `g=0.008` (`B=0.043` for every admissible
fare, since the whole range is below `r`):

| fare `c` | required `phi` (this document, re-derived) | required `phi` (independently confirmed by the standalone script) |
| --- | ---: | ---: |
| 0.005665 (double-`b` central) | 0.450794 | 0.450794 |
| 0.007405 (primary-`b` central) | 0.599426 | 0.599426 |
| 0.009145 (`b=0` central) | 0.691498 | 0.691498 |

**`phi = 0.75` exceeds all three**, and is confirmed by direct simulation of the 13-month ledger at
each fare (`verify_design_a_ledger_2026-09-15.py`'s step 3: all three paths complete 13 affordable
months from a re-entry balance of `0.04`; the review's own failing example, at the ORIGINAL
(uncorrected) flat transfer, is independently reproduced here failing at exactly month 11, matching
the review's `verification.json` exactly, confirming this document's ledger function agrees with
the review's before extending it).

**Same necessary-not-sufficient caveat as before, restated**: this proves the STRUCTURAL
impossibility is removed for a plausible re-entry balance; it does not prove agents' actual,
endogenous trip-taking (`decide_trips()`, unchanged, still a function of the perceived hire rate)
would realise a 13-month streak, nor that a resulting simulated share would be well-fitted.

## 5. Pathology checks, re-worked for the corrected, proportional design

- **Unlimited resource accumulation?** No -- and now checked for MULTI-trip months, not only
  `n=1`. Net change on an `n`-trip active month is `c*(phi - n)`. Since `phi < 1 <= n` for any
  `n>=1`, this is STRICTLY NEGATIVE for every trip count the model allows (`n` in `1..
  max_trips_per_step=3`), independently verified for `n in {1,2,3}` at all three target fares
  (`search_capital_design_verification_2026-09-15.json`'s `4_multi_trip_net_change...` block, all
  negative). D-soft (belief-inactive) months remain excluded from any credit (unchanged from the
  first version), so no channel exists for capital to grow while nominally `SEARCHING` and
  inactive.
- **Discouragement made absorbing?** No. Hard-`DISCOURAGED` dynamics (`+g`, re-entry at `r`) are
  completely untouched by this design.
- **Scarcity removed entirely?** No, and now this is a PROPERTY OF THE PARAMETRISATION, not a
  constraint that must be separately checked and could silently fail: `h_i = phi * c_i^{oop} < c_i
  ^{oop}` for any `c_i^{oop}>0` whenever `phi<1`, automatically, for every agent, at every fare, in
  every policy arm (Section 7). The one edge case where net change is exactly zero, not negative,
  is `c_i^{oop}=0` (a fully-subsidised trip, Section 7) -- stated explicitly there as an INTENDED
  policy effect, not a design flaw.
- **Free search?** No. The trip-cost mechanism is unchanged; the transfer finances a fraction of a
  real, incurred cost, it does not waive it.
- **Effort-contingent transfer, a genuine additional assumption**: `DESIGN_A_REVIEW.md` Section 4
  is right that this eligibility rule (paid only on a month with `n>=1`) is a SPECIFIC household-
  support assumption tied to observed effort, distinct from and not directly evidenced by the
  cited WIDER paper (which studies an UNCONDITIONAL transfer). This is not resolved by excluding
  D-soft months for accumulation reasons alone -- accumulation avoidance explains why D-soft
  months are excluded FROM THIS PARTICULAR DESIGN, it is not evidence that real household support
  stops when a person happens to make zero trips in a month, and a static D-soft balance for one
  month does not establish a permanent behavioural limbo (trip decisions are revisited every
  step). **Labelled here as an explicit, additional modelling assumption**, not defended as
  empirically established, carried into the recommendation (Section 10).
- **Anticipated vs. realised-only**: `decide_trips()` is UNCHANGED by this design -- an agent's
  trip-intensity decision this step still uses `cost_per_trip` (the full, un-netted cost), not a
  `phi`-adjusted expectation of net cost. This keeps the proposal an ACCOUNTING-ONLY overlay on the
  realised capital balance (no behavioural equation is touched), which is a deliberate, disclosed
  choice, not an oversight: whether a future version should let agents ANTICIPATE the transfer in
  their search-intensity decision is a SEPARATE behavioural-modelling question, requiring an actual
  change to `decide_trips()` (a production mechanism, out of scope this batch), not assumed
  equivalent to the accounting-only version here.

## 6. Fixed / estimated / scenario table, corrected

**CORRECTED 2026-09-15 (second pass), per `DESIGN_A_REVIEW.md` Section 5**: the first version
wrongly stated four parameters are currently estimated (`search_cost_per_trip`, `firm_kappa`,
`initial_search_capital`, `firm_radius`). The approved specification FIXES `initial_search_capital`
at `1.4962` and `firm_radius` at `2.5`; only `search_cost_per_trip` (`a`) and `firm_kappa` are
currently in the ESTIMATED vector. `scripts/feasibility_screen.py::build_config()`'s varying-vs-
fixed fields are a DEVELOPMENT-SCREEN scenario grid, not an estimation specification -- conflating
the two was the error.

| Parameter | Current role | Value / range |
| --- | --- | --- |
| `search_cost_per_trip` (`a`) | ESTIMATED | admissible `[0.001, 0.02]` |
| `firm_kappa` | ESTIMATED | admissible `[0.2, 2.0]` |
| `initial_search_capital` | FIXED (approved) | `1.4962` |
| `firm_radius` | FIXED (approved) | `2.5` |
| `transport_cost_rate` (`b`) | FIXED (approved, primary scenario) | `0.000145` |
| `reentry_threshold` (`r`), `household_inflow` (`g`) | FIXED (baseline) | `0.035`, `0.008` |
| `phi` (this proposal) | **PROPOSED: FIXED/SCENARIO for a first development pass, NOT jointly estimated this batch** | candidate value `0.75`, satisfying Section 4.3 at all three target fares |

**If `phi` is later promoted to ESTIMATED, the candidate estimation vector has THREE entries (`a`,
`kappa`, `phi`), not five** -- the first version's error compounded here too (it implicitly treated
`g_s` as a fifth addition to an already-wrong four-parameter baseline).

## 7. Policy-budget accounting

### 7.1 Traveller-side identity and the transport-measurement/net-depletion split

For a trip under a transport-subsidy policy arm with rate `tau in [0,1]` (fraction of the gross
fare subsidised -- a targeting-rule choice, e.g. whole-fare vs. distance-component-only, that this
document leaves open, not decided here):

```
gross fare:            c_i
out-of-pocket cost:     c_i^{oop}(tau) = c_i * (1 - tau)
transport-subsidy payment (public): tau * c_i
identity:               c_i^{oop}(tau) + tau*c_i = c_i   (exact, for every tau)
```

**Distinguishing the transport MEASUREMENT target from NET RESOURCE DEPLETION, as instructed**: the
existing `transport_budget_share` moment (matched against NHTS, a no-subsidy-world survey) should
continue to be computed from the GROSS fare `c_i` (a measure of real trips actually taken/aggregate
mobility, comparable across arms and to the baseline target) -- NOT from the out-of-pocket residual,
which would understate a subsidy arm's real transport activity relative to the empirical target.
Meanwhile, `search_capital`'s own depletion (the budget-bound mechanics) uses `c_i^{oop}(tau)`, the
amount that actually leaves the agent's balance. These are two DIFFERENT computed quantities from
the same trip event, and must be kept named and reported separately -- not resolved automatically
by using one formula for both.

### 7.2 The transfer under a subsidy: proportional to out-of-pocket cost, not the gross fare

`h_i(tau) = phi * c_i^{oop}(tau)`. This has two consequences, both checked in
`search_capital_design_verification_2026-09-15.json`'s `7a_transport_subsidy_ledger_identity`
block, across `tau in {0, 0.25, 0.5, 1.0}`:

- **At `tau=1` (a fully-subsidised, free trip), `c_i^{oop}=0`, so `h_i=0` too** -- the household
  transfer scales down WITH the subsidy rather than stacking on top of a free trip. This is what
  rules out a "cheap/free-trip policy with continued trip-triggered funding" creating a NEW
  accumulation channel, the specific case `DESIGN_A_REVIEW.md` Section 6 asks to be assessed
  explicitly: net change per active month is `h_i - c_i^{oop} = phi*c_i^{oop} - c_i^{oop} =
  c_i^{oop}*(phi-1) <= 0` at EVERY `tau`, with equality (net change exactly ZERO, not positive)
  only in the limit `tau=1`.
- **This zero-net-change limit at full subsidy is an INTENDED policy effect, not a bug to prevent.**
  `DESIGN_A_REVIEW.md` Section 6 is explicit: "do not impose scarcity preservation on every policy
  arm merely to ensure the subsidy cannot eliminate a liquidity constraint -- relaxing such a
  constraint may be the policy's intended effect." A full transport subsidy is SUPPOSED to remove
  the transport-cost liquidity constraint on searching; that this design lets it do so CLEANLY (net
  change reaches exactly zero, never positive, so there is still no runaway accumulation even at
  full subsidy) is a property worth stating explicitly, not a concession.

### 7.3 Horizon / accumulation-regime treatment

Because net change per active month is `<=0` at every `tau in [0,1]` and every `phi<1` (Section
7.2), there is no unbounded-accumulation regime that needs different treatment across a finite
policy horizon versus a settled policy regime -- the bound holds identically either way. The
SEPARATE, already-open question of whether the development screen's own three reporting windows
constitute a settled regime (they are explicitly not claimed to) is unaffected by this design and
carried forward unchanged.

### 7.4 Who pays, and the equal-budget comparison

**`h` is proposed as a PRIVATE, household-level transfer** (consistent with the cited evidence's
own "intra-household resource reallocation" framing, Section 9), tracked SEPARATELY from any
PUBLIC policy budget. Consequence, stated as an accounting rule: the equal-PUBLIC-budget comparison
between a transport-subsidy arm and a wage-subsidy arm is UNAFFECTED by `h` -- `h` never enters
either arm's public ledger. Total PRIVATE transfer spend should be reported ALONGSIDE the public-
budget comparison as a descriptive quantity, not folded into the constraint the two policy arms are
compared under.

**A common rule, a different realised total, stated as an equation**: `Total_h(arm) = h_i * (number
of eligible U agent-months in that arm)`. The RULE (`phi`, the eligibility condition) is identical
across arms; the REALISED total differs because policy changes hiring/search dynamics and therefore
the number of eligible trip-months. Illustrated with a toy, clearly-labelled (NOT simulated)
example in `search_capital_design_verification_2026-09-15.json`'s `7b_illustrative_policy_arm_
total_h_payment` block: three toy eligible-month counts (1000/1400/1250) at the same per-trip `h`
produce three different totals, by construction.

**Public wage-subsidy budget, prospective only**: no wage-subsidy payment mechanism currently
exists in the codebase (confirmed: no transport- or wage-subsidy LEDGER is implemented anywhere in
`src/`). A wage subsidy, under the CURRENT frozen-employed-capital convention, has no channel into
`search_capital` unless a future implementation explicitly chooses to top up capital at hire -- a
separate, unresolved design question, independent of `phi`, not addressed by this proposal. Its
public-budget equation (a per-hire or per-employed-month payment to firms) is left as a placeholder
for whichever future batch actually implements that arm, not invented here.

**Symmetry preserved**: `phi` is proposed as a baseline financing-realism parameter, held IDENTICAL
across the control arm and every policy arm -- never itself a policy lever. `model.
paired_separation_draw` and `_shock_rng` (the existing exogenous-shock pairing design) are
untouched by this proposal.

## 8. Identification, re-stated against the corrected fixed/estimated table

`phi` primarily affects the same duration-related moments that `search_cost_per_trip` already
affects, through the same affordability channel (Section 4.3's `c-h` net-drain term) -- likely
STRONGLY COLLINEAR with `a` in any joint fit to a single duration-share moment. **Per the review's
correction**: a one-at-a-time `phi` sweep (varying `phi` alone, holding `a`/`kappa` fixed) measures
SENSITIVITY only -- it cannot by itself establish separate identification from `a` and `kappa`. A
genuine identification assessment would need a JOINT, SCALED moment Jacobian or profile-likelihood
exercise over the WHOLE proposed target vector (including the transport moments, which may carry
information that helps separate a gross-fare parameter from a financing parameter, since transport
spend is measured from the GROSS fare while duration is affected by the NET, `phi`-adjusted
depletion) -- not demonstrated here, and not promised as a result before it is actually
demonstrated. This is specified as the NEXT diagnostic step (Section 11), not performed this batch.

## 9. Source-to-assumption table, corrected

| Assumption / mechanism | Evidence for the CHANNEL | Evidence for the FUNCTIONAL FORM or numeric strength |
| --- | --- | --- |
| Liquidity/resource constraints materially affect job-search behaviour, and are eased by transfers | Köhler, Stanwix and Bhorat, WIDER Working Paper 19/2026, "Cash transfers and labour supply under structural unemployment" (UNU-WIDER, DOI 10.35188/UNU-WIDER/2026/696-4): grant receipt raises job search, business-start attempts and employment in the short run; loss produces larger, persistent negative effects; effects run through eased liquidity/insurance constraints | NONE. The paper studies an UNCONDITIONAL transfer, not one contingent on this month's trip-taking. It supports the CHANNEL (liquidity constraints matter), not the effort-contingent ELIGIBILITY RULE this design proposes, and not `phi`'s value. **This gap is the design's main under-evidenced assumption (Section 5), not resolved by this table.** |
| Household resource reallocation (spillovers) exists but full pooling is not assumed | Same source: documents intra-household reallocation shaping labour-market behaviour | NONE -- motivates treating `h` as a PRIVATE, household-level transfer (Section 7.4), not a full household-pooling model |
| Cash-transfer receipt does not reliably produce SUSTAINED employment gains on its own | Same source: "the positive effects of receipt are short-lived and do not translate into sustained employment gains" | Tempers any expectation that `phi` alone would produce a well-FITTED k=0 target even where it makes one structurally reachable (Section 4.3's necessary-not-sufficient caveat) |
| Transport is a real, binding, institutionally documented search cost in South Africa | Banerjee and Sequeira (2023), already the project's own anchor for `search_cost_per_trip`/`transport_cost_rate` | Numeric anchor already in use; not re-derived here |
| UIF-style time-limited, wage-linked, declining post-separation benefits are a real SA institution | General institutional fact (South Africa's Unemployment Insurance Fund) | NOT numerically specified -- would need the Unemployment Insurance Act's schedule as a primary source; unconsulted (Design B, Section 10.2) |
| Wage income during employment does not feed back into `search_capital` | Existing project convention (already disclosed in the draft as the "initial-capital bound" limitation) | Preserved, not re-examined, by this design |

## 10. Recommendation

### 10.1 Design A (corrected): explicitly stylised sensitivity, NOT a primary baseline

The corrected, proportional design (`h_i = phi*c_i^{oop}`, trip-activity eligibility, `phi=0.75`)
is now INTERNALLY CONSISTENT and passes every standalone ledger check run for it (Section 4-7,
`verify_design_a_ledger_2026-09-15.py`). It is NOT recommended as a primary baseline financing rule
for three reasons, weighed explicitly:

1. **The effort-contingent eligibility rule is an additional, not-directly-evidenced assumption**
   (Section 5, Section 9) -- the cited evidence supports the liquidity CHANNEL, not this specific
   ELIGIBILITY RULE.
2. **Identification is unresolved** (Section 8) -- `phi`'s separate identifiability from `a` and
   `kappa` has not been demonstrated, only proposed as a future check.
3. **Structural feasibility is not empirical feasibility** (Section 4.3's caveat) -- whether
   agents' actual, endogenous trip-taking would realise a plausible, well-behaved k=0 duration
   distribution under this design is untested; no development-scale run was performed this batch.

**Recommendation: treat the corrected Design A as an explicitly stylised sensitivity specification
-- well-specified and ready for a bounded, EMPIRICAL development-scale check in a future batch, not
folded into the primary calibration baseline, and not yet grounds to abandon the narrower-thesis
fallback (Section 12) either.** This is not a request to keep inventing variants until a nonzero
duration statistic appears -- it is a report that the mathematics is now sound, paired with an
explicit list of what remains unproven before it could be adopted as anything more than a
sensitivity check.

### 10.2 Design B: not a safe fallback, a newly-identified defect, not merely less parsimonious

**CORRECTED 2026-09-15 (second pass), per `DESIGN_A_REVIEW.md`'s closing section**: the first
version treated Design B (a UIF-style decaying post-separation benefit) as a parsimony-costly but
otherwise safe alternative. Two problems, not previously identified, mean it is not currently a
safe fallback at all:

1. **"Post-separation" eligibility cannot actually be read off `months_jobless` alone.** That clock
   also accrues for agents who started the simulation already unemployed (never separated from an
   actual job in this run) -- calling the resulting benefit "post-separation" while paying it to
   agents who never separated is a conceptual mismatch, not merely a labelling nicety.
2. **Replacing ALL hard-`DISCOURAGED` inflow with a benefit that EXPIRES (`b(\cdot)=0` once
   `months_jobless >= D_max`) can make hard discouragement ABSORBING** for an agent whose balance
   is still below the re-entry/affordability threshold when the benefit runs out -- unlike the
   baseline's `g`, which never expires, such an agent would receive NO further inflow, ever, under
   Design B as originally specified. This is a genuine structural defect, not a parsimony
   trade-off, and Design B is NOT recommended, as either a baseline or a sensitivity, until this is
   repaired (e.g. by retaining a non-expiring floor alongside any decaying top-up) -- a repair not
   attempted here, consistent with not inventing a new variant to chase a result.

Design B therefore drops out of consideration entirely for this batch, not merely ranked below
Design A.

## 11. Bounded implementation/verification plan (NOT executed this batch)

If and when Aakash authorises a development-scale empirical check of the corrected Design A:

1. **Config field**: add `search_subsistence_fraction: float = 0.0` (i.e. `phi`, defaulting to
   `0.0` -- exactly today's behaviour) to `src/config.py`.
2. **Mechanism**: within `JobSeeker.step_searching()` (`src/agents.py`), AFTER the existing trip
   payment (`self.search_capital -= self.trips_this_step * self.cost_per_trip`) and only if
   `self.trips_this_step >= 1`: `self.search_capital += phi * self.trips_this_step_cost` where the
   cost used is `n_{i,t} * c_i^{oop}`'s PER-ACTIVE-MONTH (not per-trip) cost basis -- i.e. `h_i =
   phi * c_i` charged once per active month, exactly as worked in Section 2's event (e). Under a
   transport-subsidy arm, `c_i` in this formula is that arm's OUT-OF-POCKET cost (Section 7.2), not
   the gross fare.
3. **Tests, before any run** (mirroring `tests/test_model.py`'s existing budget-bound test
   pattern): (a) a unit test reproducing each of Section 2.1's five worked events exactly; (b) a
   deterministic fixture reproducing Section 4.3's 13-month affordability path end-to-end through
   the real `CityModel.step()`/`.run()`, at `phi=0.75`; (c) a companion fixture at `phi>=1`
   (deliberately inadmissible) demonstrating the scarcity-removal pathology occurs exactly as
   predicted, so the `phi<1` constraint's necessity is demonstrated, not merely claimed; (d) a
   multi-trip fixture confirming `n=2`/`n=3` active months deplete capital, per Section 5's
   invariant.
4. **A new development-scale screen** (reusing `scripts/feasibility_screen.py`'s structure, a
   small `phi` grid crossed with the existing `a`/`firm_kappa` grid at the same 3 development
   seeds) BEFORE any validation-scale or held-out run -- checks whether the structural feasibility
   proven here translates into nonzero, plausible simulated k=0 shares under agents' real,
   endogenous trip-taking.
5. **A joint identification assessment** (Section 8) BEFORE any future recalibration attempt --
   NOT a one-at-a-time sweep alone.
6. Only after 1-5 would recalibration, held-out validation, or a policy campaign be in scope --
   each remains under its own standing hold.

## 12. Narrower-thesis fallback (unchanged from the first version)

If a future development-scale check shows even a structurally-feasible `phi` does not produce a
plausible, well-behaved k=0 duration distribution, or the identification concern (Section 8) cannot
be resolved within the remaining project timeline, the fallback in `REVIEW_AND_RECOMMENDATION.md`
applies: narrow the thesis to a stylised transport-vs-wage-subsidy mechanism comparison, and move
the long-term-unemployment duration target to a failed external diagnostic rather than a
calibration target. Recorded as an available fallback, not triggered here, and not something this
design proposal's own mathematical consistency is grounds to bypass.

## 13. Internal review of this corrected document

Every equation above was re-derived independently from the model's own, unchanged step order, not
copied from the review and modified -- and then CROSS-CHECKED against an independently-executed
standalone script (`verify_design_a_ledger_2026-09-15.py`, run this pass, output committed as
`search_capital_design_verification_2026-09-15.json`): the script's own reproduction of the
review's ORIGINAL failing example (month 11, matching the review's `verification.json` exactly)
confirms this document's ledger arithmetic agrees with the review's BEFORE extending it to the
proportional design; the `required_phi` values in Section 4.3 are read directly from the script's
output, not retyped by hand; the multi-trip, actual-fare-domain, and policy-budget-identity checks
(Sections 5, 7) are all assertion-backed in the script, not merely claimed in prose. The Design-B
absorption defect (Section 10.2) was identified by explicitly tracing what happens to an agent
whose balance never crosses the re-entry threshold before `D_max`, not assumed safe because the
first version had called it "not rejected outright." The effort-contingent-assumption gap (Section
5, Section 9) is stated as an open gap, not closed by re-labelling it -- no claim in this document
asserts the corrected design is proven correct, only that it is now internally consistent and its
remaining open questions are named precisely enough for Aakash's actual decision (Section 10.1) to
be about the economic assumption and the empirical check still needed, not about arithmetic errors.
