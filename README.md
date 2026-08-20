# spatial-labour-trap

![CI](https://github.com/Aakashanil67/spatial-labour-trap/actions/workflows/ci.yml/badge.svg)

A spatially explicit agent-based model of job search in a stylised South African city, built
for an economics honours thesis. It asks which of two subsidies -- cheaper transport or a
wage subsidy to employers -- buys more employment per rand of public spending, and whether the
model can explain why both policies, tried for real in South Africa, produced disappointing
results.

## The problem

Standard search-and-matching theory (Diamond-Mortensen-Pissarides) treats unemployment as one
representative worker meeting one representative vacancy. That framework has nothing to say
about a job seeker in Khayelitsha whose taxi fare into Cape Town eats into a small, finite pool
of savings every time she looks for work, or about what happens when that pool runs out. Two
real South African policy experiments sharpen the question. Franklin (2018) found transport
subsidies got young Ethiopians into permanent jobs. Banerjee and Sequeira (2023) ran a similar
experiment in South Africa: search intensity rose, employment did not. South Africa's flagship
wage subsidy, the Employment Tax Incentive, evaluated repeatedly (Ranchhod and Finn 2016;
Ebrahim and Pirttila 2024), moved employment close to zero. This model exists to ask why the
same idea worked in one country and not the other, and whether the answer depends on which
side of the labour market -- worker search capacity or firm hiring appetite -- is actually
binding.

## Method

Agents are boundedly rational: they follow local rules of thumb, not a solved optimisation
problem. Nowhere does the code assert that distance lowers matching efficiency by some fixed
share -- distance only does what it does in reality, which is cost money to cross. The
aggregate matching function is then fitted statistically to the simulated series of
unemployment, vacancies and hires, exactly as an econometrician would fit it to national
statistics, so the efficiency loss from spatial friction is a measured outcome, not an
assumption. Firms post vacancies endogenously from an expected-profit heuristic, so a wage
subsidy has a real channel to work through -- if vacancies were fixed by assumption, the wage
subsidy could never do anything and the policy comparison would be rigged before the first run.

Calibration is method of simulated moments against four public data targets at once (not one
headline number, which any model can be tuned to hit), and the two policies are compared under
a common fiscal budget, reported as employment gained per rand.

## Status

Weeks 1-4 of the build plan are implemented **in code** (the writing deliverables are not: no
Model or Calibration chapter is drafted yet): the spatial model (endogenous firms, AR(1) shock,
wealth heterogeneity), all four calibration moments computed from real DataFirst microdata, the
matching-function fit with a constant-returns test before any efficiency number is trusted, and
the MSM calibration engine. An independent verification on 17 August 2026 found six real
problems spanning the model, the methodology and the public repository itself; every one is
fixed and test-covered as of this commit -- see `DECISIONS.md` for the full record, task by
task.

**Two independent bugs were found and fixed in the calibration, in sequence.** First, the
headline `long_term_share` failure was a measurement bug: the simulated moment counted the
current continuous searching spell, which resets on every discouragement cycle, while QLFS's
`Long_term_unempl` -- the empirical target -- is derived from time since the respondent last
worked, which a pause in search does not reset. Second, once that was fixed, the recalibrated
`transport_budget_share` missed its target by a factor of 19; decomposing the miss showed
`transport_cost_rate` (rand per grid-unit distance) had been set when the spatial grid was built
and never checked against data, making the distance component of a single search trip cost more
than a full day's wage before the free parameters did anything. Rebased against Banerjee and
Sequeira (2023)'s R12.50 Soweto-CBD return fare and this project's own NHTS median-wage figure
(R4,300, reproduced directly from the microdata), `transport_cost_rate` moved from 0.004 to
0.000145.

**The recalibrated fit, at the corrected clock and the rebased cost together**: `discouraged_share`
0.1329 against empirical `0.1343` (99.0 per cent of target). `long_term_share` 0.7883 against
`0.7744` (101.8 per cent). `transport_budget_share` 0.0919 against `0.1058` (86.9 per cent) --
the moment that motivated the second fix. `distance_gradient_slope` -0.8910 against `-5.0333`
(17.7 per cent) remains the one real misfit, and now carries the largest share of the objective
(51.4 per cent) precisely because the other three are close to fit and it is not.
`initial_search_capital` (1.4962) sits within 1 per cent of its 1.5 upper bound -- weakly
identified, an open item alongside `distance_gradient_slope`'s persistent under-identification.
One caution found while regenerating the response surface: the calibrated `firm_kappa` (0.2239)
sits close to a sharp regime boundary in the surface (the market collapses into a near-zero-
discouragement, near-zero-long-term-share state at `firm_kappa=0.5` and above) -- the fit is
genuine at this point but perched near a discontinuity, not sitting in a wide basin. See
`DECISIONS.md`, "The spatial money scale was never rebased into wage units" and "The campaign
under the rescaled cost, and what it changes".

**One number that is trustworthy right now**: SQ1 (does removing spatial friction change the
matching function's fitted efficiency `a`?), paired across 20 common seeds under a genuine
single-field counterfactual (`configs/baseline.yaml` vs. `configs/frictionless.yaml`, differing
only in `transport_cost_rate`), gated by a real constant-returns hypothesis test rather than
reported regardless: `delta_a = 0.0015`, 95% CI `[-0.024, 0.038]` -- statistically
indistinguishable from zero at this population, re-run after `transport_cost_rate` was rebased
(the sign and magnitude of the point estimate moved with the rescale; the conclusion did not).
Reproduce it directly:

```bash
python -m src.sq1 --baseline configs/baseline.yaml --frictionless configs/frictionless.yaml \
    --seeds 1:20 --out-dir results/published
```

## Design decisions and trade-offs

See [`DECISIONS.md`](DECISIONS.md) for the full record, including two rounds of adversarial
review that caught six model-specification bugs, several measurement errors, and a schedule
sized at roughly double the hours actually available.

## Data

No survey microdata is ever committed here -- see [`data/README.md`](data/README.md) for what
that means and how to get the source files yourself. Enforced by a pre-commit hook that checks
staged files by content, not just by path.

## How to run it

```bash
python -m venv .venv && .venv\Scripts\activate   # .venv/bin/activate on Mac/Linux
pip install -e ".[dev]"
pre-commit install --hook-type pre-commit --hook-type commit-msg

python -m src.run --config configs/mvm.yaml
pytest -m "not slow"          # full suite: pytest (no marker filter)

python -m src.calibrate --config configs/baseline.yaml --out-dir results/published
python -m src.sq1 --baseline configs/baseline.yaml --frictionless configs/frictionless.yaml \
    --seeds 1:20 --out-dir results/published
```

Notebooks under `notebooks/moments/` need `THESIS_DATA_ROOT` set to your own extracted DataFirst
download folder first -- see [`data/README.md`](data/README.md).

## What's not done

- **`distance_gradient_slope` reaches only 17.7 per cent of its target, diagnosed as a real
  limitation rather than a bug.** Distance enters this model only through search cost, not
  through search geometry; raising `transport_cost_rate` strengthens the slope but wrecks
  `discouraged_share` and `transport_budget_share` on the way (see `DECISIONS.md`, "distance_
  gradient_slope is a real, diagnosed limitation, not a bug"). The published baseline reports
  this as a limitation. A direct distance-to-search-efficiency channel, in the spirit of Wasmer
  and Zenou (2002)'s own DMP model, is being tried on `explore/distance-search-efficiency` and
  reported separately, not folded into the calibrated baseline.
- Week 5 (Banerjee-Sequeira validation, beliefs-vs-scarcity decomposition), Week 7 (policy
  experiments, condition mapping) and Week 8 (robustness, freeze) haven't started.
- `distance_gradient_slope`'s empirical uncertainty is a three-city cross-sectional spread rather
  than a formal sampling standard error, and its fitted weight sits 4.39 to 4.89 orders of
  magnitude below the other three moments -- under-identified by the current moment set, not yet
  resolved (see `DECISIONS.md`).
