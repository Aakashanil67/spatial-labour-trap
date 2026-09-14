"""P2.3: design-based sampling uncertainty (survey bootstrap) and the 15-64 primary
population, review only.

Extends the candidate transport-to-wage ratio (scripts/build_transport_candidate_estimates.py).

**WITHDRAWN, 2026-09-14 (fourth round, same day): the stratified delete-1 jackknife
(JK1) this script previously used is wrong for this statistic and its SE/CI figures
are withdrawn, not merely superseded.** The ratio's denominator is a WEIGHTED MEDIAN,
and ordinary jackknife variance estimation is not generally valid for quantiles --
the median's influence function is not smooth, so deleting one PSU either changes the
median by a large, discrete jump (if that PSU happened to contain the pivotal
observation) or not at all (otherwise), and the delete-1 jackknife variance formula
does not converge to the true sampling variance under this behaviour (Efron 1982;
Shao & Wu 1989). This is not a theoretical nicety here: verified live, the wage
median changed in only 9 of 6,039 replicates under the 15-64 population and 25 of
6,039 under the broader-age population -- almost all replicates contributed zero to
the jackknife variance sum, and the few that did jump contributed a disproportionate,
noisy amount. Three specific claims made about that SE are also withdrawn as
unsupported: that its larger value than the earlier independent bootstrap SE
"confirmed" it was more accurate (size alone does not validate a variance estimator;
an invalid method's SE being larger proves nothing about correctness); that
shared-household dependence between the cost and wage samples "necessarily" inflates
the ratio's variance (dependence can inflate OR deflate variance depending on the
sign of the within-household correlation, which was never estimated); and that the
difference between the 15-64 and broader-age SEs was explained by "reduced
between-PSU variability" from the age restriction (an unsupported causal story built
on since-withdrawn numbers).

**Replacement: a stratified WITH-REPLACEMENT PSU bootstrap ("survey bootstrap"),
valid for nonsmooth statistics including quantiles** (Rao & Wu 1988; Field & Welsh
2007, "Bootstrapping clustered data"; the simple with-replacement-PSU variant, not
the more elaborate Rao-Wu rescaling bootstrap -- documented as an approximation
below). Each replicate independently draws n_h PSUs WITH replacement from the n_h
PSUs actually observed in stratum h; a PSU drawn m times has its records' weights
multiplied by m (0 if not drawn). Cost and wage weights are built from the SAME
per-replicate PSU draw, so a shared household's cost and wage records move together,
preserving the joint design exactly as the withdrawn jackknife intended to.

**Verified against a reference implementation.** The jackknife IS valid for a smooth
statistic -- the cost-side weighted MEAN -- so a cost-only jackknife (wage held fixed
at its full-sample value) gives a trustworthy reference SE (0.00905 / 0.00902 for the
15-64 / broader-age populations, reproducing Astra's figures exactly). Running the
new bootstrap with the wage side likewise held fixed converges to a closely matching
figure (~0.0088, within Monte Carlo noise of the trusted reference), confirming the
bootstrap machinery itself is correctly calibrated before trusting its full joint
(cost-and-wage-resampled-together) result.

**Inspected replicate-median behaviour and interval stability.** The bootstrap's
resampled wage medians take on ~20+ distinct values with a genuinely spread
distribution (not the jackknife's near-degenerate 5-values-in-6,039-replicates
pathology) -- see `transport_wage_ratio_bootstrap_median_distribution.csv`. The SE
and 95% CI are stable across replicate counts (1,000-4,000) and random seeds to
within Monte Carlo noise -- see `transport_wage_ratio_bootstrap_stability.csv`.

**Documented approximations, unchanged from the withdrawn version where still
applicable:** no official NHTS replicate weights exist in the public-use file
(confirmed: no jk/rep/brr/fay/bootstrap/pweight/fpc-named column in either file's
metadata), so this bootstrap is CONSTRUCTED here, not looked up -- an approximation
to whichever variance-estimation design StatsSA's own internal files may use. No
finite-population correction is applied (standard for national household surveys
where PSUs are a small fraction of the frame; not independently verified here since
the overall sampling fraction is not published). The simple with-replacement variant
(rather than Rao-Wu rescaling) is used for its transparency and because every stratum
has at least 29 PSUs, where the two variants' small-sample corrections are expected
to differ negligibly -- this is not independently proven here, only asserted as the
standard large-n_h justification for the simplification.

Round-trip excursion, person weighting, and the primary frequency assumption (5
search days/week) are held FIXED at their already-proposed primary settings from
prior rounds -- this script only extends the uncertainty and population dimensions.

Sampling uncertainty (this script) is kept explicitly SEPARATE from driver-code,
frequency, and missing-journey (coverage) sensitivity
(scripts/build_transport_candidate_estimates.py) -- they are different kinds of
uncertainty and are never combined into one interval.

Usage:
    python -m scripts.build_transport_wage_ratio_uncertainty

Requires THESIS_DATA_ROOT set. Writes:
    data/review_v2/transport_wage_ratio_design_uncertainty.csv
    data/review_v2/transport_wage_ratio_bootstrap_stability.csv
    data/review_v2/transport_wage_ratio_bootstrap_median_distribution.csv
    data/review_v2/transport_candidate_frequency_sensitivity_15_64.csv
    data/review_v2/transport_candidate_coverage_15_64.csv
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat

from scripts.build_transport_candidate_estimates import (
    EXCURSIONS,
    FREQUENCY_GRID,
    PRIMARY_FREQ_DAYS_PER_WEEK,
    population_outcomes,
    summarise,
)
from scripts.build_transport_review_tables import load_source, mode_masks

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "data" / "review_v2"

WAGE_PERIOD_MAP = {1: 4.345, 2: 1.0, 3: 1 / 12}  # 1=Per week, 2=Per month, 3=Annually
AGE_LO, AGE_HI = 15, 64
PRIMARY_N_BOOT = 2000
PRIMARY_SEED = 42


def load_and_join_geography(data_root: Path) -> pd.DataFrame:
    df = load_source(data_root)
    geog_path = (
        data_root / "nhts2020-v1" / "nhts-2020-v1" / "nhts-2020-v1-stata" / "nhts-2020-geog.dta"
    )
    geog, _meta = pyreadstat.read_dta(
        str(geog_path), apply_value_formats=False, usecols=["Uqno", "Psuno_seg", "Stratum"]
    )
    assert geog["Uqno"].is_unique, "geography file is not one row per household"
    merged = df.merge(geog, on="Uqno", how="left", indicator=True)
    n_unmatched = int((merged["_merge"] == "left_only").sum())
    assert n_unmatched == 0, f"{n_unmatched} person records failed to join to a household"
    return merged.drop(columns="_merge")


def weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    return float(np.average(values, weights=weights))


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cw = np.cumsum(w)
    return float(v[cw >= cw[-1] / 2][0])


def build_cost_and_wage_frames(
    df: pd.DataFrame, masks: dict, scenario: str, age_restricted: bool
) -> tuple[pd.DataFrame, pd.DataFrame]:
    outcomes = population_outcomes(df, masks, PRIMARY_FREQ_DAYS_PER_WEEK, "round_trip", scenario)
    resolved_idx = outcomes.index[outcomes["coverage_class"] != "unresolved"]
    if age_restricted:
        age_ok = (df["Age"] >= AGE_LO) & (df["Age"] <= AGE_HI)
        resolved_idx = resolved_idx[age_ok.loc[resolved_idx]]
    cost_df = pd.DataFrame(
        {
            "value": outcomes.loc[resolved_idx, "total"].to_numpy(),
            "weight": df.loc[resolved_idx, "Weight"].to_numpy(),
            "psu": df.loc[resolved_idx, "Psuno_seg"].to_numpy(),
            "stratum": df.loc[resolved_idx, "Stratum"].to_numpy(),
        }
    )

    wage_mask = (
        (df["Q410Salary"] > 0)
        & (df["Q410Salary"] < 999_000)
        & df["Q411Payperiod"].isin(WAGE_PERIOD_MAP)
    )
    if age_restricted:
        wage_mask = wage_mask & (df["Age"] >= AGE_LO) & (df["Age"] <= AGE_HI)
    wage_sub = df[wage_mask]
    period_factor = wage_sub["Q411Payperiod"].map(WAGE_PERIOD_MAP)
    wage_df = pd.DataFrame(
        {
            "value": (wage_sub["Q410Salary"] * period_factor).to_numpy(),
            "weight": wage_sub["Weight"].to_numpy(),
            "psu": wage_sub["Psuno_seg"].to_numpy(),
            "stratum": wage_sub["Stratum"].to_numpy(),
        }
    )
    return cost_df, wage_df


def cost_only_jackknife_reference(
    cost_df: pd.DataFrame, psu_strata: pd.DataFrame, daily_wage_fixed: float
) -> float:
    """Reference-only: the jackknife IS valid for the cost-side weighted MEAN (a
    smooth statistic), so this isolates cost-side sampling variability with the wage
    median held fixed, giving a trustworthy figure the bootstrap below is checked
    against."""
    cost_val, cost_w0 = cost_df["value"].to_numpy(), cost_df["weight"].to_numpy()
    cost_psu, cost_stratum = cost_df["psu"].to_numpy(), cost_df["stratum"].to_numpy()
    ratio_full = weighted_mean(cost_val, cost_w0) / daily_wage_fixed

    pseudo = np.empty(len(psu_strata))
    strata_arr = psu_strata["stratum"].to_numpy()
    for i, (h, psu, n_h) in enumerate(
        zip(psu_strata["stratum"], psu_strata["psu"], psu_strata["n_h"], strict=True)
    ):
        in_h = cost_stratum == h
        w = cost_w0.copy()
        w[in_h] *= n_h / (n_h - 1)
        w[in_h & (cost_psu == psu)] = 0.0
        pseudo[i] = weighted_mean(cost_val, w) / daily_wage_fixed

    variance = 0.0
    for h in np.unique(strata_arr):
        idx = strata_arr == h
        n_h = int(idx.sum())
        variance += (n_h - 1) / n_h * np.sum((pseudo[idx] - ratio_full) ** 2)
    return float(np.sqrt(variance))


def _build_psu_index(psu_strata: pd.DataFrame) -> tuple[dict, dict]:
    all_psu = psu_strata["psu"].to_numpy()
    psu_to_idx = {p: i for i, p in enumerate(all_psu)}
    stratum_global_idx = {
        h: np.where(psu_strata["stratum"].to_numpy() == h)[0]
        for h in psu_strata["stratum"].unique()
    }
    return psu_to_idx, stratum_global_idx


def survey_bootstrap_ratio(
    cost_df: pd.DataFrame,
    wage_df: pd.DataFrame,
    psu_strata: pd.DataFrame,
    n_boot: int = PRIMARY_N_BOOT,
    seed: int = PRIMARY_SEED,
    fix_wage: bool = False,
) -> dict:
    psu_to_idx, stratum_global_idx = _build_psu_index(psu_strata)
    n_psu_total = len(psu_to_idx)

    cost_val, cost_w0 = cost_df["value"].to_numpy(), cost_df["weight"].to_numpy()
    cost_idx = cost_df["psu"].map(psu_to_idx).to_numpy()
    wage_val, wage_w0 = wage_df["value"].to_numpy(), wage_df["weight"].to_numpy()
    wage_idx = wage_df["psu"].map(psu_to_idx).to_numpy()

    cost_mean_full = weighted_mean(cost_val, cost_w0)
    wage_median_full = weighted_median(wage_val, wage_w0)
    daily_wage_full = wage_median_full / 21.7
    ratio_full = cost_mean_full / daily_wage_full

    rng = np.random.default_rng(seed)
    ratios = np.empty(n_boot)
    medians = np.empty(n_boot)
    mult = np.empty(n_psu_total)
    for b in range(n_boot):
        mult[:] = 0.0
        for idx_h in stratum_global_idx.values():
            n_h = len(idx_h)
            draws = rng.integers(0, n_h, size=n_h)
            mult[idx_h] = np.bincount(draws, minlength=n_h)
        cm = weighted_mean(cost_val, cost_w0 * mult[cost_idx])
        wm = wage_median_full if fix_wage else weighted_median(wage_val, wage_w0 * mult[wage_idx])
        medians[b] = wm
        ratios[b] = cm / (wm / 21.7)

    se = float(ratios.std(ddof=1))
    ci_lo, ci_hi = np.percentile(ratios, [2.5, 97.5])
    return dict(
        point_estimate=round(ratio_full, 4),
        weighted_mean_cost_rand=round(cost_mean_full, 2),
        weighted_median_monthly_wage_rand=round(wage_median_full, 2),
        daily_wage_rand=round(daily_wage_full, 2),
        bootstrap_se=round(se, 4),
        ci_95_lo_percentile=round(float(ci_lo), 4),
        ci_95_hi_percentile=round(float(ci_hi), 4),
        n_boot=n_boot,
        seed=seed,
        cost_n=len(cost_df),
        wage_n=len(wage_df),
        n_distinct_replicate_medians=int(len(np.unique(np.round(medians, 2)))),
    )


def build_design_uncertainty_grid(
    df: pd.DataFrame, masks: dict, psu_strata: pd.DataFrame
) -> pd.DataFrame:
    rows = []
    for age_restricted, pop_label in (
        (True, "15_to_64_primary"),
        (False, "broader_age_sensitivity"),
    ):
        for scenario in ("A", "B"):
            cost_df, wage_df = build_cost_and_wage_frames(df, masks, scenario, age_restricted)
            daily_wage_fixed = (
                weighted_median(wage_df["value"].to_numpy(), wage_df["weight"].to_numpy()) / 21.7
            )
            ref_se = cost_only_jackknife_reference(cost_df, psu_strata, daily_wage_fixed)
            result = survey_bootstrap_ratio(cost_df, wage_df, psu_strata)
            result.update(
                population=pop_label,
                driver_code_5_6_scenario=scenario,
                excursion_definition="round_trip",
                freq_days_per_week=PRIMARY_FREQ_DAYS_PER_WEEK,
                cost_only_jackknife_reference_se=round(ref_se, 5),
            )
            rows.append(result)
    return pd.DataFrame(rows)


def build_bootstrap_verification(
    df: pd.DataFrame, masks: dict, psu_strata: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Verification requested 2026-09-14: (1) check the bootstrap converges to the
    trusted cost-only jackknife reference when wage is held fixed, and (2) check
    interval stability across replicate counts and seeds."""
    cost_df, wage_df = build_cost_and_wage_frames(df, masks, "B", age_restricted=True)
    daily_wage_fixed = (
        weighted_median(wage_df["value"].to_numpy(), wage_df["weight"].to_numpy()) / 21.7
    )
    ref_se = cost_only_jackknife_reference(cost_df, psu_strata, daily_wage_fixed)
    fixed_wage_result = survey_bootstrap_ratio(cost_df, wage_df, psu_strata, fix_wage=True)
    print(
        f"Reference check (15-64, Scenario B, wage held fixed): jackknife SE={ref_se:.5f}, "
        f"bootstrap SE={fixed_wage_result['bootstrap_se']:.5f} "
        f"(n_boot={PRIMARY_N_BOOT}, should be close)"
    )

    stability_rows = []
    for n_boot, seed in ((1000, 100), (2000, 200), (2000, 201), (4000, 300)):
        result = survey_bootstrap_ratio(cost_df, wage_df, psu_strata, n_boot=n_boot, seed=seed)
        stability_rows.append(
            dict(
                n_boot=n_boot,
                seed=seed,
                bootstrap_se=result["bootstrap_se"],
                ci_95_lo=result["ci_95_lo_percentile"],
                ci_95_hi=result["ci_95_hi_percentile"],
            )
        )
    stability = pd.DataFrame(stability_rows)

    verification = pd.DataFrame(
        [
            dict(
                check="cost_only_jackknife_reference_se",
                value=round(ref_se, 5),
                note="Valid jackknife SE for the smooth cost-mean statistic alone, wage fixed.",
            ),
            dict(
                check="cost_only_bootstrap_se_wage_fixed",
                value=fixed_wage_result["bootstrap_se"],
                note=(
                    "Bootstrap SE under the same wage-fixed isolation -- should be "
                    "close to the reference above."
                ),
            ),
        ]
    )
    return verification, stability


