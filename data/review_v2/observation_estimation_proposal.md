# One coherent observation and estimation proposal

**AMENDED 2026-09-15: see `approved_specification_2026-09-15.md` for the APPROVED
specification -- Astra's `COMPLETION_REVIEW.md` found contradictions in this document's
Section 3 (no named primary clock), Section 5 (fare-anchor equation contradicted itself), and
Section 7 (`initial_search_capital` role contradicted the recorded G1 decision), each now
resolved. This document's Sections 1, 2, 4 (formula/mapping substance) and 6 remain valid and
are carried forward; Sections 3, 5 and 7 below are SUPERSEDED by the approved document and
kept here only for their still-useful supporting evidence/reasoning, not as the current
specification.**

15 September 2026. Written in response to Astra's `REVIEW_FOLLOWUP.md` deliverable 1.
**These are recommendations for Aakash's approval, not adopted decisions.** No canonical
target in `data/moments.csv` or `configs/baseline.yaml` is changed by this document, and no
code in `src/` is edited here. Where a recommendation would touch `src/moments.py` or
`configs/baseline.yaml`, that is stated explicitly as a future, gated implementation step.

---

## 1. Model population and the survey population it approximates

**Recommendation: the model's full agent population (`n_agents`) approximates QLFS's
EXPANDED LABOUR FORCE (Employed + Unemployed + Discouraged job seeker), ages 15-64, NOT the
full working-age population.**

**Justification.** The model has exactly three agent states (`EMPLOYED`, `SEARCHING`,
`DISCOURAGED`; see Section 2) and no mechanism for an agent to exit into anything resembling
QLFS's "Other not economically active" (Other NEA) category (retirees, students, people
caring for family, the permanently unable to work, and everyone else who is neither working
nor looking for work). Every model agent is, at every step, in one of the three states that
map onto QLFS's expanded labour force -- there is structurally no "Other NEA" agent. Treating
`n_agents` as an approximation to the full 15-64 population (including Other NEA) would
silently assume the model's fixed population size already accounts for a labour-force
participation rate that nothing in the model actually determines.

**Alternative rejected**: treating `n_agents` as approximating the full working-age
population. This would require either scaling moments by an assumed participation rate (not
currently done anywhere) or accepting that model shares are systematically not comparable to
QLFS's labour-force-denominator moments (`discouraged_share`, `long_term_share`, the proposed
`employment_share`) -- a much larger, silent mismatch than the population-restriction
questions already being tracked.

**Consequence**: confirms and formalises the recommendation already carried in `REVIEW_HANDOFF.md`
6.2 (ages 15-64) at the population-DEFINITION level, not only as an age filter on a survey
extract -- the model side's "who counts" question now has an explicit survey-side answer
attached to it, not just "whatever survey rows happen to remain after an age filter."

---

## 2. Observed E/U/D mapping from latent states, search activity and the observation interval

**Recommendation, building on `DECISIONS_PENDING.md` Question 2's already-quantified
inconsistency:**

| model state | this-step condition | recommended observed category | closest QLFS analogue |
| --- | --- | --- | --- |
| `EMPLOYED` | -- | E (Employed) | `Status` = 1 |
| `SEARCHING` | took >=1 search trip this step | U (actively unemployed, in the active-search denominator) | `Status` = 2 (Unemployed, the narrow category: actively searching and available) |
| `SEARCHING` | `belief_inactive_this_step` (affordable, chose zero trips) | D (inactive/discouraged) | `Status` = 3 (Discouraged job seeker) |
| `DISCOURAGED` (hard state, capital-exhausted) | -- | D (inactive/discouraged) | `Status` = 3 (Discouraged job seeker), specifically the "lack of money for transport" reason |
| *(no model equivalent)* | -- | *(not represented)* | `Status` = 4 (Other NEA) |

**Zero-trip searching agents, explained rather than assumed away.** A `SEARCHING` agent with
`belief_inactive_this_step=True` is capital-solvent (it could afford a trip) but judges, given
its own perceived offer rate, that searching this step is not worth the cost. This is the
model's "soft" inactivity channel. Under the recommendation above it counts as D this step
(matching StatsSA's own operational discouraged-worker trigger of "believes no jobs
available"), NOT as U -- reversing the current code's treatment, where these agents remain in
`long_term_share`'s `u` (searching-stock) denominator while simultaneously counting toward
`discouraged_share`'s numerator (the exact inconsistency Question 2 quantified). Because the
agent's hard `state` attribute does not change (it can resume search next step without the
`reentry_threshold`/household-inflow gate that a hard `DISCOURAGED` exit requires), this is an
OBSERVATIONAL reclassification for moment-construction purposes only -- it does not change
`src/agents.py`'s actual state machine, matching the plan's own instruction that this is "a
measurement change, not new agent behaviour."

