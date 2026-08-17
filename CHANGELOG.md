# Changelog

Format: one entry per tag, plain language, for an outside reader. `Unreleased` covers everything
since the last tag (`v0.2`) that hasn't yet earned a new tag of its own.

## Unreleased

**An independent verification (17 August 2026) found six real problems in the code and
methodology tagged `v0.2`**, and this remediation fixes them one task at a time, each with its
own failing test, fix, and `DECISIONS.md` entry:

- `frictionless.yaml` silently carried a stale `separation_rate`, so it was never actually a
  one-field counterfactual of `baseline.yaml` -- every `delta_a` computed against it is
  invalidated. Fixed and contract-tested.
- `distance_gradient_slope`'s empirical target had its sign dropped in transcription and was
  dated to the source paper's publication year instead of the underlying census year. Corrected
  against the source PDF directly.
- `transport_budget_share`'s simulated and empirical moments were measuring different things
  (a monthly per-searcher average vs. a daily per-trip conditional cost). Unified to the same
  estimand -- the old apparent 0.5pp fit was spurious, off by roughly 14x once corrected.
- The QLFS separation-rate panel linkage contained implausible person-matches. Added a
  demographic consistency check and a household-cluster bootstrap; the central estimate moved
  from 0.0317 to 0.0296 monthly, propagated into every dependent config.
- The spatial search-position draw was uniform over the radius rather than the disk area, which
  is why the `firm_radius` calibration search box had a flat, unidentified region. Fixed, and
  the search box now rejects bounds that exceed the geometric identification limit.
- The MSM weight matrix recomputed itself from each candidate's own simulation noise, silently
  discounting noisier candidates' deviations. Replaced with a fixed, two-step weight matrix and
  multi-start Nelder-Mead with explicit convergence reporting.
- `src/sq1.py` makes SQ1 a one-command, paired-seed comparison that refuses to report a
  constrained `delta_a` when either arm fails a real constant-returns hypothesis test.

**The corrected calibration campaign ran once, against all of the above, and did not clear the
no-false-success gate**: two parameters landed at their search-box floor, and `long_term_share`
simulates at exactly zero across the entire tested response surface (see `DECISIONS.md`, "The
corrected campaign, run once, fails the no-false-success gate..."). This is reported here as an
honest, diagnosed structural finding, not smoothed into a version bump -- the calibration is not
a usable headline result, and no new tag is cut for it.

Also: all four moment notebooks now read a `THESIS_DATA_ROOT` environment variable instead of a
committed absolute path; the microdata-detection hook gained a real (tested) old-format Stata
header check and corrected its licence claim; `.pre-commit-config.yaml`'s Ruff and nbstripout
revisions now match `pyproject.toml`'s pins.

## v0.2 -- Week 2 close: spatial grid, endogenous firms, real moments begin

2D grid with township clusters, neighbourhood matching, endogenous firm vacancy posting (M4),
AR(1) productivity shock, wealth heterogeneity and cell aggregates (D3), the per-agent trace
figure, the scarce-vacancy smoke test and D4's performance benchmark. The first two real
(non-provisional) moments landed from actual QLFS/NHTS microdata.

## v0.1.1 -- runner cache and the first moment scaffold

`runner.py`'s cache key (I1), provisional `moments.csv` with the four named scalars.

## v0.1 -- foundations

Repo scaffold, pinned dependencies, CI, pre-commit hooks (microdata block, AI-attribution
block), MIT licence, `DECISIONS.md` seeded with the design record from two rounds of
adversarial plan review. `config.py`/`agents.py`/`model.py`/`run.py` with the MVM: separation,
trips-per-period search intensity, the belief parameter, D11 measurement timing.
