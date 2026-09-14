"""P2.5 (+P2.1 design-effect consistency): QLFS candidate moments and joint
design-based covariance, review output only.

**Part A: extends the household-cluster bootstrap already established for
`separation_rate` to the two stock-share moments that still use only the Kish
approximation.** `configs/baseline.yaml`'s `separation_rate` already has a proper
stratified household-cluster bootstrap (notebook 03 Part B, committed) -- resampling
whole households (`UQNO`) with replacement within each `Stratum`, because no PSU or
rotation-group field exists in any QLFS extract (confirmed by a keyword search of
every column name and label, notebook 03's own design-variable audit). But
`discouraged_share` (notebook 01) and `long_term_share` (notebook 03 Part A) still use
only the Kish approximate-design-effect SE, unlike `separation_rate` in the SAME
notebook file. This is a within-project inconsistency, not a missing method -- the
method already exists and is already reviewed; it just was not applied to these two
moments. This script applies the SAME clustering scheme to them, as a review-only
comparison. It does NOT write to `data/moments.csv` -- the canonical SEs are
unchanged.

**Part B: candidate U-to-E and E-to-non-E quarterly endpoint transition moments**,
person-weighted, with explicit origin populations, matching the plan's P2.5 checklist
("Define U-to-E and E-to-non-E as distinct quarterly endpoint probabilities"). Primary
population uses the SAME demographic-consistency linkage filter (stable gender, age
change of 0 or 1) already established for `separation_rate`; the raw (unfiltered)
linkage is reported as a sensitivity, exactly mirroring `separation_rate`'s own
raw-vs-consistent distinction. **No compounding conversion to a monthly hazard is used
as the primary quantity** -- DECISIONS_PENDING.md Question 6 explicitly rejects that
conversion for the job-finding rate on the same grounds it was rejected for
`separation_rate`; a monthly-equivalent is reported only as an explicit, separately
labelled sensitivity, never as the headline number.

**Part C: joint (not one-moment-at-a-time) bootstrap covariance.** Each replicate
resamples households ONCE and computes ALL of a quarter's stock moments
(`discouraged_share`, `long_term_share`, `employment_share`) together from that one
replicate, since they share the same 2026-Q1 respondent pool; separately, each
transition replicate resamples ONCE and computes U-to-E and E-to-non-E together, since
they share the same 2025-Q4->2026-Q1 matched-pair pool. This gives the actual sampling
covariance of these specific estimators on this specific sample, not an assumed-
independent stack of separately-bootstrapped SEs (which the plan explicitly warns
against: "Calculate sampling covariance for the actual selected estimators, not for a
differently pooled sample").

**Explicitly NOT computed, documented as a limitation rather than silently assumed:**
covariance BETWEEN the stock bootstrap and the transition bootstrap. The 2026-Q1 stock
respondents and the transition's destination-quarter (2026-Q1) respondents overlap
substantially, so a real dependency likely exists between them, but capturing it would
require jointly resampling across both quarters' designs at once, which this script
does not attempt.

**Cross-survey covariance (NHTS transport vs. any QLFS moment here) is treated as zero
as an explicit WORKING ASSUMPTION for this stylised exercise, not a proven fact.**
NHTS (2020) and QLFS (2025-2026) are separate StatsSA survey administrations in
different years; no shared-household identifier or shared design document has been
checked to positively rule out overlap. The two sampling frames are not shown here to
be disjoint, only assumed so, following Astra's 2026-09-14 correction of an earlier,
overstated "zero by construction" claim. The block-diagonal covariance matrix this
implies is a mechanical construction under that assumption, not independent evidence
for it.

**Withdrawn overclaim, 2026-09-14 (Astra review):** an earlier version of this
docstring, and `qlfs_design_effect_comparison.csv`'s accompanying prose, stated that
the household-cluster bootstrap SE being 12-35% larger than Kish "confirms" or
"establishes" that Kish understates the TRUE design-based uncertainty by that margin.
That does not follow: `UQNO` identifies a dwelling, and QLFS's design has a
primary-sampling-unit stage above the dwelling that this bootstrap does not resample
(no PSU field survives in any of the four extracts -- confirmed by a full
column-name-and-label search). A household/dwelling-cluster bootstrap captures
within-household dependence and improves on Kish's no-clustering assumption, but it
does not automatically reproduce between-household, within-PSU dependence, so it is
not shown to equal the true design-based SE. The 12-35% figures are reported below as
a comparison between two specific, named approximations, not as a validated
correction factor.

Usage:
    python -m scripts.build_qlfs_candidate_moments

Requires THESIS_DATA_ROOT set. Writes (all keyed by an explicit `population` column,
"all_ages" or "15_64" -- see the 2026-09-14 age-alignment fix below):
    data/review_v2/qlfs_candidate_moments.csv
    data/review_v2/qlfs_stock_moment_covariance.csv
    data/review_v2/qlfs_transition_moment_covariance.csv
    data/review_v2/qlfs_design_effect_comparison.csv

**Age-alignment fix, 2026-09-14 (Astra review, finding 1).** `STOCK_COLS` previously
omitted `Q14AGE`, so the stock calculation could not impose the 15-64 filter it
claimed to apply, and the transition bootstrap/covariance resampled only the
unrestricted `matched` panel even though `qlfs_candidate_moments.csv` reported
separate 15-64 point estimates. Both are fixed: `Q14AGE` is now loaded, stock point
estimates and the stock bootstrap are computed separately for both populations, and
the transition bootstrap/covariance is computed separately for both `matched` and
`matched_15_64`. Every output CSV carries an explicit `population` column so the two
are never silently conflated. A regression fixture with over-64 respondents
(`tests/test_qlfs_candidate_moments.py::TestRestrictWorkingAge`) now fails if the age
filter stops being applied.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "data" / "review_v2"

STOCK_COLS = ["Status", "Long_term_unempl", "Weight", "UQNO", "Stratum", "Q14AGE"]
PANEL_COLS = ["Status", "Q13GENDER", "Q14AGE", "Weight", "UQNO", "PERSONNO", "Stratum"]
N_BOOT = 2000
SEED = 42
WORKING_AGE_LO = 15
WORKING_AGE_HI = 64


def load_quarter(path: Path, cols: list[str], encoding: str | None = None) -> pd.DataFrame:
    df, _meta = pyreadstat.read_dta(
        str(path), usecols=cols, apply_value_formats=False, encoding=encoding
    )
    df["UQNO"] = df["UQNO"].astype(str).str.strip()
    return df


def restrict_working_age(
    df: pd.DataFrame, age_col: str, lo: int = WORKING_AGE_LO, hi: int = WORKING_AGE_HI
) -> pd.DataFrame:
    """Filters to ages [lo, hi] inclusive. The caller is responsible for passing the
    correct age column -- for the matched panel this must be the ORIGIN quarter's age
    (e.g. `Q14AGE_q4`), not the destination quarter's, per the plan's separately
    documented origin-age/end-point rule."""
    age = pd.to_numeric(df[age_col], errors="coerce")
    return df[age.between(lo, hi)]


def kish_se(p_hat: float, w: np.ndarray) -> float:
    n = len(w)
    deff = (w**2).sum() * n / (w.sum() ** 2)
    n_eff = n / deff
    return float(np.sqrt(p_hat * (1 - p_hat) / n_eff))


# --- Part A: stock moments and their design-based (cluster) bootstrap -------------


def stock_point_estimates(df: pd.DataFrame) -> dict:
    elf = df[df["Status"].isin([1, 2, 3])]  # Employed, Unemployed, Discouraged
    w = elf["Weight"].to_numpy()
    discouraged_share = float(np.average((elf["Status"] == 3).to_numpy(dtype=float), weights=w))
    employment_share = float(np.average((elf["Status"] == 1).to_numpy(dtype=float), weights=w))

    unemployed = df[df["Long_term_unempl"].isin([1, 2])]
    wu = unemployed["Weight"].to_numpy()
    long_term_share = float(
        np.average((unemployed["Long_term_unempl"] == 1).to_numpy(dtype=float), weights=wu)
    )
    return dict(
        discouraged_share=discouraged_share,
        employment_share=employment_share,
        long_term_share=long_term_share,
        n_expanded_lf=len(elf),
        n_unemployed=len(unemployed),
        kish_se_discouraged=kish_se(discouraged_share, w),
        kish_se_employment=kish_se(employment_share, w),
        kish_se_long_term=kish_se(long_term_share, wu),
    )


def stock_cluster_bootstrap(
    df: pd.DataFrame, n_boot: int = N_BOOT, seed: int = SEED
) -> pd.DataFrame:
    """Resamples UQNO clusters with replacement, stratified by Stratum -- the SAME
    scheme already established for separation_rate -- and computes all three stock
    shares together from each replicate."""
    strata = df.groupby("Stratum")["UQNO"].unique().to_dict()
    rng = np.random.default_rng(seed)

    status = df["Status"].to_numpy()
    long_term = df["Long_term_unempl"].to_numpy()
    w0 = df["Weight"].to_numpy()
    uqno = df["UQNO"].to_numpy()

    rows = []
    for _ in range(n_boot):
        mult_map: dict[str, int] = {}
        for hh_ids in strata.values():
            n_h = len(hh_ids)
            draws = rng.choice(hh_ids, size=n_h, replace=True)
            vals, counts = np.unique(draws, return_counts=True)
            for v, c in zip(vals, counts, strict=True):
                mult_map[v] = mult_map.get(v, 0) + int(c)
        mult = np.array([mult_map.get(u, 0) for u in uqno], dtype=float)
        w = w0 * mult

        elf = np.isin(status, [1, 2, 3]) & (mult > 0)
        d_share = np.average((status[elf] == 3).astype(float), weights=w[elf])
        e_share = np.average((status[elf] == 1).astype(float), weights=w[elf])

        unemp = np.isin(long_term, [1, 2]) & (mult > 0)
        lt_share = np.average((long_term[unemp] == 1).astype(float), weights=w[unemp])

        rows.append(
            dict(discouraged_share=d_share, employment_share=e_share, long_term_share=lt_share)
        )
    return pd.DataFrame(rows)


# --- Part B: transition moments and their design-based (cluster) bootstrap --------


def build_matched_panel(q4: pd.DataFrame, q1: pd.DataFrame) -> pd.DataFrame:
    m = q4.merge(q1, on=["UQNO", "PERSONNO"], suffixes=("_q4", "_q1"), how="inner")
    gender_stable = m["Q13GENDER_q4"].astype(str) == m["Q13GENDER_q1"].astype(str)
    age_diff = pd.to_numeric(m["Q14AGE_q1"], errors="coerce") - pd.to_numeric(
        m["Q14AGE_q4"], errors="coerce"
    )
    m["consistent"] = gender_stable & age_diff.isin([0, 1])
    return m


def transition_point_estimates(matched: pd.DataFrame, consistent_only: bool) -> dict:
    m = matched[matched["consistent"]] if consistent_only else matched
    w = m["Weight_q4"].to_numpy()

    unemployed_t0 = (m["Status_q4"] == 2).to_numpy()
    u_to_e = float(
        np.average(
            (m.loc[unemployed_t0, "Status_q1"] == 1).to_numpy(dtype=float), weights=w[unemployed_t0]
        )
    )
    employed_t0 = (m["Status_q4"] == 1).to_numpy()
    e_to_non_e = float(
        np.average(
            (m.loc[employed_t0, "Status_q1"] != 1).to_numpy(dtype=float), weights=w[employed_t0]
        )
    )
    return dict(
        u_to_e_quarterly=u_to_e,
        e_to_non_e_quarterly=e_to_non_e,
        n_unemployed_origin=int(unemployed_t0.sum()),
        n_employed_origin=int(employed_t0.sum()),
        u_to_e_monthly_compounded_SENSITIVITY_ONLY=1 - (1 - u_to_e) ** (1 / 3),
        e_to_non_e_monthly_compounded_SENSITIVITY_ONLY=1 - (1 - e_to_non_e) ** (1 / 3),
    )


def transition_cluster_bootstrap(
    matched: pd.DataFrame, consistent_only: bool, n_boot: int = N_BOOT, seed: int = SEED
) -> pd.DataFrame:
    m = matched[matched["consistent"]] if consistent_only else matched
    strata = m.groupby("Stratum_q4")["UQNO"].unique().to_dict()
    rng = np.random.default_rng(seed)

    status_q4 = m["Status_q4"].to_numpy()
    status_q1 = m["Status_q1"].to_numpy()
    w0 = m["Weight_q4"].to_numpy()
    uqno = m["UQNO"].to_numpy()

    rows = []
    for _ in range(n_boot):
        mult_map: dict[str, int] = {}
        for hh_ids in strata.values():
            n_h = len(hh_ids)
            draws = rng.choice(hh_ids, size=n_h, replace=True)
            vals, counts = np.unique(draws, return_counts=True)
            for v, c in zip(vals, counts, strict=True):
                mult_map[v] = mult_map.get(v, 0) + int(c)
        mult = np.array([mult_map.get(u, 0) for u in uqno], dtype=float)
        w = w0 * mult

        unemployed_t0 = (status_q4 == 2) & (mult > 0)
        u_to_e = np.average((status_q1[unemployed_t0] == 1).astype(float), weights=w[unemployed_t0])
        employed_t0 = (status_q4 == 1) & (mult > 0)
        e_to_non_e = np.average((status_q1[employed_t0] != 1).astype(float), weights=w[employed_t0])
        rows.append(dict(u_to_e_quarterly=u_to_e, e_to_non_e_quarterly=e_to_non_e))
    return pd.DataFrame(rows)


def _cov_to_long(cov_df: pd.DataFrame, population: str) -> pd.DataFrame:
    long = cov_df.reset_index().rename(columns={"index": "moment_i"})
    long = long.melt(id_vars="moment_i", var_name="moment_j", value_name="covariance")
    long.insert(0, "population", population)
    return long


def main() -> None:
    data_root = Path(os.environ["THESIS_DATA_ROOT"])
    q1_path = data_root / "qlfs-2026-q1-v1" / "qlfs-2026-q1-v1.dta"
    q4_path = data_root / "qlfs-2025-04" / "qlfs-2025-q4-v1.dta"

    stock_df_full = load_quarter(q1_path, STOCK_COLS, encoding="latin1")
    stock_populations = {
        "all_ages": stock_df_full,
        "15_64": restrict_working_age(stock_df_full, "Q14AGE"),
    }
    print(
        f"Stock age restriction: {len(stock_df_full) - len(stock_populations['15_64'])} of "
        f"{len(stock_df_full)} raw records fall outside {WORKING_AGE_LO}-{WORKING_AGE_HI} "
        f"(restriction applied before computing expanded-labour-force membership, so this "
        f"count includes rows outside the expanded labour force too)"
    )

    stock_cov_frames = []
    design_rows = []
    for population, stock_df in stock_populations.items():
        point = stock_point_estimates(stock_df)
        print(f"\n=== Stock point estimates (2026-Q1, population={population}) ===")
        print(point)

        boot = stock_cluster_bootstrap(stock_df)
        cov = boot[["discouraged_share", "employment_share", "long_term_share"]].cov()
        stock_cov_frames.append(_cov_to_long(cov, population))

        for key, kish_key in [
            ("discouraged_share", "kish_se_discouraged"),
            ("employment_share", "kish_se_employment"),
            ("long_term_share", "kish_se_long_term"),
        ]:
            cluster_se = float(boot[key].std(ddof=1))
            design_rows.append(
                dict(
                    population=population,
                    moment=key,
                    point_estimate=round(point[key], 6),
                    kish_se=round(point[kish_key], 6),
                    household_cluster_bootstrap_se=round(cluster_se, 6),
                    ratio_cluster_to_kish=round(cluster_se / point[kish_key], 3),
                )
            )

    pd.concat(stock_cov_frames, ignore_index=True).to_csv(
        OUT_DIR / "qlfs_stock_moment_covariance.csv", index=False
    )
    print(f"\nWrote {OUT_DIR / 'qlfs_stock_moment_covariance.csv'} (population-keyed)")

    design_df = pd.DataFrame(design_rows)
    design_df.to_csv(OUT_DIR / "qlfs_design_effect_comparison.csv", index=False)
    print(f"\nWrote {OUT_DIR / 'qlfs_design_effect_comparison.csv'} (population-keyed)")
    print(design_df.to_string(index=False))

    q4_panel = load_quarter(q4_path, PANEL_COLS)
    q1_panel = load_quarter(q1_path, PANEL_COLS, encoding="latin1")
    matched = build_matched_panel(q4_panel, q1_panel)
    n_consistent = int(matched["consistent"].sum())
    print(f"\nMatched panel (2025-Q4 -> 2026-Q1): n={len(matched)}, consistent={n_consistent}")

    matched_15_64 = restrict_working_age(matched, "Q14AGE_q4")
    n_age_excluded = len(matched) - len(matched_15_64)
    print(
        f"Origin-age (15-64) restriction: {n_age_excluded} of {len(matched)} matched "
        f"records excluded. Applied to the panel ORIGIN quarter (Q14AGE_q4) for transitions "
        f"and to the 2026-Q1 stock file (Q14AGE) for stocks -- these are two separate "
        f"restrictions on two separate samples, both now labelled 'population' in every "
        f"output CSV, not a single shared filter."
    )

    transition_populations = {"15_plus_origin_age": matched, "15_64_origin_age": matched_15_64}

    candidate_rows = []
    for age_label, frame in transition_populations.items():
        for consistent_only, link_label in [
            (True, "consistent_PRIMARY"),
            (False, "raw_sensitivity"),
        ]:
            pe = transition_point_estimates(frame, consistent_only)
            pe["linkage"] = link_label
            pe["age_population"] = age_label
            candidate_rows.append(pe)
    candidate_df = pd.DataFrame(candidate_rows)
    candidate_df.to_csv(OUT_DIR / "qlfs_candidate_moments.csv", index=False)
    print(f"\nWrote {OUT_DIR / 'qlfs_candidate_moments.csv'}")
    print(candidate_df.to_string(index=False))

    transition_cov_frames = []
    for age_label, frame in transition_populations.items():
        tboot = transition_cluster_bootstrap(frame, consistent_only=True)
        tcov = tboot[["u_to_e_quarterly", "e_to_non_e_quarterly"]].cov()
        transition_cov_frames.append(_cov_to_long(tcov, age_label))
        print(
            f"\n[{age_label}] u_to_e cluster bootstrap SE: "
            f"{tboot['u_to_e_quarterly'].std(ddof=1):.5f}, e_to_non_e cluster bootstrap SE: "
            f"{tboot['e_to_non_e_quarterly'].std(ddof=1):.5f}"
        )
    pd.concat(transition_cov_frames, ignore_index=True).to_csv(
        OUT_DIR / "qlfs_transition_moment_covariance.csv", index=False
    )
    print(
        f"\nWrote {OUT_DIR / 'qlfs_transition_moment_covariance.csv'} "
        f"(population-keyed: {list(transition_populations)})"
    )


if __name__ == "__main__":
    main()
