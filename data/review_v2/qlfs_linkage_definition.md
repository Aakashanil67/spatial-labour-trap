# QLFS panel linkage: demographic-consistency flags and provisional quarterly transitions

## Scope

P2.5's earlier pass confirmed only that a UQNO+PERSONNO linkage between 2025-Q4 and 2026-Q1 is
feasible (67.5% raw match rate) and explicitly declined to compute anything further. This pass
reproduces and investigates Astra's specific demographic-consistency flags on the matched panel,
and computes provisional survey-side quarterly Status transitions as an empirical review output.
**Neither of these decides or adopts a model calibration target.** The model-observation state
mapping (Part 2 of the execution plan / "Question 6" in `DECISIONS_PENDING.md`) is still
unresolved and still blocks adoption; this file records what the survey side shows, not what the
model side should target.

Reproducible from `scripts/build_qlfs_linkage_review.py`
(`python -m scripts.build_qlfs_linkage_review`, requires `THESIS_DATA_ROOT`), which writes
`qlfs_linkage_flags.csv`, `qlfs_provisional_transitions.csv`, `qlfs_transition_sensitivity.csv`,
and `qlfs_origin_eligibility_outcomes.csv`. Every count in this file is an **unweighted sample
diagnostic** -- no QLFS design weight is applied anywhere here.

## Demographic linkage flags, reproduced exactly

Matching 2025-Q4 (n=63,264) to 2026-Q1 (n=62,819) on UQNO+PERSONNO gives 42,695 matched records
(67.5% of 2025-Q4, 68.0% of 2026-Q1). Three consistency checks on the matched panel:

| flag | definition | n |
| --- | --- | --- |
| age-change | `Q14AGE` differs by anything other than 0 or +1 across one quarter | 516 |
| gender-code change | `Q13GENDER` differs | 214 |
| population-group change | `Q15POPULATION` differs | 53 |
| any of the above | union, distinct matched records | 625 |

All three reproduce Astra's reported counts exactly. The age-change definition is stated
explicitly because it is not simply "any difference": a one-quarter gap between interviews of the
same real respondent normally produces a difference of 0 (birthday not yet passed) or +1 (birthday
passed), so the flag fires only on a difference outside that pair -- confirmed live (516 of 12,024
raw nonzero age differences; the other 11,508 are the ordinary +1 case).

**Not automatically discarded, not automatically declared valid.** Two pieces of evidence bear on
which reading is more likely, both suggestive rather than conclusive:

- The 10 most extreme age-change records include several where `Status` is populated in one wave
  and missing in the other, consistent with the under-15/over-15 boundary being crossed in a
  single quarter for a real respondent (implausible) rather than with a genuinely aged individual.
  This is exactly the pattern expected if a PERSONNO slot in a household roster was reassigned to
  a different person between waves (a household member left and a new one, unrelated, took the
  same numbered slot) -- a known feature of rotating-panel designs, not evidence of NHTS/QLFS data
  corruption.
- Overlap between flags is modest (143 of 625 flagged records trip both the age and gender flags,
  3 trip all three), so the flags are not simply three views of the same handful of records; each
  is catching a partly distinct set.

Neither point proves individual records are mismatches rather than genuine changes (population
group in particular can legitimately be self-reported inconsistently across waves without any
roster error). The transition-rate comparison below is offered as further, quantitative evidence,
not as a resolution.

## Origin-eligibility population and outcome decomposition, CORRECTED 2026-09-14

**The analysis population is now defined by ORIGIN (2025-Q4) age eligibility, and every person in
it is assigned exactly one of four mutually exclusive outcomes -- rather than collapsing
everything into one "unmatched" figure.** The prior pass of this file also mislabelled the age-15+
population as "working-age", which is corrected here: `Status` is derived for every respondent
aged 15 and over with no upper bound -- 10.2% of the Status-eligible 2025-Q4 population is 65 or
older -- so "age 15+" and "working-age" (conventionally 15-64, the convention this project uses
elsewhere for `discouraged_share`/`long_term_share`) are different populations. **Age 15+ is the
PRIMARY universe** (it is what `Status` is actually derived for); 15-64 is reported as an explicit
alternative, not silently substituted for it.

For each origin-eligible person, the outcome is one of:

1. **matched, valid destination status** -- linked via UQNO+PERSONNO into 2026-Q1, with a valid
   Status there, within the same age universe.
2. **destination-age exclusion** -- linked into 2026-Q1 with a valid Status there, but their Q1
   age falls outside the chosen universe (only possible under the 15-64 alternative: a respondent
   turned 65 between waves). **This is not attrition or a failed link** -- the same real person was
   found and classified, just outside the age window -- and conflating it with genuine attrition,
   as the previous "unmatched share" figure implicitly did for the 15-64 case, overstates the
   linkage's real failure rate.
