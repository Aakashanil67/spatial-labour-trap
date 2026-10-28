# spatial-labour-trap

![CI](https://github.com/Aakashanil67/spatial-labour-trap/actions/workflows/ci.yml/badge.svg)

> The model in my Economics Honours thesis is the simpler one in [`honours_simple/`](https://github.com/Aakashanil67/spatial-labour-trap/tree/honours-simple-model/honours_simple) on the `honours-simple-model` branch. This page describes the larger spatial model in `src/`, which I set aside because it was too big for a 6,000-word thesis.

This repository holds a spatially explicit agent-based model of job search in a stylised South African city, built for an economics honours thesis. It asks which of two subsidies buys more employment per rand of public spending, cheaper transport or a wage subsidy to employers. It also asks whether the model can explain why both policies, tried for real in South Africa, produced disappointing results.

## The problem

Standard search-and-matching theory (Diamond-Mortensen-Pissarides) treats unemployment as one representative worker meeting one representative vacancy. That framework has nothing to say about a job seeker in Khayelitsha whose taxi fare into Cape Town eats into a small, finite pool of savings every time she looks for work. Nor does it say what happens when that pool runs out.

Real policy experiments sharpen the question. Franklin (2018) found that transport subsidies got young Ethiopians into permanent jobs. Banerjee and Sequeira (2023) ran a similar experiment in South Africa, where search intensity rose and employment did not. South Africa's flagship wage subsidy, the Employment Tax Incentive, has been evaluated repeatedly (Ranchhod and Finn 2016; Ebrahim and Pirttila 2024) and moved employment close to zero. This model asks why the same idea worked in one country and failed in the other. It also asks whether the answer depends on which side of the labour market is binding, worker search capacity or firm hiring appetite.

## Method

Agents are boundedly rational and follow simple local rules of thumb. The code never assumes that distance lowers matching efficiency by a fixed share. Distance only costs money to cross, as it does in reality. I then fit the aggregate matching function statistically to the simulated series of unemployment, vacancies and hires, exactly as an econometrician would fit it to national statistics. The efficiency loss from spatial friction therefore comes out of the simulation as a measured outcome.

Firms post vacancies from an expected-profit rule, which gives a wage subsidy a real channel to work through. If vacancies were fixed by assumption, the wage subsidy could never do anything, and the policy comparison would be rigged before the first run.

The calibration uses the method of simulated moments and targets four public data moments at once. A single headline number would be too easy, since any model can be tuned to hit one. The two policies are compared under a common fiscal budget and reported as employment gained per rand.

## Status

The code for weeks 1 to 4 of the build plan is complete. It covers the spatial model (endogenous firms, an AR(1) shock and wealth heterogeneity), all four calibration moments computed from real DataFirst microdata, the matching-function fit with a constant-returns test before any efficiency number is trusted, and the MSM calibration engine. The Model and Calibration chapters for this version were never drafted.

An independent verification on 17 August 2026 found six real problems in the model, the methodology and the public repository itself. Every one is fixed and covered by tests in this commit. [`DECISIONS.md`](DECISIONS.md) gives the full record, task by task.

**Two independent bugs were found and fixed in the calibration, one after the other.** The first, behind the headline `long_term_share` failure, was a measurement bug. The simulated moment counted the current continuous searching spell, which resets on every discouragement cycle. QLFS's `Long_term_unempl`, the empirical target, is derived from the time since the respondent last worked, which a pause in search does not reset.

Once that was fixed, the recalibrated `transport_budget_share` missed its target by a factor of 19. Decomposing the miss showed that `transport_cost_rate` (rand per grid unit of distance) had been set when the spatial grid was built and never checked against data. The distance part of a single search trip therefore cost more than a full day's wage before the free parameters did anything. I rebased it against Banerjee and Sequeira (2023)'s R12.50 Soweto-CBD return fare and this project's own NHTS median wage (R4,300, reproduced directly from the microdata). `transport_cost_rate` moved from 0.004 to 0.000145.

**The recalibrated fit, with the corrected clock and the rebased cost together**

- `discouraged_share` is 0.1329 against an empirical 0.1343 (99.0 per cent of target).
- `long_term_share` is 0.7883 against 0.7744 (101.8 per cent).
- `transport_budget_share` is 0.0919 against 0.1058 (86.9 per cent). This is the moment that motivated the second fix.
- `distance_gradient_slope` is -0.8910 against -5.0333 (17.7 per cent). It remains the one real misfit and now carries the largest share of the objective (51.4 per cent), because the other three moments are close to fit.

`initial_search_capital` (1.4962) sits within 1 per cent of its upper bound of 1.5. It is weakly identified and remains an open item, along with the persistent under-identification of `distance_gradient_slope`.

Regenerating the response surface also turned up a caution. The calibrated `firm_kappa` (0.2239) sits close to a sharp regime boundary. At a `firm_kappa` of 0.5 and above, the market collapses into a state with near-zero discouragement and a near-zero long-term share. The fit at 0.2239 is genuine, but it lies near a discontinuity in a narrow part of the surface. See the `DECISIONS.md` entries "The spatial money scale was never rebased into wage units" and "The campaign under the rescaled cost, and what it changes".

**One number that is trustworthy now.** SQ1 asks whether removing spatial friction changes the fitted efficiency `a` of the matching function. I pair runs across 20 common seeds under a single-field counterfactual (`configs/baseline.yaml` against `configs/frictionless.yaml`, which differ only in `transport_cost_rate`). A constant-returns hypothesis test must pass before the result is reported. The estimate is `delta_a = 0.0015`, with a 95% confidence interval of `[-0.024, 0.038]`, so it is statistically indistinguishable from zero at this population size. I re-ran it after rebasing `transport_cost_rate`. The sign and size of the point estimate moved with the rescale, and the conclusion stayed the same. The command below reproduces it.

```bash
python -m src.sq1 --baseline configs/baseline.yaml --frictionless configs/frictionless.yaml \
    --seeds 1:20 --out-dir results/published
```

## Design decisions and trade-offs

[`DECISIONS.md`](DECISIONS.md) holds the full record. It includes two rounds of adversarial review that caught six model-specification bugs, several measurement errors and a schedule sized at roughly double the hours actually available.

## Data

This repository never contains survey microdata. [`data/README.md`](data/README.md) explains what that means and how to get the source files yourself. A pre-commit hook enforces the rule by checking the content of staged files as well as their paths.

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

The notebooks under `notebooks/moments/` need `THESIS_DATA_ROOT` set to your own extracted DataFirst download folder. [`data/README.md`](data/README.md) explains how.

## What is not done

- **`distance_gradient_slope` reaches only 17.7 per cent of its target.** This is a diagnosed limitation of the model, and no bug lies behind it. Distance enters this model only through search cost and has no effect on search geometry. Raising `transport_cost_rate` strengthens the slope but wrecks `discouraged_share` and `transport_budget_share` along the way (see `DECISIONS.md`, "distance_gradient_slope is a real, diagnosed limitation, not a bug"). The published baseline reports this as a limitation. A direct channel from distance to search efficiency, in the spirit of the DMP model in Wasmer and Zenou (2002), is being tried on `explore/distance-search-efficiency`. Its results will be reported separately and kept out of the calibrated baseline.
- Week 5 (Banerjee-Sequeira validation and the beliefs-versus-scarcity decomposition), week 7 (policy experiments and condition mapping) and week 8 (robustness and freeze) have not started.
- The empirical uncertainty of `distance_gradient_slope` comes from the spread across three cities, which is weaker than a formal sampling standard error. Its fitted weight sits 4.39 to 4.89 orders of magnitude below the other three moments. The current moment set leaves it under-identified, and the problem is unresolved (see `DECISIONS.md`).