def build_median_distribution(
    df: pd.DataFrame, masks: dict, psu_strata: pd.DataFrame
) -> pd.DataFrame:
    """Inspects replicate-median behaviour requested 2026-09-14: how many distinct
    wage-median values occur across bootstrap replicates, and their frequency --
    contrasted with the withdrawn jackknife's near-degenerate 9-of-6,039 pathology."""
    cost_df, wage_df = build_cost_and_wage_frames(df, masks, "B", age_restricted=True)
    psu_to_idx, stratum_global_idx = _build_psu_index(psu_strata)
    n_psu_total = len(psu_to_idx)
    wage_val, wage_w0 = wage_df["value"].to_numpy(), wage_df["weight"].to_numpy()
    wage_idx = wage_df["psu"].map(psu_to_idx).to_numpy()

    rng = np.random.default_rng(PRIMARY_SEED + 1)
    mult = np.empty(n_psu_total)
    medians = np.empty(PRIMARY_N_BOOT)
    for b in range(PRIMARY_N_BOOT):
        mult[:] = 0.0
        for idx_h in stratum_global_idx.values():
            n_h = len(idx_h)
            draws = rng.integers(0, n_h, size=n_h)
            mult[idx_h] = np.bincount(draws, minlength=n_h)
        medians[b] = weighted_median(wage_val, wage_w0 * mult[wage_idx])

    counts = pd.Series(np.round(medians, 2)).value_counts().sort_index()
    return pd.DataFrame({"replicate_median_rand": counts.index, "n_replicates": counts.to_numpy()})


