# Design decisions

Why the model is built the way it is, in the order the decisions actually got made. This file
gets appended to as the project moves; nothing here is written after the fact to make a choice
look more deliberate than it was.

Two rounds of adversarial review sit behind most of this. Round 1 caught six model-specification
bugs that would have surfaced in week 4 or 5 of an eight-week build and cost real time to unwind.
Round 2 caught a different, more dangerous class: defects that produce plausible output with no
error and no warning. Both rounds are recorded below because the reasoning is part of the
methodology, not just the fix.

## Locked commitments (from the supervisor-approved proposal, never renegotiated in code)

1. Matching efficiency `a` is recovered by fitting Cobb-Douglas to simulated data, never imposed.
2. Policy comparisons are cost-equalised: employment gained per rand under a common budget `B`.
3. Calibration is method of simulated moments against four empirical moments.
4. DMP equations are an aggregate benchmark only; agents act on local heuristics.
5. Firms post vacancies endogenously via a profit heuristic.
6. Discouragement is not absorbing.
7. Fixed seeds everywhere; nothing goes into the thesis that I can't explain line by line.

## D1 -- Mesa 3.5.1, AgentSet activation, no scheduler

Mesa removed `mesa.time` entirely as of 3.0. There is no `RandomActivation` to reach for.
Agents activate via `self.agents.shuffle_do("step")` on the model's built-in `AgentSet`, and
`Agent.__init__` takes `(self, model)` with `unique_id` assigned automatically. Some of the
scaffolding literature I started from was written against Mesa 2 and talks about "explaining the
scheduler choice" -- there isn't one to explain in this version, which is a better question, not
a worse one: why shuffled activation instead of simultaneous update, and does the answer to any
of the four calibration moments move if you change it. That's now a test
(`test_activation_order_robustness`), not a paragraph of hand-waving.

## D2 -- The belief parameter enters as perceived-rate and targeting bias, not as a price

First draft of the search rule was `beta * p_hat_local * delta_w > c(d)`: travel if the
perceived value of searching beats the cost. That's wrong for what the beliefs-vs-scarcity
decomposition (prompt 4.5) needs. `beta` there is exactly collinear with `delta_w` and inversely
collinear with `c` -- multiplying the wage gap by 1.2 and setting beta to 1.2 do the same thing
to every equation in the model. Varying "belief" in that decomposition would have been
indistinguishable from varying a price, and the decomposition would have identified nothing.

`beta` instead biases the agent's *perceived* local offer rate away from the realised one, and
biases *where* trips get targeted -- towards locations the agent (wrongly) believes are more
promising. That's mistargeted search, which is the actual mechanism Banerjee and Sequeira (2023)
point to for their null result, and it isn't collinear with a price.

## The MVM's cold-start transient rings before it settles, and that's left in, not smoothed over

