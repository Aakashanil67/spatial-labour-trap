"""P2.3: decision-ready candidate transport-cost estimates, review output only.

Builds candidate person-level transport-cost estimates using ALL administered legs
(not leg-1 only), the NHTS person `Weight`, and every disclosed conversion assumption
this review has flagged as open -- so a human decision (Aakash's, not this script's)
has concrete numbers to choose between rather than one silently adopted figure.
Nothing here touches `transport_budget_share` in configs/baseline.yaml or
data/moments.csv.

**Primary approach vs. diagnostic, stated explicitly (2026-09-14):**
  - WEIGHTING: the NHTS person `Weight` is the PRIMARY approach; unweighted figures
    are reported as a diagnostic only, not as an equally-valid alternative.
  - EXCURSION DEFINITION: "round_trip" is the PRIMARY unit, consistent with the
    model's own existing interpretation of its flat transport-cost anchor (Banerjee
    and Sequeira's R12.50 figure in configs/baseline.yaml is explicitly a RETURN
    fare, not a one-direction fare -- see src/calibrate.py). "one_direction" is
    retained as an explicit reporting comparison, not as a co-equal candidate.

**Frequency is a single physical schedule, shared consistently across excursion
definitions and across payment periods (CORRECTED 2026-09-14).** The previous version
of this script converted a weekly/monthly fare using a divisor that did not depend on
the excursion definition at all, so a weekly bus fare produced the SAME per-trip cost
under "one_direction" and "round_trip", unlike the per-single/per-return fields, which
correctly differ by a factor of 2 between the two bases. The fix: `freq_days_per_week`
is a single number -- how many search DAYS (each day = one round trip = two
one-direction legs) a job seeker travels per week -- and every conversion derives from
it. A weekly fare divided by `freq_days_per_week` gives the ROUND-TRIP cost of one
search day directly; a one-direction cost is always exactly half of the round-trip
cost for the same leg, by construction, which is the consistency property this module
tests for (`tests/test_transport_candidate_estimates.py`).

**Coverage is split into directly-supported and frequency-dependent, both unweighted
and survey-weighted (2026-09-14).** A journey/driver resolved using only per-single or
per-return legs (plus zero-fare legs) needs no frequency assumption at all --
"directly supported". A journey/driver that needs a per-week or per-month leg to
resolve requires the frequency assumption -- "requires frequency assumption". Both are
reported, plus the residual "unresolved" share (ambiguous/DNK/internal-inconsistency/
per-year legs, which no candidate here converts).

**The frequency sensitivity check now spans a bounded range including much less
frequent search (2026-09-14), not just 5-vs-7 days/week.** `FREQUENCY_GRID` covers 1,
2, 3, 5 and 7 search days/week; the 5-vs-7 comparison in the previous version is not
generalised into a claim about "the" sensitivity of this estimate to frequency
choice -- the full grid is reported instead.

Usage:
    python -m scripts.build_transport_candidate_estimates

Requires THESIS_DATA_ROOT set. Writes:
    data/review_v2/transport_candidate_estimates.csv
    data/review_v2/transport_candidate_frequency_sensitivity.csv
    data/review_v2/transport_wage_ratio_candidates.csv
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
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

WEEKS_PER_MONTH = 4.345  # South Africa's conventional figure (matches notebook 02's own use)
PRIMARY_FREQ_DAYS_PER_WEEK = 5  # BORROWED from the wage side's 21.7-day/month convention
# (21.7 / 4.345 = 5) -- explicitly flagged as NOT VERIFIED to fit a job-search trip
# frequency. Varied across the full grid below rather than assumed.
FREQUENCY_GRID = [1, 2, 3, 5, 7]
EXCURSIONS = ("round_trip", "one_direction")  # round_trip listed first: PRIMARY


def leg_contribution(
    pay: int, cost: float, freq_days_per_week: float, excursion: str
) -> float | None:
    """One search-day's transport cost in the given excursion basis. Always exactly
    half for 'one_direction' vs. 'round_trip' on the same (pay, cost, freq) -- derived
    from a single one-direction value, not two independently-computed bases, so the
    2x relationship holds by construction for every period code, not just 1/2.
    """
    if pay == 1:  # per single trip: already a one-direction cost
        one_direction = cost
    elif pay == 2:  # per return trip: a return trip is two one-direction legs
        one_direction = cost / 2
    elif pay == 3:  # per week: freq_days_per_week round trips = 2*freq one-direction legs
        one_direction = cost / (freq_days_per_week * 2)
    elif pay == 4:  # per month: freq_days_per_week*WEEKS_PER_MONTH round trips
        month_days = freq_days_per_week * WEEKS_PER_MONTH
        one_direction = cost / (month_days * 2)
    else:
        return None  # per_year (n=1) or any other code: not converted under any candidate
    return one_direction if excursion == "one_direction" else one_direction * 2


def journey_outcome(row: pd.Series, freq: float, excursion: str) -> tuple[float | None, str]:
    total = 0.0
    needs_frequency = False
    for spec in LEG_SPECS:
        cls = classify_leg(row, spec)
        if cls == "not_administered" or cls in ZERO_CLASSES:
            continue
        if cls != "positive_numeric":
            return None, "unresolved"
        pay = row[spec["pay"]]
        contribution = leg_contribution(pay, row[spec["cost"]], freq, excursion)
        if contribution is None:
            return None, "unresolved"
        if pay in (3, 4):
            needs_frequency = True
        total += contribution
    return total, ("requires_frequency" if needs_frequency else "directly_supported")


def driver_outcome(
    row: pd.Series, freq: float, excursion: str, scenario: str
) -> tuple[float | None, str]:
    pay, cost = row["Q433bPay"], row["Q434bCost"]
    if pay in (1, 2, 3, 4):
        if pd.isna(cost) or cost in (DRIVER_COST_NA, DRIVER_COST_UNSPEC):
            return None, "unresolved"
        contribution = leg_contribution(pay, cost, freq, excursion)
        needs_frequency = pay in (3, 4)
        return contribution, ("requires_frequency" if needs_frequency else "directly_supported")
    if pay == 5:
        return (0.0, "directly_supported") if scenario == "B" else (None, "unresolved")
    return None, "unresolved"  # code 6, or anything else: nonresponse under both scenarios


def population_outcomes(
    df: pd.DataFrame, masks: dict, freq: float, excursion: str, scenario: str
) -> pd.DataFrame:
    hl = df[masks["hitchhike_and_listed_mode"]].apply(
        lambda r: journey_outcome(r, freq, excursion), axis=1, result_type="expand"
    )
    drv = df[masks["drive"]].apply(
        lambda r: driver_outcome(r, freq, excursion, scenario), axis=1, result_type="expand"
    )
    hl.columns = drv.columns = ["total", "coverage_class"]
    walk = pd.DataFrame(
        {"total": 0.0, "coverage_class": "directly_supported"}, index=df[masks["walk"]].index
    )
    cyc = pd.DataFrame(
        {"total": 0.0, "coverage_class": "directly_supported"}, index=df[masks["cycle"]].index
    )
    out = pd.concat([walk, cyc, drv, hl])
    out["weight"] = df.loc[out.index, "Weight"]
    return out


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cw = np.cumsum(w)
    return float(v[cw >= cw[-1] / 2][0])


def summarise(outcomes: pd.DataFrame, **labels) -> dict:
    n_total = len(outcomes)
    is_direct = outcomes["coverage_class"] == "directly_supported"
    is_freq = outcomes["coverage_class"] == "requires_frequency"
    resolved = is_direct | is_freq
    w = outcomes["weight"]
    w_total = w.sum()

    resolved_totals = outcomes.loc[resolved, "total"].to_numpy()
    resolved_weights = w.loc[resolved].to_numpy()

    return dict(
        **labels,
        coverage_n_directly_supported=int(is_direct.sum()),
        coverage_n_requires_frequency=int(is_freq.sum()),
        coverage_n_unresolved=int(n_total - resolved.sum()),
        coverage_n_total=n_total,
        unweighted_coverage_share_direct=round(is_direct.sum() / n_total, 4),
        unweighted_coverage_share_total=round(resolved.sum() / n_total, 4),
        weighted_coverage_share_direct=round(float(w.loc[is_direct].sum() / w_total), 4),
        weighted_coverage_share_total=round(float(w.loc[resolved].sum() / w_total), 4),
        weighted_mean_rand=round(float(np.average(resolved_totals, weights=resolved_weights)), 2),
        weighted_median_rand=round(weighted_median(resolved_totals, resolved_weights), 2),
        unweighted_mean_rand_diagnostic=round(float(resolved_totals.mean()), 2),
    )


def build_primary_grid(df: pd.DataFrame, masks: dict) -> pd.DataFrame:
    rows = []
    for excursion in EXCURSIONS:
        for scenario in ("A", "B"):
            outcomes = population_outcomes(
                df, masks, PRIMARY_FREQ_DAYS_PER_WEEK, excursion, scenario
            )
            rows.append(
                summarise(
                    outcomes,
                    excursion_definition=excursion,
                    driver_code_5_6_scenario=scenario,
                    freq_days_per_week=PRIMARY_FREQ_DAYS_PER_WEEK,
                )
            )
    return pd.DataFrame(rows)


def build_frequency_sensitivity(df: pd.DataFrame, masks: dict) -> pd.DataFrame:
    rows = []
    for excursion in EXCURSIONS:
        for freq in FREQUENCY_GRID:
            outcomes = population_outcomes(df, masks, freq, excursion, scenario="A")
            rows.append(
                summarise(
                    outcomes,
                    excursion_definition=excursion,
                    driver_code_5_6_scenario="A",
                    freq_days_per_week=freq,
                )
            )
    return pd.DataFrame(rows)


def check_round_trip_is_twice_one_direction(df: pd.DataFrame, masks: dict) -> None:
    """Consistency check requested 2026-09-14: round-trip totals must equal exactly
    twice the one-direction totals for the same population, at the same frequency and
    driver scenario, for every resolved record -- not just periods 1/2.
    """
    one = population_outcomes(df, masks, PRIMARY_FREQ_DAYS_PER_WEEK, "one_direction", "A")
    two = population_outcomes(df, masks, PRIMARY_FREQ_DAYS_PER_WEEK, "round_trip", "A")
    resolved = one["coverage_class"] != "unresolved"
    ratio = two.loc[resolved, "total"] / one.loc[resolved, "total"].replace(0, np.nan)
    ratio = ratio.dropna()  # zero-fare records divide 0/0 -- both sides are 0, trivially consistent
    assert np.allclose(ratio, 2.0), "round_trip is not exactly 2x one_direction for some records"
    zero_mismatch = ((one.loc[resolved, "total"] == 0) != (two.loc[resolved, "total"] == 0)).sum()
    assert zero_mismatch == 0, "zero-fare records disagree between excursion bases"
    print(
        f"Consistency check passed: round_trip == 2 * one_direction for all {resolved.sum()} "
        f"resolved records (frequency={PRIMARY_FREQ_DAYS_PER_WEEK}/week, scenario=A)."
    )


def compute_wage_side(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Reproduces notebook 02's wage-side methodology exactly (median monthly wage,
    person-weighted, over respondents with a usable Q410Salary + Q411Payperiod)."""
    period_map = {1: 4.345, 2: 1.0, 3: 1 / 12}  # 1=Per week, 2=Per month, 3=Annually
    wage_mask = (
        (df["Q410Salary"] > 0) & (df["Q410Salary"] < 999_000) & df["Q411Payperiod"].isin(period_map)
    )
    period_factor = df["Q411Payperiod"].map(period_map)
    monthly_wage = (df["Q410Salary"] * period_factor)[wage_mask].to_numpy()
    weights = df.loc[wage_mask, "Weight"].to_numpy()
    return monthly_wage, weights