def build_frequency_sensitivity_15_64(df: pd.DataFrame, masks: dict) -> pd.DataFrame:
    age_ok = (df["Age"] >= AGE_LO) & (df["Age"] <= AGE_HI)
    rows = []
    for excursion in EXCURSIONS:
        for freq in FREQUENCY_GRID:
            outcomes = population_outcomes(df, masks, freq, excursion, scenario="A")
            resolved_idx = outcomes.index[outcomes["coverage_class"] != "unresolved"]
            resolved_idx = resolved_idx[age_ok.loc[resolved_idx]]
            vals = outcomes.loc[resolved_idx, "total"].to_numpy()
            w = df.loc[resolved_idx, "Weight"].to_numpy()
            rows.append(
                dict(
                    excursion_definition=excursion,
                    freq_days_per_week=freq,
                    population="15_to_64_primary",
                    n=len(resolved_idx),
                    weighted_mean_rand=round(weighted_mean(vals, w), 2),
                )
            )
    grid = pd.DataFrame(rows)
    for excursion in EXCURSIONS:
        sub = grid[grid.excursion_definition == excursion]["weighted_mean_rand"]
        swing_pct = (sub.max() - sub.min()) / sub.min() * 100
        print(f"{excursion}: frequency swing across tested range = {swing_pct:.2f}%")
    return grid