`configs/mvm.yaml`'s diagnostics figure (`results/figures/diagnostics.png`) shows unemployment
collapsing from 100 per cent at t=0 through a visible damped oscillation -- discouraged share
spikes past 40 per cent around step 15, decays in a ringing pattern, and only settles to a
stable ~2 per cent by roughly step 50. The idiosyncratic perception noise added to `decide_trips`
(see D2's implementation note in `agents.py`) breaks the worst of the all-search/no-search
synchrony a fully homogeneous population would otherwise show, but doesn't eliminate a residual
population-level echo: enough agents still update their belief off the same shared backward-
looking rate that a batch of them swing together for a few cycles before idiosyncratic noise and
the spread of individual capital levels desynchronise them fully. It's a real, reproducible
feature of a homogeneous-agent cold start, not a bug -- and it's exactly the kind of pathology
prompt 2.2 exists to surface before more complexity gets added on top of it. Every reported
moment in this repo excludes the transient (the tail-window convention in `src/run.py` and the
sweep/calibration code once built), so it doesn't contaminate any calibrated number, but it's
left visible in the figure rather than cropped out, because it's informative about the model's
own dynamics and worth being able to explain in a viva.

## D3 -- Cell aggregates, not agent panels, keyed on the initial wealth draw

Per-agent panels at N=5,000 seekers x T=120 months x 100 seeds is on the order of 60 million rows
per scenario. Recording `(distance_band x initial_wealth_quartile x step)` aggregates instead
gets to roughly 2,400 rows per run -- exactly the granularity the heterogeneity cuts in prompt
5.2 need, at a fraction of the storage and none of the reproducibility risk that comes with
carrying individual agent identifiers through a public results file.

Two things nearly went wrong here. First: cell aggregates record stocks, and the unemployment
duration distribution -- one of only four calibration targets -- is a property of an individual
spell, not a stock. A pure aggregate schema can't produce it. Second: whether the wealth
quartile is the agent's *initial* wealth draw or their *current* search capital matters a lot
more than it sounds. If it's current capital, a transport subsidy mechanically raises capital,
agents migrate up quartiles during the very policy experiment being measured, and the
heterogeneity cut -- which this thesis treats as the answer to "under what conditions", not a
side result -- becomes an artefact of the treatment rather than a description of who it helped.
Prompt 5.2 already specifies "initial wealth quartile"; the collector now matches its own spec.
`wealth_quartile` is assigned once at initialisation and never updated. There's a test for that:
quartile membership has to be constant for every agent across a full run.

The duration problem is solved by adding two small, fixed-size structures alongside the cell
aggregates, neither of which is an agent panel:

1. The actual calibration target -- at each measurement step, among agents *currently*
   unemployed, the share whose in-progress spell already exceeds twelve months. This mirrors the
   QLFS definition, which measures ongoing duration among the current stock of unemployed people,
   not completed spells.
2. A completed-spell histogram with a right-censored bucket, kept only as a descriptive
   secondary output, because completed spells and a surveyed stock are different statistics
   under length-biased sampling -- a shorter true spell is more likely to complete inside any
   fixed observation window, so a completed-spell distribution is biased towards short durations
   relative to what a survey of the current stock would show. Treating the two as
   interchangeable would have quietly mismeasured the moment that pins the vacancy-sensitivity
   parameter.

Plus flow counters into and out of discouragement, and per-cell spell counts.

There's also an optional `trace_agent_ids` list in config: a full per-step panel for a handful of
named agents and one firm, off by default. This is what the wealth-trajectory-through-search-
discouragement-re-entry figure comes from, and it's the thing I narrate at the end of week 1 to
prove locked commitment 6 is actually implemented and not just asserted in a config comment.

## D4 -- Performance gate on total campaign wall clock, not seconds per run

The real compute campaign across calibration, sweeps, experiments and robustness is roughly
7,300 named runs (Latin hypercube 3,000, Nelder-Mead ~2,000, 50 at the optimum, sweeps 1,620,
experiments 500, condition mapping 810), with headroom in that count for whatever the
pass-through grid and the beliefs/scarcity decomposition add on top. The gate that actually
matters is whether one full campaign completes inside a single overnight window, on the machine
I'm actually using -- not an abstract per-run millisecond target.

Measured on day one: `psutil.cpu_count(logical=False)` reports **6 physical cores**, 12 logical
(this is a 6-core/12-thread CPU). CPU-bound work gets `n_jobs=6`; the logical count overstates
useful parallelism for compute-bound simulation because two hyperthreads on one physical core
are contending for the same execution units, not doubling throughput. Confirmed
`joblib`'s `loky` (spawn) backend actually parallelises rather than silently serialising: a
stdlib-only smoke test with 12 tasks on `n_jobs=6` returned six distinct worker PIDs and
deterministic, non-colliding per-seed results in 1.5 seconds.

If the benchmark on `configs/baseline.yaml` at the real N and T comes in too slow for an
overnight campaign, the contingency is a vectorised NumPy fast path with an equivalence test
against the Mesa implementation. "Equivalence" can't mean bit-identical -- Mesa's shuffled
`AgentSet` activation consumes the model's RNG stream in a different order than a vectorised
pass ever would, so matching it draw-for-draw isn't a real target. The actual three-part
criterion: each implementation is byte-identical to itself when re-run at a fixed seed; the two
implementations agree exactly under one degenerate, fully deterministic config where ordering
can't matter; and every calibration-target moment matches distributionally across 30 seeds,
within Monte Carlo error.

## D5 -- Budget equalisation is a per-period cap with rationing, reported as an absorption rate

The wage subsidy's spend tracks an employment *stock*; the transport subsidy's tracks a trip
*flow*. Those aren't the same kind of quantity, so "equal budget" needs a definition, not just an
assertion. The definition used here: each policy gets a per-period cap `B`, metered as it's
spent, switching off within a period once exhausted.

The ledger reports per-period spend, cumulative spend, and `absorption_rate = spend / B` per
scenario per period. It does not assert `spend == B` exactly -- a policy that physically cannot
absorb its full allocation in a given period (not enough eligible trips to subsidise, say) is a
finding about that policy, not a bug in the accounting, and hiding it behind a forced equality
would be worse than reporting it.

When the cap binds and rationing is needed, eligible agents are drawn by a uniform lottery under
the run's own seed. The alternative -- leaving it to whatever order `shuffle_do` happens to
process agents in that step -- would make rationing outcomes a side effect of activation order
rather than a stated policy choice, and it lands directly on the distance-band and wealth-
quartile heterogeneity cuts, which are meant to be the answer to the thesis's second
sub-question. Pro-rata rescaling of the per-agent subsidy rate was the other option considered
and rejected: it changes the price every agent faces rather than the number of agents served,
which is a materially different policy than the one being modelled.

## D6 -- Digitise the Baez-Kshirsagar tables rather than run their reproducibility package

The World Bank reproducibility package for Baez and Kshirsagar (2026), `RR_ZAF_2025_490`
(DOI `10.60572/t00p-5p24`), needs R 4.5.1 and licensed Stata 18 MP. Fighting a Stata dependency
for a single calibration moment on a twelve-week clock is a bad trade for what it buys. Reading
the published tables and band midpoints by hand, with the table number and page recorded in the
notebook, gets the same number with a documented provenance trail and no licence to acquire.

## D7 -- Provisional moments, frozen at the start of calibration, not after it

`moments.csv` carries a `provisional` flag. Early drafts of this rule froze the moment set at
the end of the validation week (week 5) rather than the start of calibration (week 4) -- which
would have meant a real microdata result landing mid-calibration could force a redo of both
calibration *and* the validation exercise built on top of it, in weeks with no slack left to
absorb that. The moment set now freezes when calibration begins: anything still provisional at
the start of week 4 stays provisional for the headline results, and a microdata version that
lands afterward goes in a robustness appendix and never triggers a recalibration.

## D8 -- No AI-attribution trailers, enforced in week 1, not audited in week 8

The coding environment I'm using appends `Co-Authored-By` trailers to commits by default. The
original plan for catching this was a `kill-slop` audit pass in the final week of coding -- by
which point six version tags already exist, and removing a trailer at that point means a
force-push and moving every tag, which is exactly the kind of history rewrite this rule exists to
avoid in the first place. A `commit-msg` hook installed on day one
(`tools/hooks/check_commit_msg.py`) rejects the trailer pattern before it's ever committed.
Tested by attempting a commit that carries one and confirming it's rejected.

## D9 -- Microdata is blocked by content, not just by path

`.gitignore` stops an accidental `git add`. It does nothing against a deliberate `git add -f`,
and it does nothing if a QLFS extract gets renamed to something that doesn't match the ignored
patterns. `tools/hooks/check_no_microdata.py` runs on every commit regardless of `-f`, checking
both file extension/path and the first bytes of staged files against Stata/SPSS magic numbers.
Notebook outputs are stripped by `nbstripout` on every commit for the same reason: restart-and-
run-all discipline means a committed notebook carries its outputs, and a printed dataframe of
QLFS rows in a notebook cell is a licence breach exactly as much as a raw file would be.

## D10 -- Wage normalised to 1

`c`, `W0`, the household inflow `g`, the wage gap, and the policy budget `B` are all money
quantities. Scale every one of them by the same constant and the model's behaviour is
unchanged -- so estimating all of them freely, as an early draft of the calibration did, left
the parameter set identified only up to an arbitrary scale. The wage is normalised to 1 and
everything else is estimated relative to it; results are rebased to rand only at the point
they're reported.

## D11 -- Measurement timing: stocks before matching, flows during it

Once firms post vacancies endogenously in response to local seeker density (see the firm
heuristic below), `v_t` responds *within* a period to the same density that produces `m_t` in
that same period. If the collector recorded `u` and `v` after the matching step ran, the
regressor in the matching-function fit would be contaminated by the outcome it's supposed to
explain -- and the contamination wouldn't be the same size in the frictional and frictionless
configs, because the within-period flows differ between them, so it wouldn't even cancel out in
the sub-question 1 comparison. The convention: `u_t` and `v_t` are recorded as start-of-period
stocks, before the matching call for step `t` runs; `m_t` is the count of hires resolved during
step `t`. Two tests hold this in place: `m_t <= min(u_t, v_t)` every step, and the exact stock
identity `u_{t+1} = u_t - m_t + lambda * l_t - exits_to_discouragement + re_entries`.

## D12 -- Common random numbers inside the calibration search

Nelder-Mead has no built-in defence against a noisy objective. If the 15 seeds used to evaluate
the simulated-moments loss are redrawn independently at every trial parameter vector, the loss
surface itself is stochastic: the simplex can contract onto a random fluctuation and report a
false convergence, or wander indefinitely and burn through the evaluation budget without ever
settling. A restart policy for simplex collapse treats the symptom, not the cause. The actual
fix is common random numbers: one fixed list of 15 seeds, held in `config.py`, reused at every
parameter evaluation during both the Latin hypercube stage and the Nelder-Mead stage, so the
loss becomes a deterministic function of the parameters being searched over and the simplex
contracts on the real surface rather than on sampling noise. The 50-seed evaluation reported at
the optimum uses a disjoint seed list, so the fit quality reported in the thesis isn't measured
on the exact seeds the optimiser was allowed to fit to. There's a test for the determinism
itself: two evaluations of the loss at the same parameter vector return an identical float.

## D3, implemented -- wealth draw, cell aggregates, and the completed-spell histogram

Three pieces landed together since they share one dependency chain. Wealth heterogeneity
(`initial_capital_spread`, prompt 3.1) draws each agent's starting capital from a lognormal
parametrised by coefficient of variation, not a normal -- real wealth data is skewed and never
negative, and a normal draw would need truncating in a way that quietly drags the mean away
from `initial_search_capital`, which calibration later treats as a target. Wealth quartiles are
rank-assigned from that single draw before any agent exists, exactly once, matching the same
"initial, never current" rule as `distance_band`.

The cell aggregates are `(distance_band, wealth_quartile, step)` rows built fresh each step
from a live scan of the population -- not incrementally maintained flow counters -- which
costs a little more per step but means the aggregate can never silently drift out of sync with
the actual agent states, the same kind of bug class the model has already hit twice. Measured:
roughly 2,250 rows for a 150-step, 4-band, 4-quartile run, matching D3's original ~2,400-row
estimate closely enough to trust the shape of the design.

The completed-spell histogram's bucket edges (3, 6, 9, 12, 36, 60 months) were chosen to match
QLFS's own duration question (`Q36TIMESEEK`) exactly, not picked independently -- so the
eventual Week 3 comparison against real data is a straight like-for-like, not a re-binning
exercise. Verified the mechanism actually fires, not just that it stays at zero: the first spot
check used a comfortable, fast-churning config where every spell resolved in under six months,
which said nothing about whether the 12-month threshold or the right-censoring at run-end
actually worked. A second check under deliberately extreme scarcity (2 vacancies, 500 agents)
confirmed both: `n_long_term` climbed to the full population and the completed-spell histogram
correctly right-censored everyone still searching at the `>=60` bucket when the run ended.

## D13 -- Plain coordinates for the spatial grid, not Mesa's Cell/CellAgent API

Mesa 3.5.1 has a real grid system (`mesa.discrete_space`: `OrthogonalMooreGrid`, `CellAgent`,
`Cell` objects with neighbourhood queries). The model doesn't use it. Every economically
load-bearing thing the spec asks for -- a home location, a distance from home to the CBD, a
neighbourhood-radius query for which searchers a firm can hire from -- is fully delivered by a
plain `(x, y)` float pair per agent and Euclidean distance, and agents never move cell-to-cell
during a run (home is drawn once at initialisation and fixed, matching D3's "initial, not
current" rule). Mesa's grid machinery is built for agents that traverse the grid step by step
and query literal cell neighbours; adopting it here would mean learning and testing a second,
unfamiliar API surface (on top of the Mesa 3.5.1 discrete-event surprise already hit once in
Week 1) to get an abstraction the model doesn't need. "Spatially explicit" means agents have
real positions and real spatial relationships drive costs and matching, not that the
implementation has to route through Mesa's specific spatial classes.

## D2, closed out -- search positions as the spatial half of the targeting bias

D2 (Week 1) implemented `beta` as a bias on the agent's *perceived offer rate* and noted the
*targeting* half -- biasing *where* an agent searches, not just how hard -- needed the spatial
grid to mean anything. It's implemented now as `JobSeeker.search_positions()`: each trip an
agent makes generates an effective search position, drawn within a disk of radius
`cbd_radius * beta` around the CBD centre. An unbiased agent (`beta = 1`) draws uniformly
within the CBD zone, which is exactly where firms are placed, so an unbiased agent's trips
land where the real vacancies are by construction. A biased agent's effective radius is scaled
by `beta` -- overconfident agents (`beta > 1`) wander further from the centre than the CBD zone
actually extends and miss firms clustered nearer the middle; underconfident agents
(`beta < 1`) stay too close in and miss firms scattered towards the zone's edge. Either
direction shrinks the overlap between the agent's search and where the vacancies actually are,
without the agent ever being told the true firm locations -- which is the actual mechanism
behind "mistargeted search" (Banerjee and Sequeira 2023), not a disguised price effect.

## The firm can get permanently locked out of posting, and needed its own exploration floor

Caught in testing a 10-firm spatial config, not anticipated in design: a firm whose computed
vacancy target rounds to zero posts nothing that period, and `update_fill_probability`'s
quiet-period rule (correctly) leaves its belief untouched on a quiet period -- but if a firm's
belief decays low enough from a run of genuinely bad-luck outcomes (not quiet periods: the firm
posted vacancies and simply filled none of them, which local demand variance makes entirely
possible), the computed target can go negative and stay there, since nothing ever refreshes a
belief that never gets tested again. This is the same structural failure as Week 1's agent-level
zero-search deadlock -- a bad belief that can never be corrected because it prevents the very
observation that would correct it -- arrived at through bad luck rather than a bad prior, and at
the firm level there's no shared aggregate signal (unlike the model-level
`observed_hire_rate_per_trip`) to bail an individual firm out.

Two fixes, addressing two different parts of the same failure. First, `update_fill_probability`
became an exponential moving average (0.3 weight on the fresh observation) instead of a hard
replace, so one unlucky period pulls the belief down without being able to zero it out in a
single step. Second, and load-bearing: a firm quiet for three consecutive periods
(`_EXPLORATION_PATIENCE`) posts one trial vacancy regardless of what its own formula says,
purely to generate a fresh observation. The smoothing alone doesn't fix the deadlock -- as the
belief decays towards zero the computed target approaches a fixed negative number
(`kappa * -c_post`), not zero, so it keeps rounding down to zero forever without the floor.
Economically, the floor is defensible on its own terms, not just as a numerical patch: most
firms have some baseline replacement hiring from ordinary attrition even in a bad period, so a
small amount of forced exploration isn't unrealistic on top of being necessary.

## Two corrections to not-yet-built code, from reading McFadden and Pissarides directly

Neither `calibrate.py` nor the firm's free-entry test exists yet (both are Week 2/4 work), so
these are recorded now to guide that build rather than to fix anything already written.

**The MSM weight matrix is inverse data variance plus simulation variance, not data variance
alone.** The earlier plan (see the definitional-traps section below) said weight by inverse
*data* sampling variance and let Monte Carlo variance decide only the seed count. McFadden
(1989) decomposes total estimator variance into the data-sampling term *and* a separate
simulation-variance term (p.1006) -- weighting by data variance alone implicitly assumes the
simulation term is negligible. `calibrate.py` must either weight by the inverse of the *sum* of
the empirical standard error and the simulation variance at the current seed count, or
explicitly demonstrate the simulation term is negligible at 15/50 seeds and say so in the
thesis. One of the two, stated plainly -- not silently assumed.

**The free-entry test needs to test Pissarides's actual condition, not a proxy for it.** The
plan for the firm heuristic's discipline check was "average expected profit net of posting cost
tends to zero as kappa rises." Pissarides's job creation condition (2000, p.11-12) is
`p - w = (r + lambda) * pc / q(theta)` -- it nets discounted profit against posting cost through
the discount rate `r`, the separation rate `lambda`, and the vacancy-filling probability
`q(theta)`. A heuristic that merely drives profit towards zero as `kappa` rises could pass that
weaker test through pure market congestion without actually tracking free entry. When the firm
heuristic is built (Week 2), the test needs `q(theta)`, `r`, and `lambda` in it, or the model
chapter needs to say precisely which terms of the asset-value equation the heuristic represents
and which it leaves out.

**The calibration is exactly identified and that costs something.** Four free parameters, four
moments, no slack for an overidentification test (McFadden's rank condition permits K = k, but
offers no comfort about what's lost by it). The out-of-calibration validation against
Banerjee and Sequeira's null result is the actual substitute for a formal overidentification
check here, and the methodology chapter should say so explicitly rather than let an examiner
notice the exact-identification on their own.

## `dmp.py` and locked commitment 1

Chen's (2025) Appendix B system takes matching efficiency `a` as an input to solve for the
steady state -- which sits uncomfortably close to locked commitment 1 (`a` is recovered, never
imposed) unless the boundary is stated precisely. `a` is a required argument to `dmp.py` with no
default, supplied by fitting the frictionless ABM configuration, never by Chen's own calibrated
value. What the benchmark actually checks is internal consistency of `(theta, q, u, v, w)` given
that `a` -- not the level of `a` itself. Two further mismatches, both stated in the module
docstring rather than left implicit: Chen normalises productivity to 1 with the wage determined
endogenously by Nash bargaining, while this model normalises the wage to 1 (D10) -- feeding one
model's outputs into the other's equations without conversion would silently rescale everything.
And Chen's whole system is calibrated at quarterly frequency while this model steps monthly.
Solved with `scipy.optimize.least_squares` under bounds, not a bare `fsolve`, which is unbounded
and will return a mathematically valid but economically nonsensical `l < 0` from a poor starting
point without complaint.

## The AR(1) productivity shock is rebased from quarterly to monthly, not copied

Chen (2025) Table 1 reports `rho = 0.612` and `sigma = 0.0085` for the TFP process, sourced from
Kudoh et al. (2019) -- at **quarterly** frequency. This model steps monthly. Using 0.612 directly
as a monthly persistence understates the shock's actual persistence by roughly a factor of
three, which matters here specifically because that persistence is what generates the `(u, v)`
co-movement the matching-function regression needs variation in. Rebased by matching the
lag-3 autocorrelation and the unconditional variance: `rho_A = 0.612^(1/3) ~= 0.849`,
`sigma_A = 0.0085 * sqrt((1 - 0.849^2) / (1 - 0.612^2)) ~= 0.0057`. Named `rho_A` in config,
deliberately distinct from `rho`, which is the neighbourhood matching radius and one of the four
free calibration parameters -- sharing a name would have let the optimiser silently move the
shock persistence while searching over the matching radius.

## The separation rate is estimated locally, with a documented foreign fallback

Chen's separation rate traces back to Miyamoto (2011): a Japanese **monthly** exit probability of
0.0048, which Chen multiplies by three to report a quarterly 0.0144. Using that number here by
default would mean calibrating a stated South African mechanism on a Japanese labour-market
parameter with no argument for why the two should match. The separation rate is instead computed
from South African employed-to-not-employed quarter-to-quarter transitions in PALMS/QLFS, inside
the same notebook that already opens that data to build the duration-distribution moment.
Miyamoto's 0.0048 is kept only as a fallback if the South African transition rate isn't
computable by the end of week 3, and if it's used, that substitution is flagged here as a foreign
calibration, not silently absorbed into the parameter table.

## The matching-function fit tests constant returns before assuming it

Neighbourhood matching within a fixed radius, on a fixed grid, with a fixed number of firm
nodes, has no particular reason to be constant-returns-to-scale -- and if the degree of returns
differs between the frictional and frictionless configurations, a difference in the fitted
matching efficiency `a` between them would mix a genuine efficiency loss with pure approximation
error from evaluating a mis-specified functional form at two different points in `(u, v)` space.
The same risk shows up again in the policy experiments: under a wage subsidy, vacancies rise
endogenously, so a shift in `a` there could be compositional rather than a real efficiency
change. The unconstrained regression `log m = log a + b_u log u + b_v log v` is reported first,
with `b_u + b_v` and a Wald test of `b_u + b_v = 1` for every configuration, before the
CRS-constrained `a` is reported as the headline number. If the test fails in one configuration
but not another, the `a`-difference between them gets reported as contaminated by misspecification,
not as a clean efficiency measurement. Chen's own `a = 0.471` is a quarterly Japanese calibration,
useful only as an order-of-magnitude sanity anchor -- never a number this model is compared
against directly.

## Two definitional traps in the moments, found while sourcing provisional values

**The discouraged-share moment.** StatsSA stopped publishing the "expanded unemployment rate"
after Q2:2025 and replaced it with a broader indicator, LU3, which also folds in non-searchers
available for other reasons and searchers who weren't available in the reference period. The two
are not the same quantity (42.9 vs 42.4 per cent in adjacent quarters makes them look similar by
coincidence, not by definition). The discouraged-share moment has to be computed from microdata
using the StatsSA discouraged work-seeker definition directly, at one fixed QLFS vintage stated
in the notebook -- not lifted from a media release headline number, which could silently mix two
different definitions across the sample period.

**The transport-budget-share moment.** At least three published numbers answer "what share of
household spending goes to transport", and they differ by roughly a factor of four depending on
what's being measured: transport as a share of total household consumption expenditure
(15.3 per cent, nationally); the share of urban public-transport-using households spending more
than 20 per cent of per-capita household income on transport (60.1 per cent urban, 54.7 in
metros); and transport cost as a share of net wages for *employed* workers once commute time is
priced in (57 per cent, exceeding 80 in the lowest quintile -- Shah and Sturzenegger 2024). None
of these is quite the right object: the model's `c` is a search cost paid by the *unemployed*
while searching, not a consumption share or a cost borne by people who already have the job. The
moment used is the one closest to that concept, and the mismatch is stated explicitly in the
calibration chapter rather than treated as if any of the three numbers were interchangeable.

## The distance_gradient_slope moment was sourced to a table that doesn't exist

All fourteen papers on the reading list were deep-read end to end once the physical PDFs were
in hand (`paper/notes/literature-verification.md` has the full report). The most consequential
finding: `distance_gradient_slope` was documented above as "employment rate, percentage points
per 10 km from the CBD, digitised from Baez and Kshirsagar (2026) Table 1" -- but Table 1 in
that paper reports **population density** by kilometre band, not employment. The paper's actual
employment result is a different object entirely: Table 5b regresses employment share on a
**within-city, population-weighted percentile rank of network travel time** to the nearest
business district, city-specific (Johannesburg 4.9, Cape Town 3.7, eThekwini 6.5 percentage
points per 10 percentile points of that rank). Digitising Table 1 for this moment would have
quietly calibrated the model against the wrong empirical object.

Neither of the two obvious fixes is free. A genuine km-based gradient would need geography
finer than District Council/Municipality level, which is the ceiling on every public-release
file actually on disk (NIDS, QLFS, NHTS all bottom out there -- see the geography note above).
So the moment is **redefined to match what Baez and Kshirsagar actually measure**: the model's
own simulated agents are ranked by percentile of distance from the CBD within their own run
(exactly analogous to the paper's within-city travel-time percentile rank), and the simulated
moment is the slope of employment share on that percentile rank, in the same units the
empirical target is reported in. `data/README.md`'s moment table reflects this.

## Citation corrections, confirmed by reading the actual papers, not just searching for them

Several corrections made earlier in this file from web search were provisional; the deep read
confirmed some and corrected others. Recorded here so the two aren't conflated:

- **Shah and Sturzenegger.** The earlier entry in this file cited *South African Journal of
  Economics* 92(4), 549-580, DOI `10.1111/saje.12388` -- found by search, never confirmed
  against an actual copy. The file on disk, and the file the IMF (2026) paper itself cites, is
  **Sturzenegger and Shah (2022), CID Research Fellow and Graduate Student Working Paper No.
  142, Harvard University**, October 2022. Cite the working paper until the SAJE offprint is
  obtained and every page-specific number in it is re-verified against that version -- page
  numbers do not carry over between a working paper and its eventual typeset journal version.
- **The "80 per cent of net income" figure.** Confirmed misattributed. The IMF (2026) paper's
  own text attributes it explicitly: "(Figure 2, Shah and Sturzenegger, 2022)" (IMF SIP
  2026/018, p.4). The IMF did not originate this number; Sturzenegger and Shah (2022) did, and
  the thesis should cite them, not "a 2026 IMF study."
- **"Ebrahim et al. (2024)"** is Ebrahim, A. and Pirttila, J., *Journal of Development
  Economics* 172, 103394 -- two named authors, not "et al." The finding is not a flat zero:
  overall employment is near-zero, but that hides an **offsetting gender pattern** -- women's
  employment rose 4.05 percentage points, men's fell 3.39 points (p.10), which the paper
  attributes to wage incidence, not firms simply banking a windfall. A genderless ABM cannot
  reproduce that specific mechanism; the model's distance and wealth cuts are a different
  dimension of heterogeneity, not a substitute for it, and the limitations chapter should say
  so plainly rather than gesturing at "the empirical literature."
- **Von Fintel (2018)** and **Zenou (2009)** also had citation-detail errors (working-paper vs
  published pagination for the former, a wrong title for the latter) -- full corrected
  citations in `paper/notes/literature-verification.md` section 2.

## The stated "gap" in the spatial search literature was partly backwards

Thesis_Explainer_v2.pdf characterises Wasmer and Zenou (2002) and Zenou (2009) as assuming
"uniform commuting distances." That's the opposite of what those papers do: heterogeneous
commuting distance is the central state variable in both (Wasmer and Zenou 2002, p.520), and it
is what generates each paper's headline result. An examiner who knows either paper would catch
this immediately. The gap that actually survives scrutiny, and is worth quoting directly: these
papers hold *search intensity* fixed, and Zenou (2009) explicitly assumes "perfect capital
markets with a zero interest rate" (p.537) -- workers can smooth income over time without limit,
which precludes any depletable household resource stock *by construction*, not by omission.
That's a stronger, narrower, and more defensible claim than "uniform distances," and it's the
one that should replace the current text.

## Full literature verification report

`paper/notes/literature-verification.md` has the complete deep-read of all fourteen papers:
what each one actually says with page references, every quotable number and which ones are
misattributed elsewhere, what's usable as a calibration input versus what has to come from the
microdata directly, ten ranked methodological problems (including the matching-function
simultaneity concern for SQ1's frictional-minus-frictionless differencing, and the MSM weight
matrix choice against McFadden 1989's own variance decomposition), and an explicit assessment
of where the thesis's contribution claim is narrower than currently phrased.
