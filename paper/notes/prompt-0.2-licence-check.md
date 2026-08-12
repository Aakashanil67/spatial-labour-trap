# Prompt 0.2 -- DataFirst licence check

Run 2026-08-12, ahead of Week 3's moment notebooks computing real numbers into `data/moments.csv`
for the first time. Overdue from Week 1 -- this note exists specifically so that decision isn't
made by assumption at the point it actually matters.

## What tier each dataset is under

Checked directly against DataFirst's catalogue entries, not inferred from a general policy page.
QLFS's catalogue page (for the 2017 Q1 release, datafirst.uct.ac.za/dataportal/index.php/catalog/616)
lists "Access Conditions: Public use data, available to all," with a required citation:
"Statistics South Africa. Quarterly Labour Force Survey [quarter] [dataset]. Version 1.
Pretoria: Statistics South Africa [producer], [year]. Cape Town: DataFirst [distributor],
[year]," plus a dataset-specific DOI. PALMS is confirmed distributed under Creative Commons
Attribution 4.0 International (CC BY 4.0) -- DataFirst's own description of the harmonised
PALMS series states this directly.

NIDS Wave 5 was not independently checked against its own catalogue page this session. It is
listed alongside QLFS and PALMS as public-release in the project's own reference memory
(`reference-datafirst-licence`), consistent with DataFirst's general policy: "Public use" is
CC-BY (attribution-only), "Licensed" (non-commercial, CC-BY-NC) and Accredited-Researcher
(on-site SRDC access) are the two more restrictive tiers, and this thesis's data folder holds
no file that required either. Treat this as inherited, not independently re-verified -- if
NIDS W5's own catalogue page is ever checked directly and disagrees, this note is wrong until
updated. NHTS 2020 is distributed by Statistics South Africa directly, not through DataFirst,
and was not checked against a StatsSA licence page at all. It's treated here as public-release
by the same convention QLFS uses, since both are StatsSA products -- an inference, not a
confirmed citation. Flag this before publishing a number sourced only from NHTS, if that ever
matters more than it currently does.

## What this means for what gets committed

DataFirst's own general policy (confirmed by web search against multiple sources, not just one
page): "Public use data is shared under a Creative Commons CC-BY attribution-only license."
CC-BY permits derivative works with no restriction beyond attribution; published aggregate
statistics are exactly that. Nothing in any catalogue page checked here restricts publishing a
computed share, mean, or regression coefficient -- the restriction that exists in this licence
family is on redistributing the underlying individual-level records, which I4 (`DECISIONS.md`)
already treats as never-committed regardless of licence tier.

Committing `data/moments.csv` with real computed values, standard errors, and a citation to each
source dataset is permitted. The citation itself needs to name the producer (Statistics South
Africa for QLFS/NHTS, SALDRU for PALMS/NIDS) and DataFirst as distributor, in the format
DataFirst's own catalogue specifies -- `data/README.md`'s moment table
should carry this, not just a bare dataset name. Never publish a row count, a cell size under
any reasonable disclosure threshold, or anything else that could re-identify a respondent --
none of the four moments this thesis computes are anywhere near that risk (each is a share or
slope over thousands of respondents), but the rule is stated once here rather than re-derived
per notebook.

## What was not done

The full DataFirst terms-of-service document was not read end to end -- this check relied on
catalogue-page access conditions and DataFirst's published general policy, cross-checked across
independent sources, which is sufficient for the actual question (may aggregates be published)
but would not be sufficient for a question about, say, commercial use or data resale, neither of
which applies here.
