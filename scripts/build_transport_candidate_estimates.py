"""P2.3: decision-ready candidate transport-cost estimates, review output only.

Builds a small, explicitly labelled GRID of candidate person-level transport-cost
estimates using ALL administered legs (not leg-1 only), the NHTS person `Weight`, and
every disclosed conversion assumption this review has flagged as open -- so a human
decision (Aakash's, not this script's) has concrete numbers to choose between rather
than one silently adopted figure. Nothing here touches `transport_budget_share` in
configs/baseline.yaml or data/moments.csv.

What varies across the grid, and what does NOT:
  - excursion definition (varies): "one_direction" treats a per-single-trip cost as
    already the target unit and halves a per-return-trip cost; "round_trip" does the
    opposite (doubles per-single-trip, takes per-return-trip as-is). Neither is
    adopted -- both are reported side by side.
  - driver Q433bPay codes 5/6 (varies): Scenario A (labels as exported -- both codes
    are genuine nonresponse, excluded) vs Scenario B (instrument as printed -- code 5
    is a legitimate zero fare, code 6 stays nonresponse). See transport_definition.md.
  - weighting (varies): the NHTS person `Weight` vs unweighted, reported side by side.
  - week/month trip-frequency assumption (held fixed in the primary grid at 5 trips/
    week and 21.7 days/month -- the wage side's own convention, explicitly flagged as
    BORROWED AND NOT VERIFIED to fit a job-search trip frequency -- then varied
    separately in a small sensitivity table against an alternative, 7 trips/week and
    30 days/month, so the choice stays visible rather than silently fixed).

A journey's (or driver's) total is included in a given candidate only if EVERY
administered/resolved leg converts under that candidate's assumptions; a journey with
any ambiguous, internal-inconsistency, DNK, or per-year (n=1, too sparse to convert
reliably) leg is excluded from that candidate's average, which is why "coverage"
(the share of the 4,655-person population actually contributing to each mean) is
reported alongside every candidate rather than assumed to be 100%.

Usage:
    python -m scripts.build_transport_candidate_estimates

Requires THESIS_DATA_ROOT set. Writes:
    data/review_v2/transport_candidate_estimates.csv
    data/review_v2/transport_candidate_frequency_sensitivity.csv
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from scripts.build_transport_review_tables import (
    DRIVER_COST_NA,
    DRIVER_COST_UNSPEC,
    LEG_SPECS,
    ZERO_CLASSES,
    classify_leg,
    load_source,
    mode_masks,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "data" / "review_v2"

EXCURSION_BASES = {
    "one_direction": dict(single_mult=1, return_divisor=2),
    "round_trip": dict(single_mult=2, return_divisor=1),
}
FREQ_PRIMARY = dict(label="5_trips_per_week_21.7_days_per_month", week_trips=5, month_days=21.7)
FREQ_ALT = dict(label="7_trips_per_week_30_days_per_month", week_trips=7, month_days=30)


def leg_contribution(pay: int, cost: float, basis: dict, freq: dict) -> float | None:
    if pay == 1:
        return cost * basis["single_mult"]
    if pay == 2:
        return cost / basis["return_divisor"]
    if pay == 3:
        return cost / freq["week_trips"]
    if pay == 4:
        return cost / freq["month_days"]
    return None  # per_year (n=1) or any other code: not converted under this candidate


def journey_total(row: pd.Series, basis: dict, freq: dict) -> float | None:
    total = 0.0
    for spec in LEG_SPECS:
        cls = classify_leg(row, spec)
        if cls == "not_administered" or cls in ZERO_CLASSES:
            continue
        if cls != "positive_numeric":
            return None  # ambiguous / internal-inconsistency / DNK leg: unresolved
        contribution = leg_contribution(row[spec["pay"]], row[spec["cost"]], basis, freq)
        if contribution is None:
            return None
        total += contribution
    return total


def driver_total(row: pd.Series, basis: dict, freq: dict, scenario: str) -> float | None:
    pay, cost = row["Q433bPay"], row["Q434bCost"]
    if pay in (1, 2, 3, 4):
        if pd.isna(cost) or cost in (DRIVER_COST_NA, DRIVER_COST_UNSPEC):
            return None
        return leg_contribution(pay, cost, basis, freq)
    if pay == 5:
        return 0.0 if scenario == "B" else None  # Scenario B: code 5 = legitimate zero
    return None  # code 6, or anything else: nonresponse under both scenarios


def population_totals(
    df: pd.DataFrame, masks: dict, basis: dict, freq: dict, scenario: str
) -> pd.Series:
    hl_totals = df[masks["hitchhike_and_listed_mode"]].apply(
        lambda r: journey_total(r, basis, freq), axis=1
    )
    drv_totals = df[masks["drive"]].apply(lambda r: driver_total(r, basis, freq, scenario), axis=1)
    walk_totals = pd.Series(0.0, index=df[masks["walk"]].index)
    cyc_totals = pd.Series(0.0, index=df[masks["cycle"]].index)
    return pd.concat([walk_totals, cyc_totals, drv_totals, hl_totals])


def summarise(df: pd.DataFrame, totals: pd.Series, **labels) -> dict:
    resolved = totals.notna()
    weights = df.loc[totals.index, "Weight"]
    n_total = len(totals)
    n_resolved = int(resolved.sum())
    weighted_mean = (totals[resolved] * weights[resolved]).sum() / weights[resolved].sum()
    return dict(
        **labels,
        coverage_n=n_resolved,
        coverage_total=n_total,
        coverage_share=round(n_resolved / n_total, 4),
        unweighted_mean_rand=round(float(totals[resolved].mean()), 2),
        weighted_mean_rand=round(float(weighted_mean), 2),
        weighted_median_rand=round(float(_weighted_median(totals[resolved], weights[resolved])), 2),
    )


def _weighted_median(values: pd.Series, weights: pd.Series) -> float:
    order = values.sort_values().index
    v, w = values.loc[order], weights.loc[order]
    cum = w.cumsum()
    cutoff = w.sum() / 2
    return float(v[cum >= cutoff].iloc[0])


def build_primary_grid(df: pd.DataFrame, masks: dict) -> pd.DataFrame:
    rows = []
    for basis_name, basis in EXCURSION_BASES.items():
        for scenario in ("A", "B"):
            totals = population_totals(df, masks, basis, FREQ_PRIMARY, scenario)
            rows.append(
                summarise(
                    df,
                    totals,
                    excursion_definition=basis_name,
                    driver_code_5_6_scenario=scenario,
                    frequency_assumption=FREQ_PRIMARY["label"],
                )
            )
    return pd.DataFrame(rows)


def build_frequency_sensitivity(df: pd.DataFrame, masks: dict) -> pd.DataFrame:
    rows = []
    for basis_name, basis in EXCURSION_BASES.items():
        for freq in (FREQ_PRIMARY, FREQ_ALT):
            totals = population_totals(df, masks, basis, freq, scenario="A")
            rows.append(
                summarise(
                    df,
                    totals,
                    excursion_definition=basis_name,
                    driver_code_5_6_scenario="A",
                    frequency_assumption=freq["label"],
                )
            )
    return pd.DataFrame(rows)


def main() -> None:
    data_root = Path(os.environ["THESIS_DATA_ROOT"])
    df = load_source(data_root)
    masks = mode_masks(df)

    grid = build_primary_grid(df, masks)
    grid.to_csv(OUT_DIR / "transport_candidate_estimates.csv", index=False)
    print(f"Wrote {OUT_DIR / 'transport_candidate_estimates.csv'}")
    print(grid.to_string(index=False))
    print()

    sensitivity = build_frequency_sensitivity(df, masks)
    sensitivity.to_csv(OUT_DIR / "transport_candidate_frequency_sensitivity.csv", index=False)
    print(f"Wrote {OUT_DIR / 'transport_candidate_frequency_sensitivity.csv'}")
    print(sensitivity.to_string(index=False))
    print()
    print(
        "None of these figures are adopted as transport_budget_share. Coverage is under "
        "100% because ambiguous, DNK, internal-inconsistency, and per_year (n=1) legs are "
        "excluded from every candidate rather than assigned a value by assumption."
    )


if __name__ == "__main__":
    main()