def bootstrap_ratio(
    cost_vals: np.ndarray,
    cost_weights: np.ndarray,
    wage_vals: np.ndarray,
    wage_weights: np.ndarray,
    n_boot: int = 2000,
    seed: int = 42,
) -> dict:
    """Weighted bootstrap matching notebook 02's own approach exactly (resample with
    replacement, probability proportional to person weight, cost and wage populations
    resampled independently each draw)."""
    rng = np.random.default_rng(seed)
    cost_p = cost_weights / cost_weights.sum()
    wage_p = wage_weights / wage_weights.sum()
    point_cost = np.average(cost_vals, weights=cost_weights)
    point_wage_median = weighted_median(wage_vals, wage_weights)
    point_daily_wage = point_wage_median / 21.7
    point_ratio = point_cost / point_daily_wage

    boot = np.empty(n_boot)
    for i in range(n_boot):
        ci = rng.choice(len(cost_vals), size=len(cost_vals), replace=True, p=cost_p)
        wi = rng.choice(len(wage_vals), size=len(wage_vals), replace=True, p=wage_p)
        boot_cost = cost_vals[ci].mean()
        boot_wage = np.median(wage_vals[wi]) / 21.7
        boot[i] = boot_cost / boot_wage

    return dict(
        point_estimate=round(float(point_ratio), 4),
        weighted_mean_cost_rand=round(float(point_cost), 2),
        weighted_median_monthly_wage_rand=round(float(point_wage_median), 2),
        daily_wage_rand=round(float(point_daily_wage), 2),
        bootstrap_se=round(float(boot.std(ddof=1)), 4),
        ci_95_lo=round(float(np.percentile(boot, 2.5)), 4),
        ci_95_hi=round(float(np.percentile(boot, 97.5)), 4),
        n_boot=n_boot,
    )