3. **destination status invalid, other reason** -- linked into 2026-Q1, but Status is missing
   there for a reason other than the age-universe restriction (rare: 27 of 46,032 under 15+, 25 of
   40,854 under 15-64 -- not further investigated, small enough to not change any conclusion here).
4. **failed linkage** -- UQNO+PERSONNO not found in 2026-Q1 at all.

| age universe | origin-eligible n | matched, valid | destination-age exclusion | destination status invalid (other) | failed linkage |
| --- | --- | --- | --- | --- | --- |
| 15+ (PRIMARY) | 46,032 | 30,977 (67.3%) | 0 (0.0%) | 27 (0.06%) | 15,028 (32.7%) |
| 15-64 (alternative) | 40,854 | 27,223 (66.6%) | 115 (0.3%) | 25 (0.06%) | 13,491 (33.0%) |

Under the 15+ primary universe, destination-age exclusion is structurally impossible (no upper age
bound), so the entire gap between "origin-eligible" and "matched, valid" is genuine linkage
failure plus a negligible "other" residual -- the old 32.7% figure was already correct for 15+, it
simply wasn't broken out by reason. Under 15-64, 115 people (0.3% of the origin-eligible
population) are excluded purely because they aged past 64 between waves -- a real, previously
unseparated effect, now visible in `qlfs_origin_eligibility_outcomes.csv` rather than folded into
"unmatched".

Full detail (both universes, all seven rows including the dwelling-level split below) in
`qlfs_origin_eligibility_outcomes.csv`.

## Decomposing failed linkage: dwelling continuity vs. person-level non-match

**Scheduled rotation is not mechanically subtracted here.** QLFS is publicly documented as a
rotating panel, which would suggest some of the failed-linkage share reflects respondents
scheduled to leave the sample rather than genuine attrition. But neither 2025-Q4 nor 2026-Q1
carries a rotation-group, wave, visit, or panel-position variable -- confirmed by a full search of
every column name AND label in both extracts, not just a keyword subset (only `Stratum` matched
any design-related keyword). Applying a generic rotation-scheme percentage (e.g. assuming a
4-quarter rotation implies ~25% scheduled turnover per quarter) without a variable to verify it
against this specific data would be exactly the kind of unsupported assumption this review is
trying to avoid, so it is not done.

What the data DOES support is a coarser, still genuinely informative split of the failed-linkage
group, using `UQNO` (the dwelling identifier) directly:

| component (15+ primary universe) | n | share of origin-eligible | interpretation |
| --- | --- | --- | --- |
| Whole dwelling not seen in 2026-Q1 at all | 13,211 | 28.7% | The UQNO itself does not reappear. Consistent with scheduled rotation out of the panel, but not confirmed as such absent a rotation variable. |
| Dwelling continues, but this person is not matched | 1,817 | 3.9% | The UQNO DOES reappear (the dwelling stayed in the panel), but this specific PERSONNO does not. Looks more like ordinary within-household attrition (moved out, temporarily absent, deceased, etc.) than a scheduled exit, since the dwelling itself was not scheduled to leave. |

These two sum exactly to the 15,028 failed-linkage total above. This is offered as a genuine,
data-supported partial decomposition -- not a rotation-group variable, and the 28.7%/3.9% split
should not be read as "scheduled" vs. "attrition" with certainty, only as "whole-household
non-continuity" vs. "within-household non-match", which is a meaningfully different (and more
informative) split than the raw failed-linkage total alone. The 15-64 alternative universe shows
the same pattern (28.8%/4.3% of its origin-eligible population) in `qlfs_origin_eligibility_outcomes.csv`.

**A 32.7% failed-linkage share (33.0% under the 15-64 alternative) is a substantial limitation of
any survey transition target built this way**, not a footnote. No design-based nonresponse
weighting has been applied to correct for it (unweighted counts throughout, as stated above);
whether QLFS's own panel weights address this is not checked here.

## Provisional quarterly Status transitions

Official StatsSA `Status` categories (Employed / Unemployed / Discouraged job seeker / Other not
economically active), origin population = 2025-Q4 Status, destination = 2026-Q1 Status, unweighted
counts. Three populations reported side by side so the sensitivity to the 625 flagged records is
visible rather than asserted:

**Full matched panel (n=30,977):**

| origin | Employed | Unemployed | Discouraged | Other NEA | origin n | diagonal share |
| --- | --- | --- | --- | --- | --- | --- |
| Employed | 9,662 | 498 | 184 | 318 | 10,662 | 0.9062 |
| Unemployed | 436 | 3,427 | 365 | 603 | 4,831 | 0.7094 |
| Discouraged | 197 | 388 | 1,417 | 358 | 2,360 | 0.6004 |
| Other NEA | 266 | 695 | 422 | 11,741 | 13,124 | 0.8946 |

**Excluding the 625 flagged records (n=30,494) -- full absolute and relative sensitivity,
CORRECTED 2026-09-14 to cover every origin/destination cell, not just the diagonal:**

