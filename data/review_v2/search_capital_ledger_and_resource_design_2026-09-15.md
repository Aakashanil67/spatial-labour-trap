# Search-capital ledger and a bounded Option-C resource-design investigation

15 September 2026. Written per Aakash's instruction, following `REVIEW_AND_RECOMMENDATION.md`'s
recommendation: choose Option C (examine whether the model's financing of search is economically
defensible) as a bounded DESIGN INVESTIGATION, not an implementation. **Nothing in this document
changes `src/`, `configs/`, or any canonical target. No new simulation was run to produce it** --
every quantitative claim below is either (a) closed-form algebra over the model's own,
already-verified transition rules, or (b) drawn from the already-committed
`feasibility_screen_2026-09-15.csv` and the budget-bound derivation
(`data/review_v2/replenished_capital_budget_bound.md`), both unchanged. The current model and its
budget-bound finding are preserved throughout, not contradicted or worked around.

## 1. `search_capital`, defined precisely

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

This is closer to a ring-fenced "job-search allowance" than to a wealth stock. The object choice
matters for what follows: a design that reinterprets `search_capital` as literal savings would
need to explain why it never earns interest and is never spent on anything but transport; a design
that keeps it as a search-earmarked allowance (as below) only needs to ask what REPLENISHES that
specific allowance, and when.

## 2. The baseline cash-flow ledger, across every state and sub-category

Let `k_{i,t}` be agent `i`'s `search_capital` entering step `t` (i.e. after step `t-1`'s flows),
`c_i = search_cost_per_trip + transport_cost_rate * distance_to_cbd_i` (the agent's own,
time-invariant cost per trip), `n_{i,t}` the number of trips it pays for this step (from
`decide_trips()`, bounded above by `floor(k_{i,t} / c_i)` -- an agent cannot borrow), `g =
household_inflow`, `r = reentry_threshold`. The model has three STATES (`SEARCHING`, `EMPLOYED`,
`DISCOURAGED`), and the observation layer's E/U/D reporting further splits `SEARCHING` into two
sub-categories by this step's trip decision -- `U` (`n_{i,t} >= 1`) and `D`-soft/belief-inactive
(`n_{i,t} = 0`, `belief_inactive_this_step = True`). **These are OBSERVATION categories, not model
states** -- both are the same underlying `SeekerState.SEARCHING`, and this distinction is exactly
what Section 3 below examines.

| Category | Model state | Financing this step | Spending this step | `k_{i,t+1}` |
| --- | --- | --- | --- | --- |
| E (employed) | `EMPLOYED` | none | none | `k_{i,t}` (frozen) |
| U (active search) | `SEARCHING`, `n_{i,t}>=1` | none | `n_{i,t} * c_i` | `k_{i,t} - n_{i,t} c_i` |
| D-soft (belief-inactive) | `SEARCHING`, `n_{i,t}=0` | none | none | `k_{i,t}` (static) |
| D-hard (discouraged) | `DISCOURAGED` | `g` | none | `k_{i,t} + g`, state flips to `SEARCHING` if `>= r` |

**Timing, exactly as `CityModel.step()` orders it** (`src/model.py`): (1) separations
(`EMPLOYED->SEARCHING`); (2) re-entry (`DISCOURAGED` capital += `g`, then flips to `SEARCHING` if
`>=r`); (3) capital-exhaustion check (a `SEARCHING` agent that cannot afford even one trip, using
capital as it stands after step 2, becomes `DISCOURAGED`, capital untouched at the transition);
(4) `u_t`/`v_t`/`l_t`/`disc_t` stocks recorded; (5) `months_jobless` credited; (6) trip decision
and payment; (7) matching -- an agent hired this step already paid for and used its own trip(s)
this same step (search cost is a real, incurred cost of the very step in which a hire happens, not
waived), then its capital freezes from that point on.

**What persists across a state transition**: hiring freezes whatever capital an agent held after
that step's own trip payment (Row "U"/E in the table); separation hands that SAME, frozen value
back into `SEARCHING`, unchanged by however long the employment spell lasted. A newly-separated
agent with 20 months of employment behind it re-enters search with EXACTLY the capital it had on
its hire day -- no more, no less. This is a deliberate simplification already disclosed in the
draft as the "initial-capital bound" limitation, and it is preserved, not solved, by either design
below (Section 5).