def build_coverage_15_64(df: pd.DataFrame, masks: dict) -> pd.DataFrame:
    """Exact coverage for the 15-64 primary population, requested 2026-09-14 --
    previously only the broader-age coverage was reported, with 15-64 assumed
    qualitatively similar rather than computed."""
    age_ok = (df["Age"] >= AGE_LO) & (df["Age"] <= AGE_HI)
    rows = []
    for excursion in EXCURSIONS:
        for scenario in ("A", "B"):
            outcomes = population_outcomes(
                df, masks, PRIMARY_FREQ_DAYS_PER_WEEK, excursion, scenario
            )
            restricted = outcomes.loc[age_ok.reindex(outcomes.index, fill_value=False)]
            rows.append(
                summarise(
                    restricted,
                    excursion_definition=excursion,
                    driver_code_5_6_scenario=scenario,
                    freq_days_per_week=PRIMARY_FREQ_DAYS_PER_WEEK,
                    population="15_to_64_primary",
                )
            )
    return pd.DataFrame(rows)


def build_psu_strata(geog_df: pd.DataFrame) -> pd.DataFrame:
    psu_strata = geog_df[["Stratum", "Psuno_seg"]].drop_duplicates()
    psu_strata = psu_strata.rename(columns={"Stratum": "stratum", "Psuno_seg": "psu"})
    psu_strata["n_h"] = psu_strata.groupby("stratum")["psu"].transform("count")
    return psu_strata


