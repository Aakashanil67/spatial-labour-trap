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

## The earlier firm-lockout fix wasn't actually verified, and a second, separate deadlock was hiding behind it

Found while trying to build the scarce-vacancy smoke test config: sweeping `n_agents` on
`configs/baseline.yaml` from 500 up to 5,000 turned up a sharp, non-monotonic collapse. At the
same seed, `n_agents=3,200` ran fine, labour market tightness falling smoothly as expected;
`n_agents=3,250`, `3,300` and `3,350` -- population otherwise unchanged -- ended the run at
effectively 100 per cent unemployment, zero matches for the entire post-burn-in window; `3,400`
recovered again. That's not what a scarcity gradient looks like -- it's a cliff, and a cliff
meant something was actually broken, not just economically severe.

Two distinct bugs were sitting behind it, and the first one exposed how weak the existing
regression coverage for the previous fix actually was. `test_firms_never_permanently_locked_out`
asserts `quiet_streak <= _EXPLORATION_PATIENCE`, and that assertion is true by construction: the
streak resets to zero every time the exploration mechanism fires a token vacancy, whether or not
that vacancy is ever filled. A firm can sit in "post one vacancy, it goes unfilled, streak resets,
repeat" forever and this test would still pass. The actual failure at scale: `fill_prob_estimate`
can decay asymptotically towards zero across many consecutive zero-hire exploration attempts --
smoothing stops any *single* period from zeroing it out, exactly as the earlier fix intended, but
says nothing about the limit of repeated small decays. Once the estimate is negligibly small, the
formula `kappa * (fill_prob * expected_value_per_hire - c_post)` is dominated by the `-c_post`
term regardless of `expected_value_per_hire`, and rounds to zero every period except the rare
exploration window -- and if that window's own single vacancy also goes unfilled, which becomes
likely exactly when the firm needed it most, nothing ever pulls the estimate back up. Fixed by
flooring the *updated* estimate at the same 0.05 already used for the naive initial prior
(`Firm._MIN_FILL_PROB`), not just the starting value -- the asymmetry between an initial floor and
an unfloored update was the actual gap. At baseline's economics this keeps the computed target at
or above one most periods, so a firm gets a real chance at a fresh observation continuously rather
than once every three quiet periods.

The second bug was independent and, on its own, sufficient to explain the cliff. `decide_trips`
scales search intensity continuously, by design, specifically to avoid a hard "worth it or not"
cutoff -- but `desired = round(max_trips_per_step * intensity)` reintroduces exactly that cutoff:
`round()` cannot return anything but zero below intensity `1/(2 * max_trips_per_step)`. And
`observed_hire_rate_per_trip`'s naive initial value is total initial vacancies divided by
`n_agents` -- correct as a first guess, but it means a bigger population starts with a *lower*
perceived hire rate, not a higher one, purely from the bigger denominator. Once the population's
typical intensity starts below that rounding threshold, every agent's `desired` trip count rounds
to zero on the very first step, `total_trips` is zero, and `observed_hire_rate_per_trip` -- left
deliberately unchanged on an all-quiet step, so a temporary lull can't be mistaken for a
permanently dead market -- never gets the observation that would correct it. The market freezes
at zero search activity for the rest of the run. This inverts the intuition a bigger population
should produce: more searchers made the synchronised freeze *more* likely, not less, because
it only ever lowered the shared starting belief. Fixed with the same idiosyncratic-noise logic
`decide_trips` already uses to stop the population behaving identically: when rounding would send
`desired` to zero but the underlying intensity is positive, the agent still gets one trip with
probability equal to that intensity, rather than being deterministically rounded down alongside
everyone else. Checked this doesn't touch `configs/mvm.yaml`'s regression before relying on it --
instrumented the boundary condition directly and confirmed it fires zero times across a full MVM
run (7,718 `decide_trips` calls), so the byte-identical MVM numbers this file has re-verified
after every commit this session are untouched; it fires 442 times out of 2,310 calls on
`configs/baseline.yaml`, which is exactly the config this bug lived in.

Both fixes are now backed by tests that actually exercise the failure, not just the mechanism
that was supposed to prevent it -- checked directly against a stash of the pre-fix code to
confirm each one fails without the fix and passes with it, rather than trusting that by
inspection alone, which is exactly the mistake that let the first fix's coverage gap through
undetected for a full session.

## D4, closed out -- the campaign fits inside an hour, not an overnight window

Benchmarked `configs/baseline.yaml` at its real N and T (500 agents, 150 steps) through
`runner.py`'s actual `run_many`, not a standalone timing script, so the measurement includes the
same cache-write and `joblib` dispatch overhead the real campaign pays: 24 seeds, chosen well
outside any range already in `results/cache/` so every one was a genuine cache miss, at
`N_JOBS=6`. Wall clock: 8.0 seconds for 24 runs, or 0.332 seconds of effective per-run time once
the six-way parallelism is accounted for. Scaled to the full campaign's roughly 7,300 named runs
(D4's own count: Latin hypercube 3,000, Nelder-Mead ~2,000, 50 at the optimum, sweeps 1,620,
experiments 500, condition mapping 810), that's about 40 minutes -- 0.67 hours against an
overnight window D4 originally sized at 8 to 12 hours. The Mesa-based implementation has roughly
an order of magnitude of headroom left even before the pass-through grid and the
beliefs/scarcity decomposition (both currently unscoped additions per the schedule's cut list)
are added on top. The vectorised NumPy fast-path contingency, and the three-part equivalence
test D4 specified for it, are not needed and are not being built -- reopen this decision only if
a specific addition to the campaign's run count actually threatens the window, not
speculatively.

## The scarce-vacancy smoke test: the sign pattern is there, and vacancies are visibly the bottleneck

`configs/scarce_vacancies.yaml` and `configs/scarce_vacancies_subsidy.yaml` differ in exactly one
field, `transport_cost_rate` (0.004 halved to 0.002 -- a real subsidy, not a rounding change),
both at the 18,000-agent operating point the population sweep above found. Five seeds
(42, 101, 202, 303, 404), same seeds under both configs, run through `runner.py`.

Search intensity rose under every single seed: mean trips per active searcher went from 1.018 to
1.025 on average, +0.4 to +0.9 per cent depending on the seed, consistently in the same
direction. Employment did not move in any consistent direction: mean employed count changed by
+3.25, -3.39, +3.48, -0.25 and -2.49 per cent across the five seeds; the mean across seeds is +0.11 per cent -- indistinguishable from noise at this
seed count, and nowhere near the scale of the intensity change. Mean vacancies posted and mean
matches per period barely moved at all: 146.45 to 146.37 across both configs. That's why: firms
were already filling almost every vacancy they posted before the subsidy (`fill_ratio ~= 1.00`),
so vacancy supply -- not search effort -- was already the binding constraint, and more searching
cannot conjure a match that has no vacancy to land in. That's the Banerjee and Sequeira (2023)
sign pattern, present and clean, on a config that changed nothing about firm behaviour.

What actually moved instead: mean unemployed count rose sharply, 40 to 55 per cent depending on
the seed. With employment flat and vacancies flat, that rise has to be agents who were
previously discouraged or belief-inactive being pulled into active search by the lower cost, not
agents leaving jobs. The subsidy raises participation in a scarce market without raising
placement -- a sharper, more mechanistic statement than "search up, employment flat" on its own,
and one this smoke test wasn't explicitly asked to produce but which falls directly out of the
model's own accounting once vacancies are genuinely the bottleneck.

Sign-only, five seeds, not paired-difference intervals under common random numbers (that's D12,
Week 4 work) -- this is exactly the half-day check the plan scoped, not the Week 5 validation.
The consistency of the intensity sign across all five seeds and the near-total flatness of
vacancies/matches make the result reasonably trustworthy for what it's being used for: a decision
to proceed, not a paper claim.

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

**Implemented and validated.** `dmp.py` transcribes Chen's own six-equation system (`w`,
`lambda*l = q*v`, `q = a*theta^-phi`, `theta = v/u`, `l+u=1`, and the detailed job-creation
condition) directly, treating `b` as a fixed rand-level parameter rather than re-deriving it as
a moving fraction of whatever wage the solve produces, which Chen's own calibration procedure
also does -- he sets `b = 0.6w` once, from a baseline steady-state `w`, then holds `b` fixed for
later solves, not literally 0.6 times an endogenous `w` inside the same system (that would make
the wage equation circular). The transcription is checked, not just run: feeding the solver
Chen's own Table 1 parameters (`a = 0.471`, quarterly) recovers `theta = 0.781`, matching his
own reported target of 0.78 to three decimal places. Chen calibrated `a` specifically so his
system would produce that target, so an independent transcription landing on the same number is
real evidence the six equations were copied correctly, not something either side could fake by
having tuned `a` itself. Also confirmed: convergence at this thesis's own monthly-rebased
parameters, robustness to a deliberately poor initial guess (same fixed point recovered to
four decimal places), and determinism under repeated calls.

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