**A previously under-examined case, surfaced by this ledger**: the D-soft (belief-inactive) row.
An agent here is capital-SOLVENT (it passed the step-3 exhaustion check, so it could afford a
trip) but chose zero trips this step; its capital is exactly static -- no income, no spending. It
is reported as `D` in the E/U/D layer (alongside hard-`DISCOURAGED`) but is NOT accumulating
toward re-entry via `g` (it is not in the hard-`DISCOURAGED` state) and is not depleting either.
This population sits in a genuine third limbo the existing financing rules do not address at all,
distinct from both "actively searching and spending" and "capital-exhausted and recovering."

## 3. The paid-trip-to-active-search mapping, checked

`scripts/observation_layer.py::classify_observation()` defines `U` as: `SEARCHING` AND
`trips_this_step >= 1`. **Because the model has exactly one search action (paying for a trip),
this mapping is EXACT, not an approximation, as a description of the model's own internal
mechanism** -- there is no other channel through which a `JobSeeker` can search, so "made a paid
trip" and "the model's only form of search activity this step" are the same statement by
construction. Verified directly: `decide_trips()`'s only output is a trip count; no other agent
method represents effort.

**The assumption is exposed, not inside the model, but at the point this `U` category is compared
against QLFS's own "actively searching in the last four weeks" definition.** Real job seekers have
search channels that do not require a paid outbound trip -- phone calls, online applications,
asking contacts, a walk-in application within an already-planned commute -- some or all of which
QLFS would count as active search without necessarily showing up as `trips_this_step >= 1` here.
The mapping is therefore a STRICT SUBSET relationship, not a two-way equivalence: every model-`U`
month plausibly corresponds to real active search, but the model has no channel to represent real
active search that does not cost a modelled trip. This means the model's `U` stock -- and every
clock built on it, including k=0 -- is structurally biased toward UNDER-counting active search
relative to QLFS whenever real search includes a free or already-sunk-cost channel the model
cannot represent.

**Why this is checked here rather than fixed here**: it bears directly on how the resource-design
question should be read. A cash-strapped agent who cannot afford a modelled trip this month is
reclassified `D` here even in a world where the SAME agent would report actively searching to QLFS
via a free channel. Raising `search_capital`'s financing (Sections 4-5) would let more agents
literally AFFORD a trip and so cross back into `U` -- but it does not address agents who are
capital-CONSTRAINED on the trip margin specifically while still being active on a margin this
model has no channel for. **Per instruction, this is disclosed as a genuine, separate limitation,
not folded into a resource-design fix**: adding a free-search channel, switching the clock, or
redefining `U`/`D` boundaries would be an unannounced change to the target definition, prohibited
this batch. `k=0` remains the current comparison convention, and the mapping above remains a
transparent MODELLING CHOICE, not a claim that QLFS respondents themselves apply a zero-tolerance,
trip-gated rule -- exactly the distinction `REVIEW_AND_NEXT_BATCH.md`'s own k=0 recommendation
drew, and which this document does not blur.

## 4. Two parsimonious resource alternatives

Both alternatives leave `search_capital`'s definition (Section 1), the trip-cost mechanism, the
`U`/`D` observation mapping (Section 3), and the hard-`DISCOURAGED` re-entry mechanics untouched
except where explicitly stated. Neither adds free search, a consumption/savings model, or a new
agent state.

### Design A -- a search-linked subsistence transfer during active months

**One new parameter**: `g_s` (search subsistence rate), a flat top-up credited on any step an
agent is classified `U` (made at least one paid trip), in ADDITION to and financed separately from
the existing `g` (which continues to apply, unchanged, only in hard `DISCOURAGED`).

**Economic role, stated explicitly**: `g_s` represents household or informal-network resources
(family transfers, shared income, social support) that continue to flow to a job seeker SPECIFICALLY
WHILE it is making the effort of actively searching -- distinct from `g`, which represents a
larger household/safety-net response that arrives once a member has stopped even trying. This
tracks Köhler, Stanwix and Bhorat's finding (Section 7) that receipt of an unconditional cash
transfer raises search activity in the SHORT run, and that LOSING it produces large, persistent
negative effects on search-related behaviour -- i.e. the relevant channel in that evidence is
active while a person IS searching, not gated on having given up.

