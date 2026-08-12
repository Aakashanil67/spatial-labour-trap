# Data

Nothing in this directory is survey microdata. `moments.csv` holds four calibration numbers
and their standard errors, computed from microdata that lives outside this repo.

## Getting the source data

Register at [datafirst.uct.ac.za](https://www.datafirst.uct.ac.za). NIDS Wave 5 (2017), PALMS
(1993-2025) and the QLFS files are public-release and download directly after registration --
no separate approval wait, unlike the geo-coded NIDS extract, which needs an Accredited
Researcher application and on-site access at UCT and is not used here. The National Household
Travel Survey is published by StatsSA directly.

Save everything to a folder **outside this repository**, e.g. `../thesis-data/`, and set
`data_root` in `configs/*.yaml` to that path. Never inside `spatial-labour-trap/`.

## What the DataFirst licence permits publishing here

Checked in `paper/notes/prompt-0.2-licence-check.md`: QLFS, PALMS and NIDS W5 are all
DataFirst's "Public use" tier (Creative Commons Attribution, CC-BY), which permits publishing
derived aggregates -- shares, means, regression coefficients -- with attribution, no restriction
beyond that. The restriction in this licence family is on redistributing the underlying
individual-level records, which this repo never commits regardless of licence tier. Every row
in `moments.csv` needs a citation naming the producer (Statistics South Africa or SALDRU) and
DataFirst as distributor, in the format DataFirst's own catalogue specifies -- see the licence
check note for the exact citation string.

## `moments.csv` schema

One row per calibration target, each a single named scalar:

| key | definition | source |
|---|---|---|
| `distance_gradient_slope` | employment share, percentage points per 10 *percentile points* of within-city travel-time rank to the nearest business district -- **not km-distance**, see DECISIONS.md | Baez and Kshirsagar (2026), WB WP 11285, Table 5b -- digitised, not the R/Stata reproducibility package (see D6) |
| `discouraged_share` | StatsSA discouraged work-seeker definition: wants work, available, not searching because believes no jobs are available | QLFS |
| `transport_budget_share` | see the definitional trap note in DECISIONS.md before trusting this number -- at least three published variants differ fourfold | NHTS |
| `long_term_share` | share of the *currently unemployed* with in-progress spell duration >= 12 months | QLFS |

Every row also carries `standard_error`, `period`, `source`, and `provisional` (bool).
`provisional=True` rows are sourced from published headline statistics, not computed from
microdata, and exist so the model can be built and debugged before DataFirst access lands.
Per D7, the moment set freezes at the start of Week 4 (calibration); anything still
provisional at that point stays provisional for the headline results.

## Never

- Never commit a file under `data/raw/`, or any `.dta`/`.sav`/`.por`/`.zip`.
- Never paste a row of microdata into a Claude Code prompt. Paths and aggregates only.

Both are enforced by `tools/hooks/check_no_microdata.py`, run on every commit -- not just
`.gitignore`, which a `git add -f` would bypass.
