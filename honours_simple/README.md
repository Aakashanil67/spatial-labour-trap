# honours_simple

This folder holds the model behind my Economics Honours thesis. The thesis asks two questions. How do distance-related search costs affect who finds work? And when does cheaper search raise total employment? This simple model replaces the larger spatial model in `src/`, which was too big for a 6,000-word thesis.

## The rules

- There are 300 workers in three groups of 100, at distance 1, 2 and 3 from the jobs.
- One application costs 1.2 times the worker's distance, multiplied by a cost multiplier. The multiplier is 1 at normal cost and 0.5 when search is cheaper.
- Each unemployed worker gets an allowance of 3 per period and cannot save what is left over. At normal cost the near, middle and far groups can therefore afford 2, 1 and 0 applications per period. At half cost they can afford 3, 2 and 1.
- The number of jobs is fixed. A job reopens only when its worker loses it, which happens with probability 0.03 per period. A worker who loses a job can apply again in the same period.
- Matching runs in up to three rounds. In each round, every unemployed worker with an application left applies to one open job at random. Each job that receives applications hires one applicant at random. This is the urn-ball process described by Petrongolo and Pissarides (2001, pp. 401-402), and the tests check that the average number of hires in one round matches the formula.

All values are illustrative assumptions. I chose them after exploratory runs so that the far group cannot afford an application at normal cost. Its zero employment in those scenarios is therefore built into the rules.

## Reproduce

Run the tests and the model from the repository root.

```
python -m pytest tests/test_honours_simple.py -q
python -m honours_simple.run --output results/honours_simple
```

The run takes about eight seconds. It writes `periods.csv`, `run_summary.csv`, `summary.csv`, three figures and `manifest.json`, which records the parameters, seeds and source commit. Each of the four scenarios runs with 30 seeds (1000 to 1029), and the results average periods 91 to 120.

## Results

| Scenario | Employed (of 300) | Near / middle / far employed |
|---|---|---|
| Normal cost, 150 jobs | 150.0 | 0.753 / 0.747 / 0.000 |
| Half cost, 150 jobs | 150.0 | 0.500 / 0.497 / 0.503 |
| Normal cost, 300 jobs | 199.9 | 1.000 / 0.999 / 0.000 |
| Half cost, 300 jobs | 298.1 | 1.000 / 0.997 / 0.984 |

With 150 jobs, cheaper search changes who is hired and leaves employment at 150. With 300 jobs, it fills about 98 jobs that stayed open because far workers could not apply. When jobs are scarce, a second application is worth almost nothing, because almost every open job fills in the first round.

## Sensitivity check with an allowance of 4

The command below repeats the four scenarios with an allowance of 4.

```
python -m honours_simple.run --allowance 4 --no-figures --output results/honours_simple_allowance4
```

With this allowance every group can afford at least one application. The limits become 3, 1 and 1 applications at normal cost and 3, 3 and 2 at half cost. With 150 jobs, cheaper search then barely changes anything. Employment stays at 150, and about half of every group is employed at both costs. With 300 jobs it adds 2.9 workers (from 296.7 to 299.6), against 98.2 at an allowance of 3.

The large effect at an allowance of 3 therefore depends on the far group being able to afford one application. Once everyone can apply, extra applications add little. The higher allowance also changes the other groups' limits, so this comparison is a sensitivity check. It does not show how much of the 98.2 comes from each change.

## What the model leaves out

The model has no geography, savings, wages, firm decisions or calibration to South African data. The number of jobs is fixed, so cheaper search can only fill existing jobs. Time runs in model periods, which do not correspond to months.
