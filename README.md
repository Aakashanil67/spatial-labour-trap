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

Under active development. This README, the results and the figures below get filled in as each
build phase lands -- see `DECISIONS.md` for the engineering record and
`.claude/session-log.md` (local only) for the session-by-session history.

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
```

## What's not done

Everything past the minimum viable model. This section gets more specific, not less, as the
build progresses -- an honest what's-broken list is worth more here than a features list.