## `trace_agent_ids` and the single-agent trajectory figure

Locked commitment 6 says discouragement is not absorbing. Every test in `test_model.py` and
`test_spatial.py` checks that fact numerically, but a reviewer -- or an examiner in a viva --
should be able to see it happen to one agent, not just trust an aggregate share that never
quite reaches zero. `config.py` gained `trace_agent_ids: tuple[int, ...] = ()`: a full per-step
panel (`state`, `search_capital`, `months_in_state`, `trips_this_step`, `distance_to_cbd`), but
only for the handful of agents named, never the whole population -- D3 already rejected an
agent-level panel as a calibration structure, and this isn't one; it's a demonstration prop, off
by default and fixed-size even when on.

**Timing is deliberately the opposite of D11.** D11 records `u_t` and `v_t` before the matching
call runs, so the matching-function regressor isn't contaminated by that period's own outcome.
The trace records *after* matching, on purpose: it exists to show what happened to the agent
that step. Sometimes that's a re-entry that leads straight to a hire, recorded in the same row.
Recording it pre-matching would show the agent as still `DISCOURAGED` on the step it actually got hired,
which is a worse demonstration of the mechanism, not a more consistent one. The two conventions
serve different purposes and neither is wrong for its own use.

**Finding an agent worth showing took a scan, not a guess.** A bespoke low-vacancy config was
tried first and produced almost no state transitions at all (195 of 200 agents never left
`SEARCHING` across the run) -- too degenerate to demonstrate anything. `configs/baseline.yaml`'s
own already-validated parameters, at `n_agents=200`, were instead run across seeds 1 to 14 with
every agent traced temporarily, and each agent's full state history inspected. Seed 5, agent 32,
lives through five complete `SEARCHING -> DISCOURAGED -> SEARCHING/EMPLOYED` cycles in 150
steps: capital drains while searching, the reentry threshold is approached from below while
discouraged (refilled only by the household inflow), then the agent re-enters. `configs/trace_demo.yaml`
pins that exact seed and agent id, with the scan method recorded in its header comment so it
doesn't read as an arbitrary choice.

`diagnostics.py` gained `plot_agent_trajectory()`: search capital as a black line, with the
agent's state shaded as a background span per period so state changes are visible without a
second line competing for attention. Run via
`python -m src.diagnostics --config configs/trace_demo.yaml --trace-agent 32`.

One thing the trace tests caught: firms are created before job-seekers in `CityModel.__init__`,
so with `n_firms` firms present, unique ids 1 through `n_firms` belong to firms and seeker ids
start only after that. A first draft of the tests named seeker ids by guessing small numbers and
silently picked up firms instead, so the trace came back empty. The fixed version probes a throwaway
model of the same config for its actual seeker ids rather than assuming an offset.

## Full literature verification report

`paper/notes/literature-verification.md` has the complete deep-read of all fourteen papers:
what each one actually says with page references, every quotable number and which ones are
misattributed elsewhere, what's usable as a calibration input versus what has to come from the
microdata directly, ten ranked methodological problems (including the matching-function
simultaneity concern for SQ1's frictional-minus-frictionless differencing, and the MSM weight
matrix choice against McFadden 1989's own variance decomposition), and an explicit assessment
of where the thesis's contribution claim is narrower than currently phrased.

## Week 3, notebook 01 -- discouraged_share, and the denominator question that applies to every QLFS moment

The first real (non-provisional) number in `moments.csv`. Two of the decisions below apply to
every QLFS-sourced moment still to come, so they're recorded once here rather than re-litigated
per notebook.

**Denominator: the expanded labour force, not the working-age population.**
`src/moments.py`'s `discouraged_share()` computes `(discouraged + n_belief_inactive) / n_agents`
-- a share of the *whole modelled population*. The model has no scholar, retiree, or home-maker
agent type; every agent is either working, searching, or discouraged from searching. That maps
onto StatsSA's expanded labour force (employed + unemployed-narrow + discouraged), not onto the
full working-age population QLFS actually surveys, which also includes people the model simply
doesn't represent. Using the wider denominator would have diluted the share with a population
the model has no way to reproduce, and is also not the denominator StatsSA itself uses when it
publishes the discouraged work-seeker rate as a share of the expanded labour force.

**Source: QLFS's own `Status` classification, not a reconstruction.** `Status` (and its finer
sibling `Lfs_Status`, present in some but not all quarters' files -- `Status` was used for
consistency across all four) already classifies every respondent as Employed, Unemployed,
Discouraged job seeker, or Other not economically active. Re-deriving that classification from
the underlying reason codes (`Q38RSNNOTSEEK`, `InactReason`) would only add a second, less
reliable copy of a judgement StatsSA has already made correctly.

**Standard error is a Kish approximate-design-effect estimate, not a full survey-design SE.**
QLFS's file carries a `Stratum` variable but no PSU/cluster identifier was found, so the
reported SE accounts for unequal weighting but not for clustering -- it understates the true
design-based SE, in a known, stated direction, rather than being silently treated as exact. A
full Taylor-linearised or replicate-weight SE would need design variables this extract doesn't
carry.

**Four quarters, most recent single quarter as the headline, not a pool.** 2025 Q2 through
2026 Q1 -- the four most recent with clean microdata on disk -- show a real upward trend, 11.9%
to 13.4%, several times larger than any single quarter's own sampling error. Pooling across
quarters would have averaged over that trend rather than reported it. `moments.csv`'s schema
expects one `period` per moment, so the most recent quarter (2026 Q1, 13.43% +/- 0.23pp) is the
headline value; the full by-quarter series lives in the notebook as documented context. The
model's AR(1) shock mean-reverts and has no drift term, so a moving empirical target is a real
tension worth carrying into the Calibration chapter, not one this notebook resolves.

## Week 3, notebook 02 -- transport_budget_share, the moment the plan itself flagged as fraught

The plan's own definitional-trap note already warned that published transport-share figures
differ fourfold and none of them is quite `c`. NHTS 2020 turns out to have a real, purpose-built
question block for job-search travel specifically -- `Q46Lookwork`/`Q47Travlooking` identify
4,655 of 145,385 respondents who travelled while looking for work -- but no codebook shipped
with the initially-extracted CSVs, and the obvious cost variable was a trap of its own.
`Q434bCost` is labelled "Vehicle cost to work place," a private-vehicle-specific field that's
Not-applicable for 4,512 of those 4,655 people; the real costs live in `Q429b3Cost1` through
`Q432b3Cost4`, one field per mode of travel actually used, on the question block matched to
`Q47Travlooking`'s own numbering rather than an earlier, similarly-numbered block asking about
the regular commute to an *existing* job. Getting that pairing wrong would have silently measured
commuting costs for the employed instead of search costs for job seekers -- the plan's warned-of
substitution, arrived at almost by accident before the labelled `.dta` file confirmed which block
was which.

**A unit mismatch that would have shipped a number an order of magnitude too small.** The NHTS
cost fields are for a single reported travel day; `moments.py`'s `transport_budget_share()` is a
per-model-step (roughly monthly) quantity. A first pass divided the day-level cost by a monthly
wage directly and got 0.0049 -- nowhere near the 15-60 per cent range the plan's own trap note
already flagged from other sources, which is exactly the kind of implausible result that should
stop a computation before it's trusted, not after. Converting the wage to a daily rate (South
Africa's conventional 21.7 working days per month) before dividing fixed it: 0.1058, in the same
order of magnitude as the published comparators. The fix assumes job-search travel costs recur
at roughly a daily rate when they happen at all -- not verified against a job-search-specific
frequency question, because none exists in this survey, and stated as an assumption rather than
buried in a default.

**The wage benchmark comes from NHTS itself, in 2020 Rand, not a more recent QLFS figure.**
Mixing a 2020 transport cost with a 2025/26 wage would need an inflation adjustment this notebook
has no reason to introduce; using NHTS's own `Q410Salary` keeps both sides of the ratio on one
survey and one year. The whole moment is therefore in 2020 terms -- a real limitation, not
smoothed over, and one the Calibration chapter needs to name directly.

**Standard error is bootstrapped, not closed-form.** The ratio combines two independently
estimated quantities -- mean cost over 4,655 travellers, median wage over 20,867 earners -- so
2,000 weighted resamples of both populations give 0.1058 +/- 0.0055 (95% CI 0.097-0.119) without
needing to assume away the covariance a delta-method formula would have to ignore.

This is now the second-most fragile moment after the SA separation rate still to come in
notebook 03 (which needs its own panel construction). Flagged here explicitly should D7's
provisional-at-freeze rule ever need to apply to it.

## Week 3, notebook 03 -- long_term_share (clean), and the SA separation rate no longer needs Miyamoto's fallback

