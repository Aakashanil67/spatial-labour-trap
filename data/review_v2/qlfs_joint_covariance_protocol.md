# QLFS joint stock-transition covariance: an implementable, review-only resampling protocol

15 September 2026. Written in response to Astra's `REVIEW_FOLLOWUP.md` deliverable 2. **This
is a specification, verified against live data where noted, with a runnable prototype and
synthetic acceptance tests -- it is NOT the production weighting matrix and is NOT wired into
`scripts/build_qlfs_candidate_moments.py`'s `main()` or any `data/moments.csv` value.** No
canonical target changes, no recalibration, no held-out run.

Prototype: `scripts/qlfs_joint_covariance_protocol.py`
(`joint_stock_transition_bootstrap()`). Synthetic tests:
`tests/test_qlfs_joint_covariance_protocol.py` (5 tests, all pass, no live microdata).

## Why the existing machinery cannot just be reused unchanged

`stock_cluster_bootstrap()` and `transition_cluster_bootstrap()`
(`scripts/build_qlfs_candidate_moments.py`) each run their OWN independent per-stratum
household draw. Even though both ultimately touch the 2026-Q1 cross-section (the stock
frame IS 2026-Q1; the transition frame's DESTINATION quarter IS 2026-Q1), resampling them
separately treats a household that appears in both as if its stock-side and transition-side
draws were independent, which they are not -- it is the same physical household. This
protocol's core change is: **one shared per-stratum household draw, applied to both frames in
the same replicate**, so a household that appears in both keeps the same replicate multiplier
on both sides.

## 1. Cluster and stratum keys, and their cross-quarter consistency

- **Cluster key**: `UQNO` (dwelling), matching every other QLFS resampling scheme already
  built in this project (no PSU field exists in any extract -- confirmed again this pass,
  see `source_manifest.json`).
- **Stratum key**: `Stratum`, read from the 2026-Q1 stock file for the stock side and as
  `Stratum_q4` (the origin quarter's own `Stratum` field, carried through
  `build_matched_panel()`'s merge) for the transition side.
- **Cross-quarter consistency, CHECKED LIVE this pass, not assumed**: for every one of the
  42,695 records in the unrestricted matched panel (2025-Q4 -> 2026-Q1), `Stratum_q4 ==
  Stratum_q1` exactly -- 0 mismatches. `Stratum` is confirmed to be a fixed geographic
  definition that does not change household-to-household across these two quarters, so using
  a single stratum key (the stock file's `Stratum`, equivalently `Stratum_q4`) for the joint
  design is safe. Command: see the live-verification snippet in this document's git history
  / session record; re-run with `THESIS_DATA_ROOT` set and `build_matched_panel()` from
  `scripts/build_qlfs_candidate_moments.py`.
- **Household overlap, CHECKED LIVE**: of the 2025-Q4 file's 19,945 distinct households,
  13,981 (70.1%) also appear in the 2026-Q1 file; of the 2026-Q1 file's 19,978 households,
  13,981 (70.0%) also appeared in 2025-Q4. 13,797 of the 2026-Q1 stock households have at
  least one person in the matched transition panel. This is the population the joint design
  actually links; the remainder is handled in Section 3.

## 2. How shared records receive common replicate multipliers

Per replicate (`joint_stock_transition_bootstrap()`):

1. Build the per-stratum household universe as the UNION of the stock frame's `UQNO` set and
   the matched frame's `UQNO` set within each stratum (in practice these are very nearly the
   same set per Section 1's overlap figures, but the union is taken explicitly rather than
   assumed).
2. For each stratum, draw `n_h` households WITH replacement from that stratum's OWN observed
   household set (`n_h` = the number of distinct households observed in that stratum this
   quarter) -- the same with-replacement PSU-style bootstrap already used throughout this
   project, applied at the dwelling level.
3. Build ONE multiplier map `{UQNO: draw_count}` for the whole replicate.
4. Apply that SAME map to both frames: a stock-frame record's weight is multiplied by
   `draw_count` for its `UQNO` (0 if not drawn); a transition-frame record's weight is
   multiplied by the SAME `draw_count` for its `UQNO`.
5. Compute all five moments (`discouraged_share`, `employment_share`, `long_term_share`,
   `u_to_e_quarterly`, `e_to_non_e_quarterly`) from this one replicate's data, and repeat for
   `n_boot` replicates. The resulting 5x5 sample covariance matrix IS the joint
   stock-transition covariance (previously the explicitly-documented gap).

**Synthetic verification of the mechanism itself** (not just its statistical consequence):
`TestMultiplierSharing::test_household_present_in_both_frames_gets_one_shared_multiplier`
patches the draw to a fixed, hand-chosen map and confirms both frames' point estimates match
a hand calculation under that exact map.

## 3. Unmatched, excluded and quarter-specific records

- **2025-Q4-only households** (households that fail to link into 2026-Q1 at all: 5,964 of
  19,945, i.e. the complement of the 70.1% overlap) never appear in `matched` (an inner join
  on `UQNO`+`PERSONNO`) and so never enter the transition estimator's domain, joint or
  otherwise. This protocol does not resample them and does not attempt to correct for
  selection into matching -- an existing, disclosed limitation of the transition estimator
  itself (complete-case; see `DECISIONS_PENDING.md` Question 4's missingness discussion and
  Deliverable 1 item 6 below), not something this covariance protocol newly introduces or
  newly fixes.
- **2026-Q1-only households** (in the stock frame but not the matched panel: 19,978 - 13,797
  = 6,181, i.e. new entrants to the sample or households whose 2025-Q4 members did not link)
  are drawn normally for the stock estimator and simply never touch the transition estimator
  -- no special handling needed, since the union-frame construction in Section 2 step 1
  already includes them in their stratum's household pool for the stock side only.
- **A matched-frame household whose `UQNO` is drawn 0 times this replicate** (possible even
  though its stratum's `n_h` matches the observed count, since with-replacement sampling can
  miss any given household) contributes nothing to either estimator that replicate -- this is
  the same "0 if not drawn" convention already used throughout the project's other cluster
  bootstraps, not a new rule.
- **Destination-status validity** (a matched record whose `Status_q1` is not a valid QLFS
  code): per the live clean-origin sample checked in the first repair batch, this is currently
  0 records for both populations -- carried forward as a fact, not re-checked this pass since
  no new evidence changes it (per the instruction to keep closed checks closed).

## 4. Quarter-specific person weights, population restrictions and linkage convention

- **Stock side**: 2026-Q1 `Weight`, expanded-labour-force restriction
  (`Status in {1,2,3}`), age restriction applied per `restrict_working_age(df, "Q14AGE")`
  BEFORE the replicate loop (population is a data-transform on the input frame, matching the
  existing `build_qlfs_candidate_moments.py` pattern -- see Deliverable 1's population
  recommendation for which restriction is primary).
- **Transition side**: 2025-Q4 `Weight_q4` (the ORIGIN quarter's weight -- unchanged from the
  existing `transition_point_estimates()`/`transition_cluster_bootstrap()` convention), the
  demographic-consistency linkage filter (`consistent`, stable gender + age change in {0,1})
  as PRIMARY, origin-age restriction applied to `Q14AGE_q4` per the same
  `restrict_working_age()` convention as the stock side's `Q14AGE` (both now consistently
  origin-quarter ages, per the finding-1 fix).
- **Both sides must use the SAME age-population label** for a given joint replicate run (e.g.
  both "15_64" or both "all_ages") -- this protocol does not mix populations across the two
  halves of one joint replicate, since doing so would make the resulting cross-covariance
  entries describe two different populations' relationship, not one population's internal
  covariance structure.

## 5. Assumptions from unavailable PSU/panel information, and the cross-survey matrix

- **No PSU field** (only `Stratum`+`UQNO`/dwelling) means this remains a dwelling-cluster
  approximation to the true PSU-level design, exactly the limitation already disclosed for
  the separate stock and transition bootstraps (`DECISIONS_PENDING.md` Question 6, corrected
  in the first repair batch) -- carried into the joint version unchanged, not worsened or
  improved by joining the two resamples.
- **No rotation/panel weight**: the transition side still has no official panel-adjustment
  weight to apply; `Weight_q4` is used as-is, matching the existing (non-joint) transition
  bootstrap's convention.
- **How this embeds in a later full matrix**: this protocol produces a 5x5 QLFS-only
  covariance block. Embedding it into a full moment covariance matrix that also includes the
  NHTS transport-to-wage ratio requires: (a) this 5x5 block as the top-left submatrix, (b) the
  transport ratio's own (currently scalar) bootstrap variance as the bottom-right 1x1 block,
  and (c) the off-diagonal blocks between them set to the DISCLOSED WORKING ASSUMPTION of
  zero cross-survey covariance (corrected in the first repair batch to be stated as an
  assumption, not an established fact). This stacking step is mechanical once both blocks
  exist; it is not performed here, since only the QLFS block is specified/prototyped this
  pass.

## 6. Synthetic acceptance fixtures and checks (implemented, `tests/test_qlfs_joint_covariance_protocol.py`)

| Check | Test | What it confirms |
| --- | --- | --- |
| Correct estimator labels | `TestOutputSchema::test_returns_exactly_the_five_named_estimators` | Output columns are exactly the five claimed moments |
| Symmetry and positive semidefiniteness | `TestOutputSchema::test_covariance_matrix_is_symmetric_and_positive_semidefinite` | `cov == cov.T`; smallest eigenvalue >= ~0 |
| Zero induced covariance (negative control) | `TestSharedHouseholdCovariance::test_zero_induced_covariance_when_frames_share_no_households_and_no_stratum` | Disjoint-stratum, disjoint-household frames show no spurious correlation (loose Monte Carlo bound, not exactly 0) |
| Nonzero induced covariance (positive control) | `TestSharedHouseholdCovariance::test_nonzero_induced_covariance_when_households_are_shared` | Shared households with correlated constructed outcomes produce a real, detectable positive correlation between a stock and a transition moment |
| Multiplier-sharing mechanism | `TestMultiplierSharing::test_household_present_in_both_frames_gets_one_shared_multiplier` | A fixed, hand-chosen multiplier map applies identically to both frames; point estimates match a hand calculation exactly |

Run: `pytest -q tests/test_qlfs_joint_covariance_protocol.py` (5 passed, no live microdata
required).

## What is NOT done here, stated precisely

- No live run against `THESIS_DATA_ROOT`'s real stock/matched frames through this prototype
  (Section 1's consistency/overlap figures were checked live via the EXISTING
  `load_quarter()`/`build_matched_panel()` functions, but `joint_stock_transition_bootstrap()`
  itself has only been exercised against synthetic fixtures).
- No integration into `build_qlfs_candidate_moments.py`'s `main()` or any `data/review_v2/*.csv`
  output.
- No embedding into a full NHTS+QLFS matrix (Section 5's stacking step).
- No adoption anywhere in `data/moments.csv` or any calibration code.

**If a next batch wants this run for real**: `joint_stock_transition_bootstrap(stock_df,
matched_df, n_boot=2000, seed=42)` against the live 2026-Q1 stock frame and the live matched
panel (both population-filtered consistently per Section 4) would produce the actual 5x5
covariance matrix directly -- the prototype is deliberately written close enough to
production shape that this is a small, low-risk follow-up, not a rebuild.