**Capital-constrained inactivity, explained.** The hard `DISCOURAGED` state (capital
exhausted, cannot afford even one trip) is the model's literal, proposal-defined
discouragement channel. It always counts as D. There is a real, checked correspondence with a
specific QLFS reason code: `Q38RSNNOTSEEK` ("reason not searching," asked of the inactive) has
"Lack of money to pay for transport to look for work" as a distinct category (190 of roughly
4,500 classified reasons in the live 2026-Q1 extract, per the P2.2 live-data check already on
record) alongside the dominant "No jobs available in the area" (3,213) -- a plausible mapping
of the model's TWO inactivity channels onto TWO distinct QLFS reason codes, not one collapsed
category invented for this proposal.

**This correspondence is suggestive, not causal proof, and is stated as such.** A survey
respondent's SELF-REPORTED reason for not searching is not evidence that the MODEL's
zero-trip mechanism reproduces the same underlying causal process that produced that
respondent's answer -- the model's belief-driven inactivity is a stylised rational-inattention
mechanism, and QLFS's "no jobs available" is a respondent's own stated belief, arrived at
however real people actually form such beliefs. The correspondence is offered as a
PLAUSIBILITY argument for which model channel maps to which observed category, not as
validation that the model's mechanism is the true data-generating process behind the survey
response. This distinction matters because the two model channels have different reactivation
rules (soft inactivity resolves automatically next step; hard discouragement needs the
household inflow to cross `reentry_threshold`), and conflating "maps to the same observed
label" with "is the same mechanism" would overstate what the mapping establishes.

**The model's lack of Other NEA, stated as a scope limitation, not resolved.** QLFS's Other
NEA category (Status=4) has no model counterpart. This is not new -- it follows directly from
Section 1's population recommendation -- but it has a concrete consequence flagged in the
first repair batch: among the consistent, 15-64, employed-origin transition panel, 261 of
10,310 destination outcomes are Other NEA, not Unemployed or Discouraged. Any model-side
E-to-non-E comparison necessarily excludes this destination possibility; the model's
`e_to_non_e_quarterly` analogue can only ever move employed agents into `SEARCHING` or
`DISCOURAGED`, never into an Other-NEA-equivalent exit. This is disclosed as an acknowledged
scope mismatch (a modelling choice already implicit in a three-state model), not something
this mapping proposal fixes.

**Observation interval.** QLFS's `Status` derivation uses a reference WEEK (labour-force
activity in the preceding week/four weeks per StatsSA convention), while the model's states
are evaluated once per MONTHLY step -- the same weekly-vs-monthly structure already corrected
for the transport target (Section 4) applies here too, previously undisclosed. Recommendation:
treat the model's per-step (monthly) E/U/D classification as an approximation to QLFS's
per-week classification, on the same terms as Section 4's transport recommendation -- stated
explicitly as an approximation, not claimed to be the same time unit.

---

## 3. Recommended primary search-duration clock

**Recommendation: option 3 from `DECISIONS_PENDING.md` Question 5 -- a search-episode clock
with a stated pause tolerance k -- as PRIMARY, reported across a small declared sensitivity
set of k values, with option 2 (cumulative active-search months) retained as a DISTINCT
sensitivity case, not a point inside the k-range.**