`long_term_share` was the easy one, same pattern as `discouraged_share`: QLFS's own
`Long_term_unempl` classifies the currently unemployed as long-term or short-term directly, no
reconstruction needed. Four most recent quarters run 76.6 to 79.7 per cent with no clear trend
(unlike `discouraged_share`'s), so the headline value is the most recent quarter by the same
convention as notebook 01: **77.44 per cent, +/- 0.54pp**. A number this high is not a red flag
on its own -- South Africa's long-term unemployment share is well documented as one of the
highest in the world; this is corroborating, not surprising.

**The separation rate was the one flagged as a possible fallback, and it turned out not to need
one.** M1's spec: compute it from QLFS/PALMS panel transitions, keep Miyamoto (2011)'s Japanese
0.0048 monthly only "if the SA rate is not computable by end of week 3." PALMS's household and
person identifiers are only meaningful within a single survey wave, not automatically across its
30-year harmonised span (the same caution already applied to NHTS and QLFS variable identifiers
in notebooks 01 and 02) -- but the raw QLFS quarterly files carry `UQNO` and `PERSONNO`, and QLFS
is a genuine rotating panel: linking 2025 Q2 to Q3 by those two fields recovers 43,796 matched
individuals out of 65,443, a real ~67 per cent retention, not a coincidence at that scale.

Method: for each of the three available consecutive quarter-pairs, take everyone matched in both
quarters who was `Employed` in the first, and check whether they still are in the second. Pooled
across all three pairs (every matched employed person is one observation in one weighted mean,
not three separately-averaged rates): **9.21 per cent quarterly**. Rebased to monthly with the
same compounding convention already used for `rho_A` (`(1 - monthly)^3 = (1 - quarterly)`, see
the AR(1) note above) gives **3.17 per cent monthly (95% CI 3.06-3.29pp, bootstrapped)** --
roughly 6.6x Miyamoto's Japanese figure.

That gap is large enough to deserve a second opinion before trusting it, so it got one:
StatsSA's own published QLFS panel transition statistics (statssa.gov.za/?p=19090) report 91.8
per cent quarterly employment retention for 2024 Q3->Q4 (an 8.2 per cent separation rate that
quarter) and 94.0 per cent for 2019 Q3->Q4 (6.0 per cent). This notebook's 9.21 per cent for
2025-26 sits close to, and slightly above, StatsSA's own 2024 figure -- consistent with the
deteriorating labour market `discouraged_share` already showed over the same window, not an
outlier result. A 6.6x gap from Miyamoto's number is not itself surprising: Japan is close to
the global floor on labour turnover, so any other country reading several times higher than it
is the expected pattern.

**Deliberately not yet written into any config file.** `configs/baseline.yaml`, `trace_demo.yaml`
and both `scarce_vacancies*.yaml` configs were all built and validated this session under
Miyamoto's 0.0048 -- `trace_demo.yaml`'s specific seed/agent pair (seed 5, agent 32) was found by
scanning under that exact economics, and the scarce-vacancy smoke test's `n_agents=18,000`
threshold is specific to it too. Swapping in 3.17 per cent now, mid-Week-3, would silently
invalidate both without a re-check. The rate is computed, checked against an independent source,
and recorded in the notebook; adopting it into the configs is deliberately left for Week 4,
alongside the rest of the calibration setup, where those two artefacts get re-verified as
planned work rather than as an unplanned casualty of this notebook.

## Week 3, notebook 04 -- distance_gradient_slope, and the fourth moment is real

The last of the four -- documentation and unit reconciliation, not a computation, since no
survey on disk reports employment binned by kilometre-distance (confirmed in the literature
verification). Baez and Kshirsagar (2026) Table 5b reports three separate, city-specific
coefficients -- Johannesburg 4.9, Cape Town 3.7, eThekwini 6.5 pp employment-share drop per
10-percentile increase in travel-time rank -- not one number, and the model is a single
stylised city, not any specific metro among the three. The mean, 5.03, is used rather than
picking one city arbitrarily.

The source paper's own standard errors for these coefficients weren't recoverable in this
environment (no PDF-rendering tool available to read the working paper's actual table), so
`moments.csv`'s `standard_error` for this row is the cross-city sample standard deviation
(1.40) -- real city-to-city heterogeneity, not a sampling error, and labelled as exactly that
in both the notebook and the `source` column rather than left to be mistaken for one.

All four moments in `moments.csv` are now real, non-provisional numbers: `discouraged_share`
13.43%, `transport_budget_share` 10.58%, `long_term_share` 77.44%, `distance_gradient_slope`
5.03. D7's provisional-at-freeze rule has nothing left to apply to when Week 4 calibration
begins.

## matching.py, the first SQ1 number, and a real problem it surfaced

`src/matching.py` implements the CRS-testing spec exactly as written above: the unconstrained
`log m = log a + b_u log u + b_v log v` fit first, a Wald test of `b_u + b_v = 1`, then the
CRS-constrained `a` as the headline number only once that test has actually run. Validated
against synthetic data generated from a known Cobb-Douglas matching function with a known
degree of returns to scale, not just checked to run -- the noiseless case recovers the exact
parameters to six decimal places, and the Wald test correctly rejects a synthetic dataset built
with genuine increasing returns (`b_u + b_v = 1.3`) while not rejecting one built with genuine
constant returns.

**The Wald test uses Newey-West (HAC) standard errors, not ordinary OLS ones** -- this is the
answer to the "why autocorrelation matters" Week 3 gate question, implemented, not just
recited. `u_t`, `v_t` and `m_t` are one run's own time series, evolving smoothly period to
period rather than drawn independently; treating consecutive periods as iid observations (what
plain OLS does) understates the true standard errors and makes the test overconfident. Lag
count follows Newey and West's own automatic rule, `floor(4*(T/100)**(2/9))`, not a number
picked by eye. Re-ran the SQ1 sweep below after adding this -- the point estimates and `delta_a`
figures are unchanged (HAC only changes standard errors, not coefficients), and the CRS
rejection counts moved by at most one seed out of twenty in either arm.

`configs/frictionless.yaml` is `baseline.yaml` with `transport_cost_rate` set to 0 and nothing
else changed -- population, firms, wealth heterogeneity and the AR(1) shock held fixed, since
SQ1 asks what removing the spatial-friction channel does at a fixed population, not what a
different population does. Twenty common seeds, both configs, matching function fitted on each
run's post-burn-in window, per-seed paired difference `delta_a = a(friction) - a(frictionless)`.

**The number came back near zero and uninformative, and the reason why is the actual finding.**
`a_constrained` sits at almost exactly 1.0 in both arms for the large majority of seeds --
mean `delta_a = -0.0025`, 95% interval `[-0.025, +0.009]`, which contains zero. Digging into
why: at `baseline.yaml`'s default population (500 agents), the labour market is heavily
vacancy-abundant (theta ~= 9.85, established while designing the scarce-vacancy smoke test
earlier this session) -- close enough to "every unemployed searcher who trips gets hired" that
matches track unemployment almost exactly regardless of whether transport costs exist. The fit
sits in a **degenerate corner** (`b_u ~= 1`, `b_v ~= 0`) where vacancies carry almost no
measured elasticity, not a genuine, well-identified Cobb-Douglas interior point -- and a
matching-efficiency comparison computed at a population where vacancies don't matter cannot
detect an effect that operates through vacancy scarcity, whatever the true effect actually is.
Confirmed this isn't specific to 500 agents: sweeping population up (the same sweep that found
the scarce-vacancy threshold) shows the model transitioning to the *opposite* degenerate corner
(`b_u ~= 0`, `b_v ~= 1`, matches tracking vacancies instead) around 18,000 agents, with a
genuinely ill-behaved zone in between (10,000-15,000 agents) where the Wald test correctly
rejects constant returns -- real increasing returns to scale, not noise (`b_u + b_v` up to 1.59).
There may be no population at which this model's matching technology is well-approximated by a
stable, non-degenerate Cobb-Douglas form with both elasticities economically meaningful at once.

This is exactly what "what population the SQ1 interval is over" (the Week 3 gate question) is
asking, and the honest current answer is that the population choice used here is the wrong one
for a headline result -- not because anything is broken, but because it sits in a regime where
the measurement is structurally insensitive to the thing being measured. Flagged for Week 5's
full validation, not resolved here: the population scale for the real SQ1 comparison needs
choosing with this corner-degeneracy in mind, and the model's matching technology's departure
from constant returns in the 10,000-15,000 range is itself worth understanding mechanistically
before it's papered over with a CRS constraint that doesn't hold there.

## Week 4, calibrate.py -- the MSM engine, D12 and M9 implemented exactly as specified

Four free parameters against the four moments in `data/moments.csv`: `search_cost_per_trip`
(c), `initial_search_capital` (W0), `firm_radius` (rho), `firm_kappa` (kappa) -- prompt 4.2's
own list, unchanged. Exactly identified, no slack for a formal overidentification check; the
out-of-calibration validation against Banerjee and Sequeira's null result is the substitute, as
M9's own note already said before this file existed.

**The weight matrix is inverse (data SE^2 + simulation variance), not data variance alone** --
M9's correction, implemented rather than left as a note for later. Simulation variance is
estimated directly from the spread of the 15 common-random-number seeds at each evaluation
(variance of the mean, not the raw per-seed spread), never assumed negligible.

**D12's common random numbers**: `CALIBRATION_SEEDS` (15, `config.py`) reused at every
evaluation during both the Latin hypercube and Nelder-Mead stages, so the loss is a
deterministic function of the parameters -- tested directly (`test_msm_loss_is_deterministic_at_a_fixed_parameter_vector`),
not just asserted. `VALIDATION_SEEDS` (50, disjoint) is used once, at the reported optimum
only, so the fit quality shown was never available to the optimiser to fit to.

**Caching required a second cache flavour, not a reuse of the first.** `runner.py`'s existing
`run_cached`/`run_many` cache the raw history DataFrame, but `distance_gradient_slope` is
cross-sectional and reads the *live* `CityModel`'s final agent states directly -- a pickled
history alone can't reconstruct that, and a calibration run needs thousands of (config, seed)
evaluations, each producing only four floats worth keeping. `run_moments_cached`/
`run_moments_many` cache the *computed moments* (a small JSON dict) per (config, seed) instead,
computed at the point where both the model and its history still exist. This also required
adding `src/moments.py` to `runner.py`'s source fingerprint, which previously covered only
`agents.py` and `model.py` -- an edit to `moments.py`'s own logic wouldn't have invalidated a
stale moments cache otherwise, a real correctness gap caught while building this, not before.

**Validated by parameter recovery, not just by running.** `test_recovers_a_known_parameter_vector`
(marked `slow`) simulates "empirical" moments from a known parameter vector on a small config,
feeds them back in as the calibration target, and confirms the LHS+Nelder-Mead engine finds its
way back to within 35 per cent of each parameter's search-box width -- the same "recover a known
answer" standard as `dmp.py`'s Chen recovery and `matching.py`'s synthetic-data tests, applied to
the optimiser itself rather than to a closed-form fit.

## The identification logic, and where the real weak spots are

Prompt 4.2 asks for this explained, not just the calibrated numbers handed over.

**`firm_radius` (rho) identifies `distance_gradient_slope` most directly** -- it's the literal
parameter controlling how far a firm's hiring catchment reaches, so it's the most direct lever
on how much distance from the CBD matters for employment odds.

**`firm_kappa` (kappa) identifies `long_term_share` most directly** -- it scales how
aggressively firms convert expected profit into posted vacancies, which is the parameter that
actually governs vacancy *supply*. A smoke test at `configs/baseline.yaml`'s default parameters
(before any calibration) found `long_term_share` simulating at exactly 0.0000 against an
empirical target of 77.44 per cent -- the same vacancy-abundant corner degeneracy already found
in the matching-function analysis above, this time showing up as a calibration problem rather
than a measurement problem: baseline's `firm_kappa=0.9` posts so many vacancies that almost
nobody's search spell survives long enough to become long-term. A 20-point LHS-plus-Nelder-Mead
smoke test (not the full campaign) pushed `firm_kappa` up to 1.26 and `initial_search_capital`
up to 1.13, which brought `long_term_share` from 0.0000 to 0.56 against the 0.77 target -- real
progress, not a full fix.

**`search_cost_per_trip` (c) and `initial_search_capital` (W0) are the acknowledged weak spot.**
Both move affordability in the same direction -- more capital or a cheaper trip both mean more
searching before capital exhaustion -- so `discouraged_share` alone can't cleanly separate them;
what identifies them apart is their *differential* effect on `long_term_share` (W0's absolute
level matters for how long a spell can run) versus `transport_budget_share` (c enters that
moment directly, W0 doesn't). The smoke test's own result illustrates the tension this creates:
pushing W0 up to help `long_term_share` pulled `transport_budget_share` down to 0.036 against a
0.106 target, worse than baseline's own 0.107 fit -- moving one parameter to fix one moment
visibly cost fit quality on another, exactly the trade-off an exactly-identified system can't
avoid when the moments pull in different directions.

**`distance_gradient_slope` stayed almost entirely unexplained in the smoke test, and that's
itself informative.** `firm_radius` was pushed to its lower search bound (1.1, against a 1.0-6.0 box)
without getting anywhere near the 5.03 target, and the simulated value even came back with the
wrong sign (-0.10). At `firm_radius` this small, on a 40-unit grid with townships 8-20 units from
the CBD, very few search trips ever land inside any firm's catchment at all -- so few completed
hires that the cross-sectional employment-by-distance regression is likely running on a handful
of noisy observations, not a real signal. This is a boundary problem worth investigating before
trusting the full campaign's `firm_radius` estimate, not a parameter search issue to just widen
the bounds on and hope disappears.

## The full campaign confirms the smoke test, and this is not yet a usable calibration

Ran the real thing after the smoke test: 200 LHS points, 179 Nelder-Mead evaluations, 50
validation seeds at the optimum, `configs/baseline.yaml` as the base -- roughly 19 minutes wall
clock, in line with the throughput measured during the smoke test (0.226s per individual seeded
run, slightly better than D4's own 0.332s benchmark).

```
calibrated parameters:
  search_cost_per_trip = 0.029485
  initial_search_capital = 1.458701
  firm_radius = 1.156804
  firm_kappa = 1.608181

moments at optimum (validation seeds, n=50):
  distance_gradient_slope: simulated=-0.3279 (se=0.0918)  empirical=5.0333 (se=1.4048)
  discouraged_share:       simulated=0.1848 (se=0.0198)  empirical=0.1343 (se=0.0023)
  transport_budget_share:  simulated=0.0649 (se=0.0117)  empirical=0.1058 (se=0.0055)
  long_term_share:         simulated=0.5095 (se=0.0527)  empirical=0.7744 (se=0.0054)
```

**Two of the four bounds are actively binding.** `initial_search_capital` landed at 1.459
against a 0.2-1.5 box -- 3 per cent from the wall. `firm_radius` landed at 1.157 against a
1.0-6.0 box -- 16 per cent from the wall, and pinned in the same direction as the smoke test's
independent 20-point run (1.105 there). An optimiser parked at its own box constraint has not
found an interior optimum; it's reporting that the box was drawn in the wrong place. This is not
a converged calibration result and shouldn't be read as one -- it's the engine's first real
diagnostic pass, and what it diagnoses is that `DEFAULT_BOUNDS` needs revisiting, specifically
widening `initial_search_capital`'s ceiling and considering whether `firm_radius` should be
allowed smaller than 1.0, before the next attempt.

**`distance_gradient_slope` is still the moment this model structurally cannot fit at these
settings.** Wrong sign, small magnitude, exactly as the smoke test found -- consistent evidence
across two independent searches that this isn't sampling noise. Widening `firm_radius`'s lower
bound might let the optimiser find a smaller value, but the mechanism already suspected above
(too few trips land in any firm's catchment for the cross-sectional regression to have a real
signal at small radius) predicts that going smaller makes this moment *harder* to fit, not
easier -- in which case the fix isn't a wider search box, it's diagnosing why the model's spatial
mechanism doesn't reproduce this specific empirical pattern at all before spending more
optimiser time on it.

**What Week 4 actually delivers**: a calibration engine that's built, tested against known
synthetic answers, and run once at full real scale without crashing or behaving
non-deterministically -- and an honest, evidence-backed diagnosis of what's wrong with the first
attempt, rather than a declared "calibration complete" sitting on top of two bound violations and
an unfit moment. Fixing the bounds and diagnosing `distance_gradient_slope` are next session's
first two items, not swept into a claimed result here.

## The catchment-access guess above was wrong -- the real mechanism is an employment ceiling, and it explains the weight imbalance too

Checked directly rather than left as a guess, the way every other mechanism claim in this file
has been. Running the model at the calibrated point (`search_cost_per_trip=0.0295`,
`initial_search_capital=1.459`, `firm_radius=1.157`, `firm_kappa=1.608`) and inspecting the
actual run: 496 of 500 agents are `EMPLOYED` at the final step, and the employment count reaches
roughly that level by step 16 and stays there for the remaining 134 steps
(`l` sits at 493-496 from step 16 onward, `u` at 1-4). Splitting the final population into
distance quartiles: 100.0 per cent employed in the nearest quartile, 98.4 per cent in the
farthest -- a real difference, but far too small and far too close to a ceiling for a percentile-
rank OLS fit to read as a stable slope rather than noise from whichever handful of agents happen
to be the ones still unemployed. The "too few trips land in any firm's catchment" guess in the
entry above was plausible-sounding and wrong; the actual problem is the opposite failure mode --
almost everyone gets hired almost immediately at these parameters, so there's next to no
cross-sectional variation left by the time `distance_gradient_slope` takes its snapshot.

**This also explains why `firm_radius` drifted to a boundary in the first place, and it isn't
really about `firm_radius` at all.** Computing each moment's actual loss weight at the reported
optimum: `distance_gradient_slope` carries a weight of 0.50; `discouraged_share`, 2,517;
`transport_budget_share`, 5,983; `long_term_share`, 356 -- `distance_gradient_slope` counts for
somewhere between 700 and 12,000 times less than the other three, because Baez and Kshirsagar's
own cross-city dispersion (used as the uncertainty proxy in notebook 04, since the source
paper's real standard errors weren't recoverable) is enormous next to the other moments' tight
survey-based standard errors. M9's weighting is implemented correctly -- this is what inverse-
variance weighting is *supposed* to do with a target this uncertain -- but the practical
consequence is that the optimiser has almost no reason to care what `firm_radius` does to
`distance_gradient_slope` at all, and moves it only insofar as it happens to affect the other
three moments through some other channel. A parameter search box being pinned near its edge
looked like a real finding about `firm_radius`; it's actually a symptom of one moment's weight
being negligible, which is a different problem with a different fix.

**The honest version of "exactly identified, four parameters, four moments" needs a caveat now.**
If one moment's weight is functionally near zero, its corresponding parameter isn't really being
pinned down by the calibration in practice, whatever the parameter count says on paper. Either
`distance_gradient_slope` needs a tighter, better-grounded uncertainty than a three-city sample
standard deviation before it can carry real identifying weight, or the model chapter needs to
say plainly that `firm_radius` is under-identified by this moment set as currently weighted --
one of the two, not left implicit. Worth deciding before the bounds get widened and the campaign
re-run, since widening `firm_radius`'s box won't fix a parameter the loss barely responds to.

## A third door into the same deadlock class, and the actual fix to the saturation problem

Asked to investigate the firm posting mechanism before assuming the population scale needed to
change (the population-increase option was the other one on the table). That investigation
found two separate things -- a real bug, and, once the bug was out of the way, the actual reason
this model saturates near full employment regardless of how the four free parameters are tuned.

**The bug.** Sweeping `firm_kappa` down towards its lower bound (0.2) to see whether a genuinely
scarce, non-saturated regime existed anywhere in the search box produced total market collapse
instead: `u` stuck at 500 of 500 for the entire run, `v` near zero throughout, `m` exactly zero
throughout. Tracing it step by step: at `firm_kappa=0.2`, every firm's own computed vacancy
target rounds to zero on the very first step (the naive fill-probability prior, floored at 0.05,
isn't enough to clear the rounding threshold at this `kappa`), so `v_1 = 0`. With 607 agents
making trips that period on their naive initial belief and zero vacancies to hire into,
`observed_hire_rate_per_trip` updates to `m_t / total_trips = 0 / 607 = 0.0` -- a real
observation (total_trips was positive, not a quiet step), so the Week 1 guard ("don't reset the
belief on a quiet step") correctly lets it through. Once the shared belief is exactly 0.0, every
agent's `decide_trips` computes zero desired trips simultaneously, `total_trips` stays at 0
forever after, and the belief -- correctly left unchanged on what is now a genuinely quiet step
-- never gets another chance to update. A third, independent door into the same "a multiplicative
belief can reach an absorbing exact zero" bug class already fixed twice this session (the
model-level initial-zero deadlock in Week 1, the firm-level `fill_prob_estimate` decay and the
population-scaling `decide_trips` freeze in Week 2), this time triggered by a legitimately-bad
first period rather than a bad prior or a scaling effect. Fixed the same way as the firm-level
case: floored `observed_hire_rate_per_trip` at `MIN_OBSERVED_HIRE_RATE_PER_TRIP = 0.005`
whenever it updates, not just at its initial value -- small enough not to distort a normal run
(baseline's own naive initial value is over an order of magnitude larger) but enough to keep the
door open for a later period's real vacancy supply to correct the belief. Confirmed the fix
against a stash of the pre-fix `model.py`: `test_observed_hire_rate_never_decays_to_exactly_zero`
fails on the stashed version (`0.0 >= 0.005`) and passes with the fix. One pre-existing test
(`test_extreme_scarcity_produces_a_fully_censored_long_spell`) started failing after this fix --
not a regression in the mechanism it checks (n_long_term still peaks at 286 of 300 agents
mid-run in that scenario), but a fragile assertion on the run's *final* step of a genuinely
cyclical process, which this fix's changed timing happened to catch on a downswing. Fixed to
check the run's peak instead of its last step, which is what the test's own docstring already
said it was trying to confirm.

**What the bug fix revealed, once it stopped masking the real question.** With the deadlock out
of the way, `firm_kappa=0.2` converges to almost the *same* near-total-employment steady
state as every other value tried across the 0.2-2.0 box -- meaning `kappa` was never actually the
parameter determining whether this model saturates. `expected_value_per_hire =
(firm_productivity * shock - WAGE) / (discount_rate + separation_rate)` is approximately 32.6 at
baseline's parameters, and that number is almost entirely driven by the tiny denominator
(`0.001332 + 0.0048`), not by `kappa`. Every `kappa` in the search box multiplies the same huge
base value, so the model has an enormous structural incentive to fill jobs no matter how the
free parameters are tuned. Testing this directly: swapping in Week 3's own already-computed real
SA separation rate (3.17 per cent monthly, notebook 03 -- still sitting un-adopted in
`configs/baseline.yaml` as Miyamoto's 0.48 per cent Japanese fallback, deliberately deferred at
the time to avoid invalidating `trace_demo.yaml` and the scarce-vacancy threshold mid-week)
drops `expected_value_per_hire` to about 6.05 -- a 5.4x reduction -- and produces a genuinely
moderate, persistent labour market at baseline's own `firm_kappa=0.9`: unemployment settling
around 8-15 of 500 agents (1.6-3 per cent) with a substantial, *persistent* discouraged
population (roughly 20 per cent), not the near-total saturation found throughout this session's
calibration attempts. This is the actual fix the calibration needs -- not wider bounds on the
four free parameters, which were never going to reach a regime the structural economics rule out
entirely, but the separation rate this project already computed and correctly held back from a
premature mid-week adoption. Adopting it now, with the re-checks that were always attached to
that decision, is next session's first item, ahead of re-running the campaign.

## The real separation rate, adopted, and both re-checks it was waiting on both came back clean

`configs/baseline.yaml`'s `separation_rate` is now Week 3's own QLFS-panel SA rate (3.17 per
cent monthly), not Miyamoto's Japanese fallback. Confirmed directly: the updated config settles
into 2.55 per cent mean unemployment and a 23.3 per cent discouraged share over the last 30 per
cent of a run -- the same order of magnitude as the real `discouraged_share` target (13.43 per
cent) this project is trying to calibrate to, not the near-zero saturation the old rate produced.

**`trace_demo.yaml`'s re-check.** Agent 32 under seed 5 no longer lives through exactly five
cycles -- under the new economics it's a long stable employment spell (steps 15 to 83), then
three tighter discouraged/re-entry cycles, and the run ends with the agent employed. Still a
clean demonstration of locked commitment 6; the figure was regenerated and looks as clear as
before.
Not re-scanned for a different seed/agent pair, since this one still does the job -- the
config's header comment now describes the actual trajectory rather than the original "five full
cycles" count, which stopped being accurate the moment the separation rate changed.

**The scarce-vacancy smoke test's re-check.** `configs/scarce_vacancies.yaml` and its subsidy
arm now use the same real separation rate. Checked whether the population threshold that made
this config vacancy-saturated still holds, rather than assuming it does: at `n_agents=18,000`,
`fill_ratio` is still exactly 1.00, and `theta` is now *lower* than before (0.013 versus the
original 0.19) -- firms post far fewer vacancies overall at the smaller `expected_value_per_hire`,
so the same population is, if anything, more decisively scarce than it was. Re-ran the full
five-seed comparison rather than trusting the old numbers: search intensity still rises on every
seed (+1.5 to +15.0 per cent), vacancies and matches barely move (26.2 to 27.3, +4.3
per cent), and unemployed count rises sharply (+34.7 to +41.5 per cent) -- the Banerjee-Sequeira
sign pattern, if anything more decisive than the original finding. Employment moved up slightly
more this time (mean +4.1 per cent across seeds, versus close to flat before) -- still small next
to the intensity and unemployment movements, and worth noting rather than rounding away, since a
future reader comparing this entry to the original smoke-test numbers should be able to see
exactly what changed and why, not just a bare "still holds."

## The re-run campaign: real progress, one moment still in genuine tension with the others

Re-ran the full 200-point campaign against the corrected `baseline.yaml`. Real, measurable
improvement over the first attempt: **no bound is pinned this time.**
`search_cost_per_trip=0.0177`, `initial_search_capital=1.422`, `firm_radius=4.827` and
`firm_kappa=1.574` all land inside their search boxes, not at a wall -- an actual interior
optimum, not an optimiser reporting that the box was drawn wrong. Two of the four moments fit
well: `discouraged_share` simulates at 0.1281 against an empirical 0.1343 (0.6pp off), and
`transport_budget_share` simulates at 0.1103 against 0.1058 (0.5pp off) -- both a large
improvement on the first attempt's 0.1848 and 0.0649.

**`long_term_share` still simulates at exactly 0.0000, and this time the mechanism is clear,
not just described as clear.** Inspecting the model at these exact parameters: mean unemployment
(`u`) sits at only 13 agents, while mean hard-discouraged count sits at 72-92 -- `discouraged_share`
is being fit almost entirely through the hard-discouragement channel, not through people staying
in active search. With `firm_radius` nearly doubled from baseline's 2.5 to 4.827, an agent who
re-enters `SEARCHING` gets matched quickly once they do, so `months_in_state` rarely has the
chance to reach the 12-month `long_term_share` threshold before the spell ends one way or the
other. The empirical target asks for both a large discouraged population *and* long spells among
the (much smaller) group still actively searching -- two properties that, in this model's actual
mechanics, currently pull against each other rather than being independently tunable: a
`firm_radius` large enough to help `transport_budget_share` and `discouraged_share` fit well is
also large enough to keep searching spells short.

**`distance_gradient_slope` is still unfit (-1.52 against an empirical 5.03), still the wrong
sign.** Consistent with the earlier diagnosis that this moment's own weight is functionally
negligible (roughly three to four orders of magnitude below the other three) given
`distance_gradient_slope`'s own large cross-city-dispersion uncertainty -- the optimiser has
little reason to care what `firm_radius` does to this moment specifically, and moved it to 4.827
for reasons connected to the other three moments, not this one.

**Where this actually leaves Week 4.** A materially better calibration than the first attempt --
an interior optimum, two moments fitting closely -- but not yet a usable one, and said plainly
rather than rounded up to "done." The obvious next guess was tested directly rather than left as
a guess: does `reentry_threshold` (currently fixed at baseline's 0.035, not one of the four free
parameters) decouple the two moments, since it governs the `DISCOURAGED` -> `SEARCHING`
transition? Swept it from 0.035 to 0.3 at the calibrated point: `long_term_share` stays at
exactly 0.0000 throughout, while `discouraged_share` moves *away* from its target (0.1446 up to
0.2952) as `reentry_threshold` rises. `reentry_threshold` was the wrong lever -- it governs how
easily an agent re-enters search, not how long a search spell survives once re-entered.
`long_term_share` needs months_in_state to reach 12 *while actively searching*, and at
`firm_radius=4.827` an agent who does re-enter gets matched again quickly, so the spell ends
long before 12 months regardless of how the discouragement side is tuned. The real tension is
between `firm_radius` large enough to help the other three moments and `firm_radius` small
enough to let a search spell actually run long -- narrower and more specific than "a fifth
parameter might be needed," and the next thing to test directly rather than guess at.

## An independent verification on 17 August found the frictionless config drifted, and it invalidates delta_a=-0.0025

An independent verification pass over this repository, run on 17 August 2026 before any Week 5
work started, found that `frictionless.yaml` had drifted out from under its own stated purpose.
Its header comment still read "identical in every field except `transport_cost_rate`," but its
`separation_rate` had been left at Miyamoto's Japanese fallback (0.0048) through the session
that moved `baseline.yaml` onto the QLFS-derived SA rate (0.0317, see "The real separation
rate, adopted..." above). Nobody edited `frictionless.yaml` in that session because nothing told
them to -- the two files are supposed to be identical apart from one field, so a change to one
should have meant an identical change to the other, and didn't.

That means every `delta_a = a(friction) - a(frictionless)` computed since then, including the
`mean delta_a = -0.0025`, 95% interval `[-0.025, +0.009]` reported above, compared two economies
that differed in **two** channels at once: transport cost, which SQ1 is actually about, and
separation rate, which changes `expected_value_per_hire` and therefore the entire vacancy-posting
regime (see "A third door into the same deadlock class..."). A near-zero, CI-straddles-zero
result computed under a confound isn't evidence of anything -- it's exactly what a shared, silent
bug looks like. **The `-0.0025` figure above is invalidated by configuration drift, not by a
finding about matching efficiency, and is kept here as a labelled failed result rather than
deleted.** `frictionless.yaml` is now resynchronised to `baseline.yaml`'s separation rate, and
`tests/test_configs.py` asserts the two files can never diverge on anything but
`transport_cost_rate` again -- this specific silent-drift failure mode gets a regression test,
the same discipline applied to every other bug class in this project.

The audit's independently measured constrained matching efficiencies at seed 42 make the size of
the confound concrete: `0.963283` for `baseline.yaml`, `1.000000` for the committed (stale)
`frictionless.yaml`, and `0.953347` for a frictionless config corrected to match baseline's
separation rate -- and that corrected run rejects constant returns at the five per cent level,
which the stale comparison's near-1.0 both-arms reading had been masking. SQ1 is rebuilt properly
in a later stage of this remediation (Task 7 of the verification plan), with paired seeds and a
CRS gate that refuses to report a constrained `delta_a` when either arm's returns-to-scale
assumption fails; this section exists so the superseded number stops circulating as if it still
meant something.

## An independent verification found distance_gradient_slope's sign and dating both wrong

The same 17 August audit found a second, separate error in `distance_gradient_slope`: notebook
04 recorded the magnitude of Baez and Kshirsagar's three city coefficients but dropped the
sign, storing `+5.0333` in `data/moments.csv` when Table 5b's own coefficients are all
negative -- a higher travel-time-rank percentile (further from the business district) *lowers*
employment share, it doesn't raise it. Confirmed directly against the source PDF rather than
trusting the earlier transcription (`pypdf` text extraction, page 39 of 50): the table's row
reads "Travel Time -0.49\*\*\* -0.46\*\*\* -0.37\*\*\* -0.21\*\*\* -0.65\*\*\* -0.65\*\*\*" under
"Table 5b: Spatial Correlates of Share of the Adult Population Employed." The row's `period`
was also wrong -- "2026," the paper's publication year, when the underlying regression links
2011 census sub-place geography (the latest South African census available at that level) to
spatial tax employment data. Both are fixed: `data/moments.csv` now records `-5.0333` dated
`2011`, and `tests/test_empirical_moments.py` asserts the sign, the period and the presence of
a `Table 5b` citation so this specific transcription error can't recur silently.

**This changes the diagnosis, not just the number.** Every place in this file that described a
simulated `distance_gradient_slope` as having "the wrong sign" was comparing against the
wrong-signed target -- the model's own output was negative throughout, which means it had the
*right* sign against the *correct* target all along, just short of the target's magnitude. Three
specific claims above are superseded by this correction:

- "Week 3, notebook 04 -- distance_gradient_slope, and the fourth moment is real" records the
  value as `5.03` with no sign discussion -- correct as a description of what the notebook
  computed at the time, now superseded by the corrected `-5.0333`.
- "The full campaign confirms the smoke test..." describes `firm_radius` pinned at its lower
  bound with a simulated value "com[ing] back with the wrong sign (-0.10)," and the printed
  block immediately below it records `empirical=5.0333`. Both the prose and the console
  output reflect the pre-correction target; against the corrected `-5.0333`, `-0.10` has the
  *same* sign as the target, just a small fraction of its magnitude -- the boundary/noisy-
  regression diagnosis in that section is unaffected by this correction and still stands.
- "The re-run campaign: real progress..." describes `distance_gradient_slope` as "still unfit
  (-1.52 against an empirical 5.03), still the wrong sign." Against the corrected target,
  `-1.52` is the right sign at roughly 30 per cent of the target's magnitude -- unfit, but not
  for the reason stated. The section's separate finding (this moment's loss weight is three to
  four orders of magnitude below the other three, so the optimiser has little reason to move
  `firm_radius` for this moment's sake) is the real explanation and is unaffected by this
  correction.

The console blocks recording literal program output (`empirical=5.0333` and similar) are left
as printed, not edited, since they are a record of what the code actually produced at the time
-- the surrounding prose is what carried the wrong interpretation, and that's what this section
corrects. Task 8 of the verification remediation plan reruns the full calibration campaign
against the corrected target; whatever it reports there supersedes the specific numbers above
regardless of this sign correction.

## transport_budget_share and its NHTS target were measuring two different things

The same 17 August audit found that `transport_budget_share()`'s simulated moment and its NHTS-
derived empirical target were never the same estimand, even though both had been landing near
0.08-0.11 and looking like a fit. The empirical side (notebook 02) is conditional and daily on
both sides: mean transport cost among the 4,655 NHTS respondents who actually reported travelling
while job-hunting on a given day, divided by a daily wage equivalent (median monthly wage /
21.7). The old `transport_budget_share()` was monthly and unconditional: total transport spend
in a period divided by the *entire currently-unemployed stock* `u`, including every agent who
made zero trips that period, then compared to the full monthly wage. Comparing a conditional
daily ratio to an unconditional monthly one and getting similar numbers back was coincidence, not
agreement -- the two formulas measure different objects at different time scales and there is no
reason their point estimates should land near each other except by chance.

**The fix makes both sides the same estimand.** `transport_budget_share()` now sums transport
spend and effective search trips separately across the window, divides total spend by
(total trips times the daily wage), and returns `nan` rather than a false zero when the window
contains no trips at all -- see `src/moments.py` and the hand-calculated fixtures in
`tests/test_moments.py` (one trip, several trips in one period, an all-zero window, and a mixed
window with some zero-trip periods interleaved, confirming the ratio depends only on total spend
and total trips, not on how activity is distributed across periods). This is a genuine
conditional, daily, per-trip cost share, the same object the empirical side computes -- not the
previous per-searcher monthly average.

**`search_cost_per_trip` already meant the right thing, so the four-parameter calibration
survives unchanged.** The plan flagged a possible stop-and-decide point here: if
`search_cost_per_trip` were actually non-transport expenditure, NHTS's transport-only cost
couldn't identify it and the four-parameter/four-moment mapping would need rethinking.
Checked directly in `src/agents.py`: `cost_per_trip = search_cost_per_trip +
transport_cost_rate * distance_to_cbd` -- `search_cost_per_trip` is already the fixed
(distance-independent) component of a trip's transport cost, and `transport_cost_rate *
distance` is its distance-varying component. Total trip cost is therefore the correct model
analogue of NHTS's reported travel cost already; no redefinition of what the parameter means was
needed, and locked commitment 3's four-parameter, four-moment mapping stands.

**The size of the correction is the actual finding.** Run at `configs/baseline.yaml`'s current
(pre-Task-8) parameters across all 15 `CALIBRATION_SEEDS`: the old formula averaged 0.0754 across
seeds, close enough to the 0.1058 empirical target that the calibration campaign treated this
moment as reasonably well fit. The new, correctly-conditioned formula averages 1.5171 across the
same seeds and parameters -- roughly fourteen times the empirical target, not a small correction.
A large jump is expected and is itself evidence the old apparent fit was spurious: the model's
`WAGE=1.0` numeraire divided by `DAYS_PER_MONTH=21.7` gives a small daily wage (0.0461), so a
per-trip cost even a few cents above `search_cost_per_trip`'s calibrated range easily exceeds a
full day's wage once expressed as a share of it. Task 8 reruns the full calibration campaign
against this corrected formula; every other reported moment value for `transport_budget_share`
from before this commit, including the 0.1103/0.1058 "0.5pp off" reading in "The re-run
campaign," compared the old formula to the same target it was never actually measuring the same
thing as, and is superseded by whatever Task 8 reports under the corrected definition.

The wage-benchmark side of notebook 02 also carried an imprecise claim -- that converting the
monthly wage to a daily rate "assumes job-search travel costs recur at roughly a daily rate,"
which reads as a frequency assumption. It isn't one: the numerator is already conditional on a
travel day having happened (`Q47Travlooking == "Yes"`), and dividing the wage by 21.7 is a unit
conversion, not a claim about how many days a month job search actually happens. Reworded in the
notebook; the computed values (R20.96 mean daily cost, R4,300 monthly wage, 0.1058 point
estimate, 0.0055 bootstrap SE) are unchanged, since nothing about the empirical computation
itself was wrong -- only the model-side formula and this piece of the empirical-side prose were.

## The QLFS separation-rate linkage needed a demographic consistency check, and the design variables needed auditing before trusting a plain bootstrap

The 17 August audit's most consequential finding was in notebook 03, Part B. The raw
`UQNO`+`PERSONNO` panel linkage that produced the 3.17 per cent monthly separation rate now
adopted into `baseline.yaml` (see "The real separation rate, adopted...") contains implausible
matches: a household code reassigned to a different person between quarters (a new household
moving into a rotated-out dwelling, an enumerator data-entry slip, a genuine but rare within-
household `PERSONNO` renumbering) reads as a spurious "employment transition" under the raw
linkage, because the code has no way to tell a real transition from an identity error. Measured
directly rather than assumed: over the full matched population in each quarter-pair (not just
the employed subset), 314 gender mismatches and 735 implausible age changes (an age *decrease*,
or an increase of two or more years across a roughly three-month gap) in 2025 Q2->Q3; 222 and
521 in Q3->Q4; 214 and 516 in Q4->2026 Q1.

**The fix requires stable recorded gender and a plausible age change (zero or one year) across
each matched pair**, both fields every one of the four quarterly extracts carries. Restricted to
the employed-in-t0 population the separation rate is actually computed over: 94/212 (gender/age)
rejections out of 10,745 in Q2->Q3, 69/187 out of 10,822 in Q3->Q4, 66/177 out of 10,671 in
Q4->2026 Q1 -- attrition of 1.8 to 2.1 per cent per pair. `Q15POPULATION` (population group) is
also available and consistently coded across all four quarters, so it was checked for stability
the same way: 37, 17 and 33 additional mismatches per pair, under 0.3 per cent of the employed
subsample. Adding it as a third filter moves the pooled quarterly rate from 0.0861488108 to
0.0861345569 -- a change in the fifth decimal place, both rounding to the same 0.0296 monthly --
so it's reported for completeness but not applied: the frozen estimate below uses gender and age
only, the two checks that actually explain the correction's size.

**Pooled across all three pairs, the demographically-consistent quarterly rate is 0.0861488108**
(was 0.0921049673 under the raw linkage), rebasing to a **monthly rate of 0.0295827815** (was
0.0316956564) via the same compounding convention `rho_A` already uses. This is the central
estimate now written into `configs/baseline.yaml`, `frictionless.yaml`, `trace_demo.yaml` and
both `scarce_vacancies*.yaml` files as `0.0296`; the raw-link value (`0.0317`, unrounded
0.0316956564) is kept as a documented upper robustness bound, not the value any config uses.
Described in every config's header as "an approximate QLFS panel estimate," not "the official SA
separation rate" -- see the design-variable audit below for exactly what it can't reproduce.

**Design-variable audit, before choosing a resampling scheme.** Searched every one of the four
quarterly files' full column lists and their Stata variable labels -- a design variable can sit
under a name that doesn't say what it is, so names alone weren't enough -- for a rotation-group
indicator, a primary sampling unit (PSU), an enumeration-area/cluster code, or a wave indicator.
This extends the original audit, which checked only 2025 Q2: all four files carry `Stratum`/
`STRATUM` and nothing else design-related. `UQNO` is used only as the household identifier it's
documented to be (the linkage this notebook already relies on), never decoded for extra
structure it isn't documented to carry.

**The uncertainty estimate is now a household-cluster bootstrap, stratified by `Stratum`**, not
an individual-record bootstrap treating each matched person as an independent draw. Cluster
unit is (quarter-pair, `UQNO`) -- a household re-appearing in a later pair is a distinct cluster
each time it's matched, never double-counted as one unit across pairs. Each of 2,000 replicates
resamples, independently within every one of 248 strata, as many households as that stratum
actually contributes, then pools every matched person in the resampled households. Result:
quarterly bootstrap SE 0.001822, monthly bootstrap SE 0.000645, 95 per cent CI
[0.02837, 0.03086] -- close to, not dramatically wider than, what an (incorrect) individual-
record bootstrap on this same data would give, since the consistent sample averages only 1.33
matched people per household. **This still doesn't reproduce StatsSA's own published panel
non-response adjustment**, which needs rotation-group and PSU information neither this notebook
nor its four source files has access to -- stated as a limitation, not smoothed over, in both
the notebook and every config's header comment.

**Both re-checks the earlier separation-rate adoption required, redone for this rate too.**
`trace_demo.yaml`'s agent 32 was re-traced under 0.0296 rather than assumed unchanged from the
0.0317 version: exact state transitions (from `model.trace_dataframe()`) are SEARCHING at step
1, DISCOURAGED at 6, EMPLOYED at 15, DISCOURAGED at 24, EMPLOYED at 34, DISCOURAGED at 78 (a
roughly 44-step stable spell), EMPLOYED at 87, DISCOURAGED at 97, EMPLOYED at 107, DISCOURAGED
at 111, EMPLOYED at 121, running employed to the step-150 end -- five full discouragement/
re-entry cycles, still a clean demonstration of locked commitment 6, figure regenerated and
config header updated to describe this exact trajectory rather than the previous one.

The scarce-vacancy smoke test was re-run in full across seeds 1-5, not spot-checked. `fill_ratio`
is still exactly 1.00 in both arms on every seed -- vacancies remain the binding constraint, the
condition the sign pattern needs. Search intensity rises sharply on every seed (+43.1 to
+54.1 per cent, versus +1.5 to +15.0 per cent under the previous 0.0317 re-check -- a
substantially stronger signal, not a weaker one, under the lower rate). Vacancies and matches
barely move and in either direction (-5.4 to +4.5 per cent; they move identically to each other,
since a fill ratio pinned at 1.00 means matches are vacancies). Unemployed count rises sharply
(+41.2 to +48.9 per cent) and `theta` falls in the subsidy arm on every seed (from 0.0126-0.0177
down to 0.0084-0.0120). Employment moves by less than 5 per cent in either direction on every
seed (-4.9 to +4.1 per cent) -- small next to the intensity and unemployment movements, the
same "search intensity rises, employment barely moves" pattern Banerjee and Sequeira (2023)
document, and if anything more decisive here than in either of the two earlier versions of this
smoke test.

## The search-position draw oversampled the CBD centre, and it explains the flat firm_radius calibration region

The 17 August audit's sixth finding: at the reported calibrated values, changing `firm_radius`
from 4.1 to 6.0 produced identical simulation histories and identical moments at seed 42. The
cause was a sampling bug, not a genuine flat spot in the model's economics. `agents.py`'s
`search_positions()` drew a ticket's radius as `cbd_radius * belief_multiplier * U`, uniform
over the *radius*, while `model.py`'s firm placement already drew `cbd_radius * sqrt(U)`,
uniform over the disk's *area* -- the two draws that are supposed to describe the same
CBD-zone geography used different distributions. A uniform-radius draw packs samples near the
centre (mean radius `R/2`); a uniform-area draw doesn't (mean radius `2R/3`). Confirmed directly
with a 10,000-draw fixed-seed test before touching the fix: `test_search_positions_are_uniform_
over_the_cbd_disk_area_not_the_radius` measured a mean radius of 2.499 at `cbd_radius=5.0`
against the `R/2` value of 2.5, not the correct `2R/3` value of 3.333. Fixed to
`cbd_radius * belief_multiplier * sqrt(U)`, matching the firm draw; angle sampling and
`belief_multiplier`'s own role (scaling the radius for D2's targeting-bias mechanism) are
untouched.

**The consequence for `firm_radius` identification is geometric, not statistical.** With
`belief_multiplier=1` (D2's unbiased case), both search tickets and firms are now confirmed to
be drawn uniformly within the same disk of radius `cbd_radius` around the CBD, so no ticket-firm
pair can ever be more than `2 * cbd_radius` apart. A `firm_radius` at or beyond that diameter
makes every firm reachable from every ticket regardless of its exact value -- the calibration
loss stops responding to `firm_radius` at all past that point, which is exactly the flat region
the audit measured (4.1 and 6.0 both sit past `2 * 2.0 = 4.0`, `baseline.yaml`'s diameter).
`calibrate.py`'s `DEFAULT_BOUNDS` for `firm_radius` is now `(1.0, 4.0)`, not `(1.0, 6.0)`, and a
new `_validate_firm_radius_bound()` check raises `ValueError` if a caller supplies a wider upper
bound than `2 * base.cbd_radius` while `belief_multiplier == 1` -- explaining, in the error
itself, that every ticket-firm pair becomes reachable past that point. A separate,
deterministic regression test (`test_firm_radius_beyond_the_geometric_maximum_is_a_flat_region`)
keeps two calibration-irrelevant values (4.1 and 6.0) producing byte-identical histories, to
document why they're excluded rather than to legitimise them as a search domain.

`CalibrationResult` also now carries `boundary_adjacent_params`: any parameter landing within
one per cent of either edge of its own search box is flagged there, whether or not it happens to
be `firm_radius` -- a numerical estimate that close to a wall is weakly identified regardless of
whether the box itself is geometrically well-posed, and Task 8's no-false-success gate needs
this signal available on every `CalibrationResult`, not computed ad hoc after the fact.

**This directly supersedes "The re-run campaign" section's `firm_radius=4.827` finding above.**
That section described `firm_radius=4.827` landing "inside its search box, not at a wall -- an
actual interior optimum, not an optimiser reporting that the box was drawn wrong." Under the
corrected geometry, `4.827` is *past* the `4.0` diameter -- squarely inside the flat,
unidentified region the old `(1.0, 6.0)` box wrongly made searchable, not an interior optimum at
all. Every specific number that section reports (the two "well-fit" moments, the `long_term_share`
tension diagnosis, the `reentry_threshold` sweep) was measured at a parameter point now known to
be geometrically meaningless for `firm_radius` specifically, and needs re-measuring under the
corrected sampling and the corrected `(1.0, 4.0)` box -- done in Task 8 of the verification
remediation plan, not here, since it also depends on Tasks 6 and 7's changes to the calibration
engine and SQ1 machinery landing first.

## The MSM weight matrix was quietly rewarding noisy candidates, not just missing a simulation-variance term

M9's original correction (see "Two corrections to not-yet-built code, from reading McFadden and
Pissarides directly" and "Week 4, calibrate.py -- the MSM engine, D12 and M9 implemented exactly
as specified", both above) was half right and half wrong in a way that only shows up once you
ask what the formula actually does across candidates, not just at one point. McFadden (1989)
does decompose total MSM estimator variance into a data-sampling term and a separate simulation
term (p.1006), and does support fixed common random draws as parameters change -- both correctly
cited. What McFadden's decomposition does **not** license is recomputing a diagonal inverse-
variance weight `1 / (data_SE^2 + sim_var)` from *each candidate's own* simulation variance,
inside the loss function, at every evaluation. The implemented version did exactly that: a
candidate landing in a noisier region of parameter space got a smaller weight and therefore a
*cheaper* loss for the same deviation from target, purely because it was noisy -- an MSM
estimator is supposed to be indifferent to where its own noise happens to be larger, not
rewarded for finding it. Nothing in the 17 August audit evidence flagged this by number, but
it's a direct consequence of re-reading the implemented formula against McFadden's actual
argument while fixing the surrounding calibration bugs, and it needed fixing in the same pass
as the bounds and sampling issues, not left for a later session to rediscover independently.

**The fix is a two-step, fixed-weight procedure**, matching McFadden's decomposition without
reopening the discount-noisy-candidates hole. `MSMWeights` is a new frozen dataclass carrying
the ordered moment keys, the weight matrix itself, the parameter point (if any) the simulation-
covariance component was estimated at, and the seeds used for that estimate. `quadratic_loss`
is the pure `g.T @ W @ g` form, taking no dependency on how `g` or `W` were built. `msm_loss`
now takes a fixed `MSMWeights` argument and never reads a candidate's own simulation variance
into its weight -- confirmed directly by `test_msm_loss_gives_no_discount_to_a_higher_variance_
candidate`, which forces two candidates to an identical deviation with simulation variances of
0.001 and 50.0 respectively and checks the returned loss is bit-identical.

`calibrate()` now runs two full search stages, each an LHS sweep plus Nelder-Mead from the
three best distinct LHS points (`n_restarts`, configurable):

1. **W0** = `pinv(S_data)`, `S_data` the diagonal matrix of empirical variances (off-diagonal
   entries are zero -- `discouraged_share` and `long_term_share` are both QLFS-derived but come
   from separate notebooks with independent bootstraps that never estimated their joint
   sampling covariance, so zero is documented as "not estimated," not assumed correct). Held
   fixed for the whole preliminary search.
2. At the preliminary search's optimum, simulate `WEIGHT_SEEDS` (`range(2001, 2051)`, 50 seeds
   disjoint from `CALIBRATION_SEEDS` 1-15 and `VALIDATION_SEEDS` 1001-1050) and estimate the
   full 4x4 simulation covariance matrix there (`np.cov` over the raw per-seed moment draws,
   not just the four per-moment variances the old code used).
3. **W1** = `pinv(S_data + S_sim / 50)`. Held fixed for a second, independent search from
   scratch. This search's result is what `CalibrationResult` reports.

A ridge (`1e-8 * trace`) is added only if a covariance matrix is rank-deficient, and its exact
value is stored on the `MSMWeights` rather than hidden inside the inverse call.

**Optimiser status is now part of the public result, not assumed.** `CalibrationResult` carries
`success`, `message`, `selected_restart_index`, `n_restarts`, `n_converged_restarts`, the fixed
`weights` the final stage searched under, and `preliminary_params` (the W0-stage optimum W1 was
estimated from). If every restart in a stage fails to converge, `calibrate()` raises
`RuntimeError` naming every restart's SciPy status and message, rather than returning a
parameter vector nobody actually validated as an optimum -- `test_calibrate_raises_when_no_
restart_converges` forces this with a monkeypatched `minimize` that always reports failure.

This roughly doubles the wall-clock cost of a campaign (two full search stages instead of one,
each with up to three restarts instead of one Nelder-Mead run), so D4's performance gate needs
re-checking against the real cost once Task 8 runs the corrected campaign -- flagged here rather
than discovered as a surprise during that run.
