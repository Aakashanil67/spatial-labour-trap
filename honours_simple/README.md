# honours_simple

The model behind the Honours thesis: how distance-related search costs affect who finds work,
and when cheaper search raises employment rather than only changing who is hired. It replaces
the larger spatial model in `src/`, which was out of scope for a 6,000-word thesis.

## The rules

- 300 workers in three groups of 100, at distance 1, 2 and 3 from the jobs.
- One application costs `1.2 x distance`, times a cost multiplier (1 normally, 0.5 for cheaper
  search). Each unemployed worker has an allowance of 3 per period, which cannot be saved, so
  workers can afford 2, 1 and 0 applications at normal cost and 3, 2 and 1 at half cost.
- A fixed number of jobs. A job reopens only when its worker is separated (probability 0.03 per
  period); separated workers can apply in the same period.
- Matching runs in up to three rounds. In each round every unemployed worker with an
  application left applies to one open job at random, and each job that receives applications
  hires one applicant at random. This is the urn-ball process in Petrongolo and Pissarides
  (2001, pp. 401-402); the tests check that one round's average hires match its expectation.

All numbers are illustrative assumptions, not estimates. They were chosen after exploratory
runs to show an affordability threshold: at normal cost the far group cannot apply, so its zero
employment is built into the rules rather than found.

## Reproduce

```
python -m pytest tests/test_honours_simple.py -q
python -m honours_simple.run --output results/honours_simple
```

The run takes about eight seconds and writes `periods.csv`, `run_summary.csv`, `summary.csv`,
three figures and `manifest.json` (parameters, seeds, source commit). Four scenarios, 30 seeds
each (1000 to 1029), summarised over periods 91 to 120.

## Results

| Scenario | Employed (of 300) | Near / middle / far employed |
|---|---|---|
| Normal cost, 150 jobs | 150.0 | 0.753 / 0.747 / 0.000 |
| Half cost, 150 jobs | 150.0 | 0.500 / 0.497 / 0.503 |
| Normal cost, 300 jobs | 199.9 | 1.000 / 0.999 / 0.000 |
| Half cost, 300 jobs | 298.1 | 1.000 / 0.997 / 0.984 |

With 150 jobs, cheaper search changes who is hired but not how many. With 300 jobs it fills
about 98 jobs that stayed open because far workers could not apply. When jobs are scarce, a
second application is worth almost nothing: every open job fills in the first round.

## What it leaves out

No geography, savings, wages, firm decisions or calibration to South African data. Jobs are a
fixed stock, so the model cannot create jobs, only fill them. Periods are model periods, not
months.