**Definition.** An episode begins the step an agent both (a) is in `SEARCHING` state (not
`DISCOURAGED`, not `EMPLOYED`) and (b) takes >=1 search trip (i.e., is U under Section 2's
mapping, not D). It continues counting elapsed months, including through gaps of up to k
months where the agent is D (either channel) but has not been re-employed. A gap exceeding k
months, OR a transition to `EMPLOYED`, ends the episode; re-employment resets the clock to 0
(`resolve_hire()`'s existing `months_jobless=0` already does this correctly). A gap that ends
the episode starts a NEW episode at the agent's next U step, at 0.

**Declared sensitivity set for k: {0, 1, 3, infinity}.** k=0 (any gap ends the episode) and
k=infinity (the episode survives any gap, provided the agent is not re-employed) bound the
range; k=1 and k=3 are intermediate, defensible-length "short absence" tolerances. This is
NOT fitted -- per Question 5's own reasoning, the instrument does not resolve pause treatment
(checked against the full 71-page questionnaire; no interviewer instruction anywhere addresses
a paused-then-resumed search), so the honest position is a reported range, not a point
estimate presented as if it were resolved.

**Cumulative active-search months, as a distinct estimator, not a k-range point.** This counts
ONLY months in which the agent was actively searching (U), subtracting every D month
regardless of tolerance -- the worked example in Question 5 (3 months searching, 2-month
pause, 4 more months searching: elapsed-since-hire=9, cumulative-active=7, episode
clock=4-to-9 depending on k) shows this estimator can never be reproduced by any k value in
the episode family. It is reported alongside, labelled as testing a DIFFERENT question
("how many months did the agent actually search," not "how long has the current episode
lasted"), not folded into the same sensitivity table as if it were one more k value.

**Initialisation/reset/timing rules, consistent with the already-fixed calendar-accounting
convention.** The clock's measurement-time convention (a continuously unemployed agent reads
11 at the step-12 measurement, first classified long-term at step-13) is preserved unchanged;
this proposal is about WHAT counts as elapsed time within an episode, not about when the
observation is taken relative to the count, which is already a separately fixed decision.

**Elapsed-time-since-last-work is NOT recommended as primary.** It is what the code currently
does, and it answers `Q313TIMEUNEMPLOY`'s question ("time since last worked"), not
`Q36TIMESEEK`'s ("how long trying to find work") -- the target moment `long_term_share` is
built from `Long_term_unempl`, itself derived from `Q36TIMESEEK` (established by
cross-tabulation, Question 5). Keeping the elapsed-since-work clock as primary would leave the
model measuring a different quantity than its own calibration target by construction.

---

## 4. Transport respondent contribution, inclusion event, averaging over time: formula and worked example

**Recommendation: a person-window mean, computed per model month as a cross-sectional average
across that month's monthly travellers, then time-averaged across the measurement window with
EQUAL WEIGHT PER MONTH (not per traveller-month observation).**

### Formula

Survey side (unchanged from the existing candidate reconstruction):
```
theta_survey = ( sum_{i in S} w_i * c_i ) / ( sum_{i in S} w_i )
```
where `S` = NHTS respondents with `Q47Travlooking==Yes` and a resolved journey cost, `w_i` =
person survey weight, `c_i` = that person's one recorded round-trip journey cost for the
reference week.

Model side, recommended (replaces the current trip-mean `total_spend / (total_trips *
daily_wage)`):
```
For each model month t:
    M_t = { agents who took >= 1 search trip in month t }
    for each agent i in M_t:
        c_bar[i, t] = spend[i, t] / trips[i, t]        # that agent's own per-trip mean cost this month
    theta_model[t] = mean_{i in M_t} ( c_bar[i, t] )    # equal weight PER AGENT this month

theta_model = mean_{t in measurement window} ( theta_model[t] )   # equal weight PER MONTH
             / daily_wage
```

This is a person-mean WITHIN each month (fixing the original trip-mean/person-mean mismatch
for the within-month estimand), combined with an explicit, separately-justified choice of how
to average ACROSS months (Section "one remaining transport error," below) -- these are two
different design choices this proposal keeps visibly separate, where the earlier
`transport_measurement_specification.md` treated them as already resolved together.

### Worked example (three agents, two months)

| agent | month 1 trips (costs) | month 1 spend | month 2 trips (costs) | month 2 spend |
| --- | --- | --- | --- | --- |
| A (unequal trip counts across periods) | 3 (10,10,10) | 30 | 1 (10) | 10 |
| B (a person making no trip in month 2) | 1 (30) | 30 | 0 | 0 |
| C (a zero-cost traveller, e.g. walks) | 2 (0,0) | 0 | 2 (0,0) | 0 |

Month 1: `M_1 = {A, B, C}` (C travelled, at zero cost -- included, distinct from B's month-2
absence). `c_bar_A,1 = 30/3 = 10`, `c_bar_B,1 = 30/1 = 30`, `c_bar_C,1 = 0/2 = 0`.
`theta_model[1] = (10 + 30 + 0) / 3 = 13.33`.

Month 2: `M_2 = {A, C}` (B took no trips this month -- excluded from `M_2` entirely, not
included as a zero; a zero-cost traveller and a non-traveller are different things, per the
plan's own transport specification). `c_bar_A,2 = 10/1 = 10`, `c_bar_C,2 = 0/2 = 0`.
`theta_model[2] = (10 + 0) / 2 = 5`.

Equal-weight-per-month average: `theta_model = (13.33 + 5) / 2 = 9.165` (before dividing by
daily wage). For comparison, the CURRENT trip-mean formula over the same two months:
`total_spend / total_trips = (30+30+0+10+0+0) / (3+1+2+1+2) = 70/9 = 7.78` -- a different
number from a different estimand, confirming the formula change is not cosmetic even in this
small example.

If this were treated as a single cross-sectional snapshot matching the survey's one-week
design (month 1 only, since NHTS provides no multi-period series), the closest survey-matching
figure would be `theta_model[1] = 13.33` alone, not the two-month average -- flagged explicitly
in the next section, since averaging across simulation TIME is itself an approximation beyond
what a single survey week can identify, separate from the person-mean/trip-mean question.

---

## One remaining transport error to correct: fare conversion is not observation selection

**Withdrawn claim (2026-09-14 round): that the existing 1-7 search-days/week
fare-frequency-conversion grid "IS the required weekly-to-monthly approximation."** It is not.
Fare conversion allocates a weekly/monthly PAYMENT over an assumed trip count to get a cost
PER TRIP. Observation selection decides WHICH model agents should be treated as the ones a
weekly survey screen would have caught. These are different operations; the first does not
solve the second, and the second problem exists even under a world with no payment-period
conversion needed at all (every fare reported per single trip already).

**Recommendation: use monthly-traveller participation (`M_t` above) as an explicit,
DISCLOSED approximation to weekly-traveller participation, with a bounded sensitivity rather
than a silent equal-weighting assumption.**

**The selection issue, stated precisely.** A survey that screens "did you travel in the last
week" catches a frequent traveller (say, 4 trips/week) on very nearly every week it is fielded,
but catches an infrequent traveller (say, 1 trip/month) in only about 1 of every 4-5 weeks.
Equal-weighting every monthly traveller (Section 4's formula) implicitly assumes every monthly
traveller was equally likely to be caught by a one-week screen, which understates how much a
true weekly cross-section would be dominated by frequent travellers relative to a monthly
traveller list.

**Bounded sensitivity, not a single silent choice:**
- **Lower bound (recommended primary, Section 4's formula)**: equal weight per monthly
  traveller, i.e. every agent in `M_t` treated as equally likely to appear in a weekly screen.
  Simplest, most conservative in the sense of not assuming a specific selection mechanism.
- **Upper bound**: weight each agent in `M_t` by its OWN trip count that month (`trips[i,t]`),
  approximating "probability of being caught in a given week is proportional to how often you
  travel." This is mathematically close to reverting toward the ORIGINAL trip-mean estimator
  the model already had -- a genuinely useful observation: the trip-mean and person-mean
  formulas are not simply "wrong vs. right," they are close to the two ends of a defensible
  bounded range for this specific, previously unexamined selection problem, not unrelated
  errors.
- Report both ends as an explicit sensitivity range around the primary (equal-weight)
  estimate, analogous to the existing frequency-conversion sensitivity grid, but kept in a
  SEPARATE row/column so the two approximations are never combined into one number.

**Why an exact weekly observation model is not required for this thesis.** Building a true
within-month weekly sub-step (tracking which week of the month an agent's trips fall in) would
be a nontrivial model extension, not a measurement fix, and is not proposed. The bounded
sensitivity above is offered as the honours-thesis-appropriate resolution: state the
approximation, bound its consequence, move on -- not "solve" weekly observation exactly.

**Averaging across simulation time, stated as its own approximation.** Per Section 4's worked
example, even the equal-weight-per-month formula averages across MULTIPLE model months, while
NHTS provides one cross-sectional week. This is necessary on the model side (a single model
month's cross-section would be far noisier than the survey's own ~4,655-respondent sample), but
it is an approximation the survey design does not itself require or validate -- disclosed here,
not previously stated anywhere in the transport documentation.

---

## 5. Recommended parsimonious fare structure

**Recommendation: option (c) from `DECISIONS_PENDING.md` Question 4 -- a disclosed split of
the R12.50 anchor -- with a specific identification rule: anchor the flat + distance-linear
SUM at the model's MAXIMUM township distance (20 grid units) to equal R12.50, rather than
anchoring each component independently to the full R12.50 (the current double-count).**

**Why not the other two structural options.** Option (a) (flat only, zero the distance rate)
would remove the model's distance-dependent search-cost gradient entirely -- the mechanism
this thesis's central "spatial labour trap" question depends on. Option (b) (distance-linear
only, zero the flat cost) makes a zero-distance search trip free, which is economically
implausible (even a CBD-adjacent searcher pays SOME minimum fare) and removes a cost floor
that other estimated parameters may be implicitly calibrated against. Neither is a defensible
default for a project whose research question is specifically about distance-dependent cost.

**The identification rule, stated as a formula.** For a fare schedule `c(d) = a + b*d` (a =
flat/base, b = distance rate, d = grid-unit distance), set:
```
a + b * d_max = R12.50   (d_max = 20, the model's maximum township distance)
```
one equation, two unknowns -- one genuine remaining degree of freedom, which must still be
fixed by an assumption (unlike the withdrawn "option (d)," this does not pretend the NHTS mean
alone can identify both parts; see the first repair batch's correction). Recommended default
for that remaining freedom: the majority of R12.50 as the distance-linear component (`b`),
since minibus-taxi fare structures in South Africa are typically dominated by a per-kilometre
increment beyond a small flat boarding charge, and because `b`, not `a`, drives the thesis's
central spatial mechanism and therefore deserves the more carefully justified share. A
specific numeric split (e.g. 20% flat / 80% distance-linear at `d_max`) is left for the
implementing batch to fix alongside `search_cost_per_trip`'s bounds, not computed here, since
`search_cost_per_trip` is itself an ESTIMATED parameter (Section 7) whose calibrated value
will move away from any initial anchor regardless -- the anchor mainly needs to be a sane
STARTING point and bound-setter, not a value expected to survive estimation unchanged.

**Distinguishing transport from non-transport cost.** Nothing in the current parameterisation
represents a non-transport search cost (time cost, application effort, etc.) -- both
`search_cost_per_trip` and `transport_cost_rate` are transport-labelled in `configs/baseline.yaml`'s
own comments. No decomposition into transport vs. non-transport components is needed under the
current model structure; flagged here only so a future addition of a genuine non-transport
cost term is not confused with adjusting the transport double-anchor.

**How the aggregate total-cost observation constrains this.** The NHTS-based candidate
`transport_budget_share` target (~0.10-0.20 depending on the excursion/population/driver
decisions in Section 6) constrains the model-side aggregate `a + b*E[d]` (population mean
distance, not `d_max`) once `transport_budget_share()`'s averaging convention is also fixed
(Section 4) -- this is a SEPARATE constraint from the `d_max` anchor above: the anchor fixes
`b` and `a`'s STARTING relationship to the R12.50 source figure, while the aggregate target is
what calibration will actually fit `search_cost_per_trip` (and, if freed, `transport_cost_rate`)
against. The two are not in tension -- the anchor sets the prior/bound, the aggregate target
disciplines the fitted value -- but they should not be conflated as the same constraint.

**What is assumed vs. estimated.** `transport_cost_rate` stays FIXED (not part of the current
estimated-parameter set); the R12.50-at-`d_max` anchor rule above sets its value once decided,
and it is not re-estimated afterward, so the FLAT/DISTANCE SPLIT ITSELF is an assumption, not
something the data pins down. `search_cost_per_trip` is ESTIMATED (Section 7); its initial
bound derived from the same split is a starting point, refined by calibration. This split is a
recommendation for Aakash's approval -- not implemented in `configs/baseline.yaml` here.

---

## 6. Driver scenario, fare-frequency conversion, missingness treatment -- preserving recorded approvals

**Driver scenario: Scenario B (instrument-as-printed) as PRIMARY**, per `REVIEW_HANDOFF.md`
C.1 -- carried forward unchanged, not reopened.

**Fare-frequency conversion: 5 search days/week as PRIMARY**, with the existing 1-7 days/week
range as an explicit sensitivity (moves the point estimate by ~5.5%) -- carried forward
unchanged from `transport_candidate_estimates.md`/`transport_measurement_specification.md`,
now explicitly DISTINGUISHED from the separate observation-selection sensitivity in Section
"one remaining transport error" above (previously conflated).

**Missingness treatment: complete-case (exclude unresolved/ambiguous/DNK journeys from the
point estimate), coverage reported separately (96.79%-98.03% directly resolved depending on
driver scenario, per `transport_candidate_coverage_15_64.csv`) -- PRIMARY, carried forward.**

**Limitation, stated explicitly per this deliverable's instruction: high coverage does not
establish the absence of a selection effect.** A 96-98% resolution rate means complete-case
estimation drops only a small fraction of respondents, but small does not mean random. If
whoever cannot report a resolved cost (the ambiguous/DNK group, or drivers with unresolved
`Q433bPay` codes) differs systematically from resolved respondents -- e.g. irregular travellers
less able to recall a typical fare, or higher-income respondents who do not track small cash
costs -- the resulting point estimate could be biased in an unknown direction even at 96-98%
coverage. No correction for this is proposed (no missingness mechanism has been tested against
the data), but the assumption that complete-case estimation is unbiased here is now stated as
an assumption, not a fact established by the coverage percentage.

---

## 7. Complete proposed fitted-moment set, diagnostic moments, fixed and estimated parameters

| role | item | current status | evidence still needed before adoption |
| --- | --- | --- | --- |
| Fitted moment | `discouraged_share` | in `data/moments.csv`, fitted | Age population (15-64 vs. 15+) still open (`REVIEW_HANDOFF.md` 6.3); state-mapping change (Section 2) would change its numerator's construction if adopted |
| Fitted moment | `transport_budget_share` | in `data/moments.csv`, fitted, value 0.1058 | Averaging convention (Section 4), fare structure (Section 5), driver/frequency/missingness (Section 6) all pending -- current canonical value predates all of this proposal's corrections |
| Fitted moment | `long_term_share` | in `data/moments.csv`, fitted | Search-duration clock (Section 3) not yet chosen; state-mapping (Section 2) would change its denominator (`u`) if adopted |
| Diagnostic only (not fitted) | `distance_gradient_slope` | DECIDED removed from fitted set (2026-09-13), retained as qualitative benchmark | None -- role already settled, not reopened here |
| Proposed new fitted moment | `employment_share` | not yet in `data/moments.csv` | State-mapping (Section 2) must be adopted first, since it changes the expanded-labour-force denominator's composition; confirmed not algebraically redundant with `discouraged_share` (existing redundancy check) |
| Proposed new fitted moment | `u_to_e_quarterly` / `e_to_non_e_quarterly` | candidate estimates exist (`qlfs_candidate_moments.csv`), not yet fitted | State-mapping (Section 2); the QLFS Other-NEA scope mismatch (Section 2) needs an explicit disclosed limitation if adopted; joint stock-transition covariance (this pass's Deliverable 2 protocol) should be built before any formal specification test uses these alongside the stock moments |
| Estimated parameter | `search_cost_per_trip` | estimated, currently anchored (initial value/bounds) to the un-split R12.50 figure | Section 5's split-anchor recommendation, if approved, changes its STARTING bounds, not its estimated status |
| Estimated parameter | `firm_kappa` | estimated | Convergence/burn-in method still open (`REVIEW_HANDOFF.md` C.8, this pass's regenerated acceptance table) |
| Estimated parameter | `initial_search_capital` | estimated, previously reported near its upper bound (1.49623 against 1.5) | Whether the bound itself needs widening depends on the stationary-vs-transition interpretation decided in Question 1 -- not re-examined this pass |
| Fixed (not estimated) parameter | `firm_radius` | RECOMMENDED fixed at 2.5 (`configs/baseline.yaml`'s own pre-calibration default) since `distance_gradient_slope`'s removal took its only identifying signal | Not yet formally adopted as a confirmed fixed role -- no recalibration has run since the removal decision to confirm the 3-estimated-parameter identification holds in practice, only checked analytically (condition number) |
| Fixed (not estimated) parameter | `transport_cost_rate` | fixed, currently double-anchored (Section 5's problem) | Section 5's split-anchor recommendation, if approved, changes its VALUE; stays fixed either way |
| Fixed (not estimated) parameter | `separation_rate` | fixed at 0.0296, built by the now-rejected compounding conversion | Live decision, unchanged from `REVIEW_HANDOFF.md` C.6: measure the quarterly endpoint directly (done, `qlfs_candidate_moments.csv`), defer fixed-vs-estimated until the baseline is seen against the new candidate AND until state-mapping (Section 2) is adopted, since `e_to_non_e_quarterly`'s Other-NEA scope mismatch affects any direct comparison |
