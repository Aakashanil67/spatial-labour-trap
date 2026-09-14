"""P2.3: design-based sampling uncertainty and the 15-64 primary population, review only.

Extends the candidate transport-to-wage ratio (scripts/build_transport_candidate_estimates.py)
with two corrections requested 2026-09-14:

1. **Design-based sampling uncertainty, not independent resampling.** The previous
   bootstrap resampled the cost (traveller) and wage populations INDEPENDENTLY, which
   is not an adequate default: the two samples share 1,113 households (verified live
   below), so a shock to a shared household (e.g. it falls into the same dropped PSU)
   should move both sides of the ratio together, not independently. This script joins
   the NHTS 2020 GEOGRAPHY file (`nhts-2020-geog.dta`, fields `Uqno`, `Psuno_seg`,
   `Stratum`) to the person file on `Uqno` -- confirmed live: a unique household join,
   0 unmatched person records, 6,039 PSU/segment identifiers, 90 strata (all exactly
   matching an independent source check) -- and builds a STRATIFIED DELETE-1 JACKKNIFE
   (JK1) over PSU/segments: each replicate drops one PSU, reweights the surviving PSUs
   in that PSU's stratum by n_h/(n_h-1), and recomputes the weighted cost mean AND the
   weighted wage median TOGETHER from that one replicate's weights, so any shared
   household is dropped from (or kept in) both sides simultaneously. The jackknife
   variance formula (Wolter 2007) is applied to the resulting pseudo-values of the
   ratio. No official NHTS replicate weights exist in the public-use file (confirmed:
   no jk/rep/brr/fay/bootstrap/pweight/fpc-named column in either file's metadata), so
   this jackknife is CONSTRUCTED here, not looked up -- an approximation to whichever
   variance-estimation design StatsSA's own internal files may use. A second
   approximation: no finite-population correction is applied (the standard assumption
   when PSUs are a small fraction of the sampling frame, which is not independently
   verified here since the overall sampling fraction is not published in the files
   available).

2. **Ages 15-64 as the PROPOSED primary population for both numerator and wage
   benchmark**, with the broader (unrestricted) age range retained as a sensitivity
   comparison rather than silently dropped. Verified live: 19 of 4,655 travellers and
   364 of 20,867 wage observations fall outside 15-64.

Round-trip excursion, person weighting, and the primary frequency assumption (5
search days/week) are held FIXED at their already-proposed primary settings from the
prior round -- this script only extends the uncertainty and population dimensions,
it does not reopen those.

Sampling uncertainty (this script) is kept explicitly SEPARATE from driver-code,
frequency, and missing-journey (coverage) sensitivity
(scripts/build_transport_candidate_estimates.py) -- they are different kinds of
uncertainty and are never combined into one interval.

Usage:
    python -m scripts.build_transport_wage_ratio_uncertainty

Requires THESIS_DATA_ROOT set. Writes:
    data/review_v2/transport_wage_ratio_design_uncertainty.csv (both age populations,
        both driver scenarios -- age sensitivity is the `population` column, not a
        separate file)
    data/review_v2/transport_candidate_frequency_sensitivity_15_64.csv
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
)
from scripts.build_transport_review_tables import load_source, mode_masks

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "data" / "review_v2"

WAGE_PERIOD_MAP = {1: 4.345, 2: 1.0, 3: 1 / 12}  # 1=Per week, 2=Per month, 3=Annually
AGE_LO, AGE_HI = 15, 64


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


def jackknife_ratio(cost_df: pd.DataFrame, wage_df: pd.DataFrame, psu_strata: pd.DataFrame) -> dict:
    cost_mean_full = weighted_mean(cost_df["value"].to_numpy(), cost_df["weight"].to_numpy())
    wage_median_full = weighted_median(wage_df["value"].to_numpy(), wage_df["weight"].to_numpy())
    daily_wage_full = wage_median_full / 21.7
    ratio_full = cost_mean_full / daily_wage_full

    cost_psu, cost_stratum = cost_df["psu"].to_numpy(), cost_df["stratum"].to_numpy()
    cost_val, cost_w0 = cost_df["value"].to_numpy(), cost_df["weight"].to_numpy()
    wage_psu, wage_stratum = wage_df["psu"].to_numpy(), wage_df["stratum"].to_numpy()
    wage_val, wage_w0 = wage_df["value"].to_numpy(), wage_df["weight"].to_numpy()

    pseudo = np.empty(len(psu_strata))
    strata_arr = psu_strata["stratum"].to_numpy()
    for i, (h, psu, n_h) in enumerate(
        zip(psu_strata["stratum"], psu_strata["psu"], psu_strata["n_h"], strict=True)
    ):
        factor = n_h / (n_h - 1)

        in_h_c = cost_stratum == h
        w_c = cost_w0.copy()
        w_c[in_h_c] *= factor
        w_c[in_h_c & (cost_psu == psu)] = 0.0
        cm = weighted_mean(cost_val, w_c)

        in_h_w = wage_stratum == h
        w_w = wage_w0.copy()
        w_w[in_h_w] *= factor
        w_w[in_h_w & (wage_psu == psu)] = 0.0
        wm = weighted_median(wage_val, w_w)

        pseudo[i] = cm / (wm / 21.7)

    variance = 0.0
    for h in np.unique(strata_arr):
        idx = strata_arr == h
        n_h = int(idx.sum())
        variance += (n_h - 1) / n_h * np.sum((pseudo[idx] - ratio_full) ** 2)
    se = float(np.sqrt(variance))

    return dict(
        point_estimate=round(ratio_full, 4),
        weighted_mean_cost_rand=round(cost_mean_full, 2),
        weighted_median_monthly_wage_rand=round(wage_median_full, 2),
        daily_wage_rand=round(daily_wage_full, 2),
        jackknife_se=round(se, 4),
        ci_95_lo=round(ratio_full - 1.96 * se, 4),
        ci_95_hi=round(ratio_full + 1.96 * se, 4),
        n_replicates=len(psu_strata),
        cost_n=len(cost_df),
        wage_n=len(wage_df),
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
            result = jackknife_ratio(cost_df, wage_df, psu_strata)
            result.update(
                population=pop_label,
                driver_code_5_6_scenario=scenario,
                excursion_definition="round_trip",
                freq_days_per_week=PRIMARY_FREQ_DAYS_PER_WEEK,
            )
            rows.append(result)
    return pd.DataFrame(rows)


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
        # Swing expressed relative to the LOWER (daily-search, freq=7) end of the
        # range, i.e. "how much higher is the infrequent-search estimate than the
        # frequent-search one" -- not relative to the higher end.
        swing_pct = (sub.max() - sub.min()) / sub.min() * 100
        print(f"{excursion}: frequency swing across tested range = {swing_pct:.2f}%")
    return grid


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
    print(f"Travellers n={len(travellers)}, households={travellers['Uqno'].nunique()}")
    wage_mask = (
        (df["Q410Salary"] > 0)
        & (df["Q410Salary"] < 999_000)
        & df["Q411Payperiod"].isin(WAGE_PERIOD_MAP)
    )
    wage_pop = df[wage_mask]
    print(f"Wage sample n={len(wage_pop)}, households={wage_pop['Uqno'].nunique()}")
    shared_hh = set(travellers["Uqno"]) & set(wage_pop["Uqno"])
    print(f"Shared households: {len(shared_hh)}")
    print()

    psu_strata = build_psu_strata(df)
    n_strata = psu_strata["stratum"].nunique()
    print(f"Jackknife replicates: {len(psu_strata)} PSUs across {n_strata} strata")
    t0 = time.time()
    grid = build_design_uncertainty_grid(df, masks, psu_strata)
    print(f"Jackknife computation time: {time.time() - t0:.1f}s")
    grid.to_csv(OUT_DIR / "transport_wage_ratio_design_uncertainty.csv", index=False)
    print(f"\nWrote {OUT_DIR / 'transport_wage_ratio_design_uncertainty.csv'}")
    print(grid.to_string(index=False))
    print()

    freq_grid = build_frequency_sensitivity_15_64(df, masks)
    freq_grid.to_csv(OUT_DIR / "transport_candidate_frequency_sensitivity_15_64.csv", index=False)
    print(f"\nWrote {OUT_DIR / 'transport_candidate_frequency_sensitivity_15_64.csv'}")
    print(freq_grid.to_string(index=False))


if __name__ == "__main__":
    main()
