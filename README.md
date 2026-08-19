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

**The calibration itself does not clear its own no-false-success gate.** The campaign converges
cleanly on all three restarts, but `search_cost_per_trip` lands on its 0.005 search-box floor,
and two of the four moments cannot be reached from anywhere in the box. `long_term_share` (the
share of currently-unemployed agents searching 12+ months) reaches at best 0.0056 against an
empirical `0.7744` -- 0.72 per cent of target -- and is exactly zero at 12 of the 15 points on
the published response surface. `transport_budget_share` sits at 1.1121 against an empirical
`0.1058`, a factor of 10.5, and never approaches it along any axis.

Diagnosed, not hidden: whenever an agent resumes active search, the match rate relative to the
small active-searching pool is high enough that spells rarely reach 12 months. The one direction
that moves `long_term_share` at all is a higher separation rate, and pushing it there overshoots
`discouraged_share` by 5.4x -- so the moments trade off against each other rather than being
independently reachable. That is a mechanism question for the supervisor conversation rather than
a bug; see `DECISIONS.md`, "What actually identifies what, after the corrected campaign", and
`results/published/` for the unrounded numbers.

**One number that is trustworthy right now**: SQ1 (does removing spatial friction change the
matching function's fitted efficiency `a`?), paired across 20 common seeds under a genuine
single-field counterfactual (`configs/baseline.yaml` vs. `configs/frictionless.yaml`, differing
only in `transport_cost_rate`), gated by a real constant-returns hypothesis test rather than
reported regardless: `delta_a = -0.0104`, 95% CI `[-0.031, 0.013]` -- statistically
indistinguishable from zero at this population. Reproduce it directly:

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

- **A usable calibration.** See "Status" above. Two of the four moments are effectively
  uninformative, for opposite reasons: `distance_gradient_slope` carries 0.02 per cent of the
  fitted objective, and `long_term_share` carries 95.88 per cent but is exactly flat at 12 of 15
  swept points. That leaves two live moments to pin four parameters. Whether a fifth mechanism is
  warranted is a decision for Aakash and the supervisor, and Week 5 policy work should not
  proceed on a calibrated model until it is taken.
- Week 5 (Banerjee-Sequeira validation, beliefs-vs-scarcity decomposition), Week 7 (policy
  experiments, condition mapping) and Week 8 (robustness, freeze) haven't started.
- `distance_gradient_slope`'s empirical uncertainty is a three-city cross-sectional spread rather
  than a formal sampling standard error, and its fitted weight sits 3.70 to 5.40 orders of
  magnitude below the other three moments -- under-identified by the current moment set, not yet
  resolved (see `DECISIONS.md`).