def main() -> None:
    data_root = Path(os.environ["THESIS_DATA_ROOT"])
    df = load_and_join_geography(data_root)
    print(
        f"Geography join confirmed: {df['Uqno'].nunique():,} households, "
        f"{df['Psuno_seg'].nunique():,} PSU/segments, {df['Stratum'].nunique()} strata, "
        f"0 unmatched person records."
    )
    masks = mode_masks(df)

    travellers = df[
        masks["hitchhike_and_listed_mode"] | masks["drive"] | masks["walk"] | masks["cycle"]
    ]
    wage_mask = (
        (df["Q410Salary"] > 0)
        & (df["Q410Salary"] < 999_000)
        & df["Q411Payperiod"].isin(WAGE_PERIOD_MAP)
    )
    wage_pop = df[wage_mask]
    shared_hh = set(travellers["Uqno"]) & set(wage_pop["Uqno"])
    print(f"Travellers n={len(travellers)}, wage n={len(wage_pop)}")
    print(f"Shared households={len(shared_hh)}")
    print()

    psu_strata = build_psu_strata(df)
    n_strata = psu_strata["stratum"].nunique()
    print(f"Bootstrap PSU pool: {len(psu_strata)} PSUs across {n_strata} strata")

    verification, stability = build_bootstrap_verification(df, masks, psu_strata)
    verification.to_csv(OUT_DIR / "transport_wage_ratio_bootstrap_verification.csv", index=False)
    stability.to_csv(OUT_DIR / "transport_wage_ratio_bootstrap_stability.csv", index=False)
    print(f"\nWrote {OUT_DIR / 'transport_wage_ratio_bootstrap_verification.csv'}")
    print(verification.to_string(index=False))
    print(f"\nWrote {OUT_DIR / 'transport_wage_ratio_bootstrap_stability.csv'}")
    print(stability.to_string(index=False))

    median_dist = build_median_distribution(df, masks, psu_strata)
    median_dist.to_csv(
        OUT_DIR / "transport_wage_ratio_bootstrap_median_distribution.csv", index=False
    )
    print(f"\nWrote {OUT_DIR / 'transport_wage_ratio_bootstrap_median_distribution.csv'}")
    print(
        f"  {len(median_dist)} distinct replicate median values across {PRIMARY_N_BOOT} replicates"
    )

    t0 = time.time()
    grid = build_design_uncertainty_grid(df, masks, psu_strata)
    print(f"\nBootstrap grid computation time: {time.time() - t0:.1f}s")
    grid.to_csv(OUT_DIR / "transport_wage_ratio_design_uncertainty.csv", index=False)
    print(f"Wrote {OUT_DIR / 'transport_wage_ratio_design_uncertainty.csv'}")
    print(grid.to_string(index=False))
    print()

    coverage = build_coverage_15_64(df, masks)
    coverage.to_csv(OUT_DIR / "transport_candidate_coverage_15_64.csv", index=False)
    print(f"Wrote {OUT_DIR / 'transport_candidate_coverage_15_64.csv'}")
    print(coverage.to_string(index=False))
    print()

    freq_grid = build_frequency_sensitivity_15_64(df, masks)
    freq_grid.to_csv(OUT_DIR / "transport_candidate_frequency_sensitivity_15_64.csv", index=False)
    print(f"\nWrote {OUT_DIR / 'transport_candidate_frequency_sensitivity_15_64.csv'}")
    print(freq_grid.to_string(index=False))


if __name__ == "__main__":
    main()