| origin -> destination | full panel share | excl-flagged share | absolute diff (pp) | relative diff |
| --- | --- | --- | --- | --- |
| Employed -> Employed | 0.9062 | 0.9104 | +0.42 | +0.5% |
| Employed -> Unemployed | 0.0467 | 0.0457 | -0.10 | -2.1% |
| Employed -> Discouraged | 0.0173 | 0.0169 | -0.04 | -2.3% |
| Employed -> Other NEA | 0.0298 | 0.0270 | -0.28 | -9.4% |
| Unemployed -> Employed | 0.0903 | 0.0882 | -0.21 | -2.3% |
| Unemployed -> Unemployed | 0.7094 | 0.7125 | +0.31 | +0.4% |
| Unemployed -> Discouraged | 0.0756 | 0.0758 | +0.02 | +0.3% |
| Unemployed -> Other NEA | 0.1248 | 0.1235 | -0.13 | -1.0% |
| Discouraged -> Employed | 0.0835 | 0.0820 | -0.15 | -1.8% |
| Discouraged -> Unemployed | 0.1644 | 0.1645 | +0.01 | +0.1% |
| Discouraged -> Discouraged | 0.6004 | 0.6061 | +0.57 | +0.9% |
| Discouraged -> Other NEA | 0.1517 | 0.1473 | -0.44 | -2.9% |
| Other NEA -> Employed | 0.0203 | 0.0181 | -0.22 | -10.8% |
| Other NEA -> Unemployed | 0.0530 | 0.0520 | -0.10 | -1.9% |
| Other NEA -> Discouraged | 0.0322 | 0.0314 | -0.08 | -2.5% |
| Other NEA -> Other NEA | 0.8946 | 0.8984 | +0.38 | +0.4% |

Full detail in `qlfs_transition_sensitivity.csv` (its `absolute_difference_pp` column is now on
the same 0-100 percentage-point scale as this table -- CORRECTED 2026-09-14, it previously stored
a raw 0-1 proportion difference under a column name that claimed percentage points). The diagonal
(persistence) cells all move by
under 0.6 percentage points in absolute terms -- immaterial for the states that dominate the
population. But the RELATIVE picture on small off-diagonal cells is not uniformly small: the two
"-> Employed" cells from inactive-adjacent origins move by 9-11% in relative terms (Employed ->
Other NEA and Other NEA -> Employed), because their base rates are themselves small (2-3%), so the
same absolute change is a larger fraction of a smaller number. Absolute magnitude is what matters
for most practical purposes here, but a future user relying on a small transition probability
specifically (e.g. the inactive-to-employed flow) should be aware the relative sensitivity there is
larger than the headline diagonal comparison suggests.

**Flagged records only (n=483 with valid Status both waves, of 625 total):**

| origin | diagonal share | origin n |
| --- | --- | --- |
| Employed | 0.6971 | 208 |
| Unemployed | 0.4928 | 69 |
| Discouraged | 0.1875 | 32 |
| Other NEA | 0.6149 | 174 |

The flagged subgroup's transition rates are markedly less persistent than the clean panel's at
every origin state (e.g. Employed-Employed 69.7% vs. 91.0%; Discouraged-Discouraged 18.8% vs.
60.6%). This is consistent with -- though does not prove -- a meaningful share of the 625 flagged
records being roster mismatches (a different person occupying the same PERSONNO slot) rather than
genuine individual transitions, since a mismatched pair's "transition" is really two different
people's states compared to each other. It is also consistent with the flag simply correlating
with population subgroups that have less stable labour-market attachment. Both readings are
recorded; neither is adopted.

## What this does and does not settle

Settled: the demographic flags reproduce exactly; the flagged records are a small enough share
that excluding them moves diagonal transition shares by under 0.6pp (though some small
off-diagonal cells move by 9-11% in relative terms, with units now correctly on a 0-100 pp scale
in `qlfs_transition_sensitivity.csv`); the analysis population is defined by origin-age
eligibility (primary: 15+) rather than requiring destination-age eligibility too, so
destination-age exclusion (only possible under the 15-64 alternative) is reported separately from
genuine failed linkage instead of being folded into it; the age-15+ population is correctly
distinguished from the 15-64 "working-age" convention, with both reported; and failed linkage is
decomposed as far as the available fields allow (whole-dwelling non-continuity vs. within-dwelling
person-level non-match) without assuming a mechanical rotation percentage.

Not settled: whether the flagged records are genuine transitions or linkage errors; whether
whole-dwelling non-continuity is actually scheduled rotation (no rotation variable exists to
confirm it); any panel weighting correction for attrition or the rotating-panel design (everything
here is an unweighted sample diagnostic); and -- unchanged from the prior pass -- whether or how
any of this becomes a model calibration target, which depends on the still-unresolved
model-observation state mapping.