def build_wage_ratio_candidates(df: pd.DataFrame, masks: dict) -> pd.DataFrame:
    wage_vals, wage_weights = compute_wage_side(df)
    rows = []
    for scenario in ("A", "B"):
        outcomes = population_outcomes(
            df, masks, PRIMARY_FREQ_DAYS_PER_WEEK, "round_trip", scenario
        )
        resolved = outcomes["coverage_class"] != "unresolved"
        cost_vals = outcomes.loc[resolved, "total"].to_numpy()
        cost_weights = outcomes.loc[resolved, "weight"].to_numpy()
        result = bootstrap_ratio(cost_vals, cost_weights, wage_vals, wage_weights)
        result.update(
            driver_code_5_6_scenario=scenario,
            excursion_definition="round_trip",
            freq_days_per_week=PRIMARY_FREQ_DAYS_PER_WEEK,
            transport_sample=(
                "job-search travellers (walk/cycle/drive/hitchhike/listed-mode), all "
                "administered legs, unresolved (ambiguous/DNK/internal-inconsistency/"
                "per_year) journeys excluded -- see coverage_share above"
            ),
            wage_sample=f"n={len(wage_vals)} NHTS respondents with valid Q410Salary + Payperiod",
        )
        rows.append(result)
    return pd.DataFrame(rows)


def main() -> None:
    data_root = Path(os.environ["THESIS_DATA_ROOT"])
    df = load_source(data_root)
    masks = mode_masks(df)

    check_round_trip_is_twice_one_direction(df, masks)
    print()

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

    wage_ratios = build_wage_ratio_candidates(df, masks)
    wage_ratios.to_csv(OUT_DIR / "transport_wage_ratio_candidates.csv", index=False)
    print(f"Wrote {OUT_DIR / 'transport_wage_ratio_candidates.csv'}")
    print(wage_ratios.to_string(index=False))
    print()
    print(
        "None of these figures are adopted as transport_budget_share. Weighted figures are "
        "primary; unweighted means are a diagnostic only. round_trip is the primary excursion "
        "unit (matches the model's existing return-fare interpretation); one_direction is a "
        "reporting comparison."
    )


if __name__ == "__main__":
    main()