**Deliberately excludes the D-soft (belief-inactive) row.** `g_s` is paid only on a `U` step (a
trip actually made), not merely for holding `SEARCHING` status while making zero trips. This keeps
the change tightly scoped to the literal instruction ("funding available during ACTIVE
unemployment") and, as shown below, avoids a genuine accumulation pathology that including D-soft
would introduce.

**Revised ledger** (only the U row changes from Section 2):

| Category | `k_{i,t+1}` |
| --- | --- |
| E | `k_{i,t}` (unchanged) |
| U | `k_{i,t} - n_{i,t} c_i + g_s` |
| D-soft | `k_{i,t}` (unchanged) |
| D-hard | `k_{i,t} + g` (unchanged) |

**Design constraint, proposed as part of the specification, not a fitted value**: `0 <= g_s <
min(c_i)` over the admissible `search_cost_per_trip` range -- i.e. the subsistence transfer must
never fully cover even the cheapest trip. This is what keeps net spending negative on any month
with at least one trip, preserving scarcity by construction rather than by accident (worked in
Section 6).

### Design B -- a post-separation transitional benefit (UIF-style, time-limited, decaying)

**Three new parameters**: a replacement rate `rho` (fraction of `WAGE` paid initially), a decay
factor `delta` in `(0, 1]` (multiplicative per-month decline), and a duration cap `D_max` (months
after which the benefit is exhausted). No new agent-level state is needed -- the model already
tracks exactly the right clock: `months_jobless` (increments every non-employed step, resets to 0
only at `resolve_hire()`, survives `DISCOURAGED`<->`SEARCHING` cycling -- verified in
`src/model.py`'s step-5 block and `src/agents.py::resolve_hire()`).

**Economic role**: this represents South Africa's actual Unemployment Insurance Fund (UIF), a
real, institutionally documented wage-linked benefit paid to recently-separated contributors for a
limited period, at a declining rate. **This document does NOT propose numeric values for `rho`,
`delta`, or `D_max`** -- the UIF's actual benefit schedule is set in the Unemployment Insurance
Act and its regulations, a primary source not consulted for this design investigation; inventing
plausible-sounding numbers here would misrepresent them as evidence-based when they are not.

**Benefit function**: `b(months\_jobless) = rho * WAGE * delta^{months\_jobless}` for
`months_jobless < D_max`, else `0`. Applied to EVERY non-employed category (U, D-soft, D-hard)
uniformly, replacing `g` entirely -- UIF payments are not conditioned on this month's search
effort, so gating this benefit on trip-taking would misrepresent the institution it is modelled
on.

**Revised ledger**:

| Category | `k_{i,t+1}` |
| --- | --- |
| E | `k_{i,t}` (unchanged) |
| U | `k_{i,t} - n_{i,t} c_i + b(\text{months\_jobless}_{i,t})` |
| D-soft | `k_{i,t} + b(\text{months\_jobless}_{i,t})` |
| D-hard | `k_{i,t} + b(\text{months\_jobless}_{i,t})` (replaces `g`) |

Re-entry rule for D-hard becomes `k_{i,t} + b(\cdot) >= r`.

### Why not both, and why not a household/consumption model

Combining A and B, or building a joint household-consumption layer (income pooling across
co-resident members, endogenous savings, etc. -- exactly what the Köhler/Stanwix/Bhorat paper's
"spillover effects" section documents happening in the real economy) is NOT proposed. The
instruction is explicit that a full household model should not be added unless demonstrably
necessary, and neither the budget-bound finding nor the development screen demonstrates that a
single new financing channel is insufficient to investigate the question -- that would need to be
established by actually testing one design first, which is exactly what implementation (out of
scope this batch) would do.

## 5. Recommendation: Design A, with equations, justification, and the identification/policy
## consequences of Design B set out for comparison

**Recommended: Design A.** Reasons, weighed explicitly rather than asserted:

- **Parsimony.** One new parameter against Design B's three. The current estimable set is already
  `{search_cost_per_trip, firm_kappa, initial_search_capital, firm_radius}` (4 parameters,
  confirmed from `scripts/feasibility_screen.py::build_config()`'s fixed-vs-varied fields) against
  a small canonical+new moment set; adding three more free parameters with no dedicated target
  moment (Design B) risks under-identification in a way one parameter does not.
- **It extends, rather than replaces, the already-verified budget bound's own functional form**
  (worked below) -- Design B's time-varying benefit breaks the bound's simple closed form entirely
  and would need a new derivation from scratch.
- **No invented numeric institutional parameters.** Design B's `rho`/`delta`/`D_max` would need a
  primary source (the UIF Act's schedule) this investigation did not consult; Design A needs no
  external numeric anchor beyond the constraint below, which is a modelling admissibility bound,
  not a claimed real-world number.
- **Design B is not rejected outright** -- it is a better institutional match to the ASYMMETRIC
  receipt/loss finding in the cited evidence (Section 7), and is recorded as the fallback if Design
  A proves insufficient at a future implementation stage. It is not implemented or adopted here.

### 5.1 Equations and worked affordability paths (Design A)

Re-derive the budget bound's re-entry consequence under Design A. The hard-`DISCOURAGED` ledger is
UNCHANGED, so the re-entry bound from `replenished_capital_budget_bound.md` is UNCHANGED: capital
on re-entry into `SEARCHING` is still bounded above by `max(r, c) + g`.

**What changes is what happens AFTER re-entry.** For a continuously active agent (`n_{i,t}=1`
every month, the cheapest sustained path), net capital change per active month is `g_s - c` (one
trip paid, one subsistence credit). Sustaining 13 consecutive active months from a starting
balance `x < max(r,c)+g` requires `x + 13(g_s - c) >= c` at every intermediate month, which -- since
`g_s < c` by the design constraint (net still negative each month, monotonically decreasing) --
reduces to the single binding check at month 13: **feasible only if `13(c - g_s) <= max(r,c)+g`**,
i.e.

```
g_s >= c - (max(r,c) + g) / 13
```

Using the already-approved baseline `r=0.035`, `g=0.008` (`max(r,c)+g = 0.043` for every fare in
the admissible `search_cost_per_trip` range `[0.001, 0.02]`, since that whole range is below `r`):

```
g_s_required(c) = c - 0.0033077
```

-- exactly the SAME `0.0033077` cutoff the original budget bound derived (the fare below which the
inequality is already satisfied at `g_s=0`). At the three target-compatible fare candidates:

| fare `c` | `g_s` required to flip the 13-month inequality | `g_s` vs. `c` (constraint check) |
| --- | ---: | --- |
| 0.005665 (double-`b` central) | 0.002357 | `< c` -- satisfies `g_s<c` automatically |
| 0.007405 (primary-`b` central) | 0.004097 | `< c` -- satisfies `g_s<c` automatically |
| 0.009145 (`b=0` central) | 0.005837 | `< c` -- satisfies `g_s<c` automatically |

**This is algebra, not a simulation result, and it proves exactly one thing: that a `g_s` in this
range removes the STRUCTURAL impossibility of a 13-consecutive-active-month spell from a fresh
re-entry balance.** It does NOT prove that agents' actual, endogenous trip-taking behaviour
(`decide_trips()`'s intensity margin, itself a function of the perceived hire rate) would ever
realise such a spell, nor that the resulting simulated k=0 share would be well-fitted, nor that
this is a "successful calibration" in any sense -- satisfying the inequality is necessary in the
relevant paths, not sufficient for a good model, exactly as instructed.

### 5.2 Pathology checks, worked explicitly

- **Unlimited resource accumulation?** No. Every U-month nets `g_s - c < 0` by the design
  constraint -- capital strictly decreases on any month with at least one paid trip, with no
  accumulation channel introduced on active months. D-soft is deliberately excluded from `g_s`
  (Section 4), so no channel exists for an agent to accumulate capital indefinitely by remaining
  nominally `SEARCHING` while making zero trips -- ruling out the specific runaway pathway a
  D-soft-inclusive variant would have introduced (considered and rejected during this
  investigation for exactly this reason).
- **Discouragement made absorbing?** No. Hard-`DISCOURAGED` dynamics (`+g`, re-entry at `r`) are
  completely untouched by Design A.
- **Scarcity removed entirely?** No, PROVIDED the design constraint `g_s < min(c_i)` holds. This is
  a proposed constraint on any future parameter choice, not a proof that it will always be
  respected -- if a future calibration or an unexamined default ever set `g_s >= c` at some
  admissible fare, scarcity WOULD be removed at that fare (a continuously active agent's capital
  would never decrease). This must be checked explicitly whenever `g_s` or the fare range changes,
  not assumed.
- **Free search?** No. The trip-cost mechanism is completely unchanged; `g_s` finances trips, it
  does not waive their cost or create a costless search channel.

## 6. Identification and policy consequences

**Estimable-parameter interaction.** `g_s` primarily affects the SAME duration-related moments
(the k-family long-term shares) that `search_cost_per_trip` already affects, through the same
affordability channel (Section 5.1's `c - g_s` net-drain term). This makes `g_s` likely to be
STRONGLY COLLINEAR with `search_cost_per_trip` in any joint fit to a single duration-share moment
-- raising both together can leave the net affordability roughly unchanged, so a single k=0 share
target is unlikely to separately pin down both. Before any future calibration attempts to estimate
`g_s`, a sensitivity/profile check (varying `g_s` alone, holding the other four parameters fixed,
and reading off which moments move and by how much) is the appropriate next diagnostic step -- not
performed here, consistent with the hold on recalibration. A moment sensitive to the SHAPE of the
duration distribution (not just one threshold share) is the more plausible candidate for helping
separate a flat monthly subsidy (which shifts the whole distribution roughly uniformly) from a
trip-cost change (which rescales affordability); this is flagged as an open identification
question, not resolved here.

**Policy-arm symmetry.** No transport-subsidy or wage-subsidy payment ledger currently exists in
the codebase (the halved transport-rate file referenced in prior planning is not an actual
payment/budget system). `g_s` is proposed as a BASELINE financing-realism correction, applied
IDENTICALLY across the control arm and any future policy arm -- it is not itself a policy lever,
and must not be tuned differently across arms, per the standing instruction to treat modelling
changes symmetrically across policy arms and preserve the existing exogenous-shock pairing design
(`model.paired_separation_draw`, `_shock_rng`, both untouched by this proposal).

**A first-order interaction worth flagging for any future transport-subsidy design**: a transport
subsidy lowers `c_i` for eligible agents. Under Design A, the scarcity-preserving constraint is
`g_s < c_i`, evaluated PER AGENT at their own current (possibly subsidised) cost -- a subsidy
large enough to push a treated agent's `c_i` below `g_s` would remove scarcity for exactly that
treated subgroup, an effect that would need checking against the subsidised cost, not the baseline
fare, once such a policy arm exists. A wage subsidy, under the current frozen-employed-capital
convention, has no direct channel into `search_capital` at all unless a future implementation
explicitly chooses to top up capital at hire -- a separate, unresolved design question, independent
of `g_s`, not addressed by this proposal.

## 7. Source-to-assumption table

| Assumption / mechanism | Evidence for the CHANNEL | Evidence for the FUNCTIONAL FORM or numeric strength |
| --- | --- | --- |
| Liquidity/resource constraints materially affect job-search behaviour, and are eased by transfers | Köhler, Stanwix and Bhorat, WIDER Working Paper 19/2026, "Cash transfers and labour supply under structural unemployment" (UNU-WIDER, DOI 10.35188/UNU-WIDER/2026/696-4): grant receipt raises job search, business-start attempts and employment in the short run; loss produces larger, persistent negative effects; effects run through eased liquidity/insurance constraints, not childcare | NONE. The paper does not specify a functional form linking transfer size to trip-taking or to any model equation; it is evidence for the CHANNEL Design A represents, not for `g_s`'s value or shape. Explicitly not treated as such here. |
| Household resource reallocation (spillovers) exists but full pooling is not assumed | Same source: documents intra-household reallocation shaping labour-market behaviour | NONE -- this is why a full household-pooling model is NOT built (Section 4, "why not both") |
| Cash-transfer receipt does not reliably produce SUSTAINED employment gains on its own | Same source: "the positive effects of receipt are short-lived and do not translate into sustained employment gains" | Tempers any expectation that adding `g_s` alone would produce a well-FITTED k=0 target even if it makes one structurally reachable (Section 5.1's necessary-not-sufficient caveat) |
| Transport is a real, binding, institutionally documented search cost in South Africa | Banerjee and Sequeira (2023), already the project's own anchor for `search_cost_per_trip`/`transport_cost_rate` (`configs/baseline.yaml`) | Numeric anchor already in use; not re-derived here |
| UIF-style time-limited, wage-linked, declining post-separation benefits are a real SA institution | General institutional fact (South Africa's Unemployment Insurance Fund) | NOT numerically specified here -- would require the Unemployment Insurance Act's schedule as a primary source before any `rho`/`delta`/`D_max` value is proposed; explicitly flagged as unconsulted (Design B) |
| Wage income during employment does not feed back into `search_capital` | Existing project convention (already disclosed in the draft as the "initial-capital bound" limitation) | Preserved, not re-examined, by either design in this document |

## 8. Bounded implementation/verification plan (NOT executed this batch)

For Design A, if and when Aakash authorises implementation:

1. **Config field**: add `search_subsistence_rate: float = 0.0` to `src/config.py` (defaulting to
   `0.0`, i.e. exactly today's behaviour -- a config addition, not a behaviour change, until a
   nonzero value is deliberately chosen).
2. **Mechanism**: one line in `JobSeeker.step_searching()` (`src/agents.py`), crediting `g_s` to
   `search_capital` only when `trips_this_step >= 1` is determined for THIS step -- requires
   care about ordering relative to the existing capital-exhaustion check (step 3 of
   `CityModel.step()`), which runs BEFORE `step_searching()` (step 6); `g_s` must be credited
   AFTER the trip is paid for within `step_searching()`, not before, so it cannot retroactively
   change this step's own affordability check.
3. **Tests, before any run**: (a) a direct unit test asserting the per-step ledger matches Section
   2's table exactly for one U-month, one D-soft month, one E month, holding `g_s` fixed; (b) a
   deterministic fixture reproducing Section 5.1's 13-month worked path end-to-end through the
   real `CityModel.step()`/`.run()` (mirroring `tests/test_model.py`'s existing
   `test_reentry_bound_reproduces_end_to_end_through_the_real_model_step` pattern), at a `g_s`
   value satisfying the design constraint, confirming the affordability inequality is REACHED
   (not merely asserted algebraically); (c) a companion fixture with `g_s >= c` (a deliberately
   INADMISSIBLE choice) demonstrating the scarcity-removal pathology occurs exactly as predicted,
   so the design constraint's necessity is demonstrated, not merely claimed.
4. **A NEW development-scale screen** (reusing `scripts/feasibility_screen.py`'s existing
   structure, a small `g_s` grid crossed with the existing `a`/`firm_kappa` grid at the SAME 3
   development seeds) BEFORE any validation-scale or held-out run, to check whether the
   structural feasibility this document proves actually translates into nonzero simulated k=0
   shares under agents' real, endogenous trip-taking behaviour -- exactly the "necessary, not
   sufficient" caveat from Section 5.1, checked empirically rather than left as algebra.
5. **Sensitivity/profile check** (Section 6) BEFORE any recalibration attempt: vary `g_s` alone
   over a small grid, holding the other four estimable parameters fixed, and record which moments
   move and by how much -- informs whether `g_s` is separately identifiable before it is added to
   an estimation target set.
6. Only after 1-5 would recalibration, held-out validation, or a policy campaign be in scope --
   each remains under its own standing hold, unaffected by this plan existing.

## 9. Narrower-thesis fallback, if neither design proves defensible within an Honours-project scope

If a future development-scale check (implementation step 4 above) shows that even a
structurally-feasible `g_s` does not produce a plausible, well-behaved k=0 duration distribution --
or that the identification concern in Section 6 cannot be resolved with the currently-targeted
moment set within the remaining project timeline -- the fallback set out in
`REVIEW_AND_RECOMMENDATION.md` applies: explicitly narrow the thesis to a stylised
transport-vs-wage-subsidy MECHANISM comparison, and move the long-term-unemployment duration
target to a FAILED EXTERNAL DIAGNOSTIC (reported and discussed, not silently dropped) rather than a
calibration target the model is expected to fit. This would require reassessing the identification
and policy-claim scope of the whole thesis (which parameters remain estimable without the duration
moment's discipline, and what the transport/wage-subsidy comparison can and cannot claim without
it) -- a genuinely separate, larger decision, not something this document resolves or recommends
pre-emptively. It is recorded here as the fallback it is, not as permission to discard the duration
target silently if a design investigation happens to be inconvenient.

## 10. Internal review of this document

Before delivery, this document was checked against the same standard applied to the corrected
assessment: every equation in Section 5.1 was re-derived independently from the (unchanged) budget
bound rather than copied and modified; the `0.0033077` cutoff's reappearance was verified as a
consequence of `max(r,c)+g` being constant across the whole admissible fare range (all candidate
fares are below `r=0.035`), not asserted; the WIDER paper's abstract was read directly (not
inferred from the review's summary) before being cited, and is cited only for the channel it
actually documents, not for any functional form or number it does not provide; the D-soft
exclusion from Design A was arrived at by explicitly identifying and then closing the
unlimited-accumulation pathway a D-soft-inclusive variant would have opened (Section 5.2), not
because it was assumed safe. No new parameter, equation, or claim here is presented as evidence of
a working design -- only as a specification with its consequences worked through, pending Aakash's
decision on whether to authorise implementation.
