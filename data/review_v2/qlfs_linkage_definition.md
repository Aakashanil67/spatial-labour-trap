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
`qlfs_linkage_flags.csv` and `qlfs_provisional_transitions.csv`.

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

## Status coverage and working-age attrition

The raw 67.5% match rate is not the right "attrition" figure for a Status-based transition target,
because `Status` is only derived for respondents aged 15+ -- children are a large share of the
denominator and cannot appear as a transition regardless of linkage:

| metric | value |
| --- | --- |
| 2025-Q4 total respondents | 63,264 |
| 2025-Q4 Status-eligible (age 15+) | 46,032 |
| 2026-Q1 total respondents | 62,819 |
| 2026-Q1 Status-eligible (age 15+) | 45,873 |
| Matched (UQNO+PERSONNO), both waves Status-eligible | 30,977 |
| Attrition among 2025-Q4 Status-eligible population | 32.7% |
| Attrition among 2026-Q1 Status-eligible population (back-attrition) | 32.5% |

Confirmed as an exact internal consistency check: 30,977 matched Status-eligible-both-waves
records is exactly the population size behind the transition matrix below (the "All" margin of
the raw matched-panel cross-tab). Missingness among the raw 42,695 matched records (11,718 with
`Status` unmapped in at least one wave) is 100% attributable to age under 15 in the affected wave,
confirmed live -- not a separate nonresponse problem.

**32.7% is a substantial attrition rate and should be treated as a real limitation of any survey
transition target built this way**, not a footnote. No design-based nonresponse weighting has been
applied to correct for it (unweighted counts throughout); whether QLFS's own panel weights address
this is not checked here.

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

**Excluding the 625 flagged records (n=30,494):**

| origin | diagonal share |
| --- | --- |
| Employed | 0.9104 |
| Unemployed | 0.7125 |
| Discouraged | 0.6061 |
| Other NEA | 0.8984 |

Excluding the flagged records moves every diagonal share by at most 0.006 -- the flagged records
are too small a share of the panel (2.0% of the Status-eligible matched population) to matter for
the aggregate transition rates, whichever reading of them is correct.

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

Settled: the demographic flags reproduce exactly, the flagged records are a small enough share
that excluding them barely moves the aggregate transition rates, and working-age attrition (32.7%)
is quantified rather than ignored.

Not settled: whether the flagged records are genuine transitions or linkage errors; any panel
weighting correction for attrition or the rotating-panel design; and -- unchanged from the prior
pass -- whether or how any of this becomes a model calibration target, which depends on the
still-unresolved model-observation state mapping.
