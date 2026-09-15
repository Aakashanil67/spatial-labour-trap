"""ONE small, bounded, illustrative model run demonstrating scripts/observation_layer.py's
E/U/D mapping, duration clocks and transport estimator against REAL model output -- not a
calibration run, not a held-out validation campaign, not adopted anywhere. Deliberately
modest in scale (see MODEST_* constants below) so this stays a demonstration, not a
held-out simulation.

Uses configs/baseline.yaml with the approved fixed roles substituted
(approved_specification_2026-09-15.md): initial_search_capital=1.4962 (fixed, not estimated),
firm_radius=2.5 (fixed). search_cost_per_trip and firm_kappa are left at their PUBLISHED
starting values (results/published/calibration_result.json) -- NOT re-estimated under the new
bounds (Section 2 of the approved specification), since re-estimation is out of this batch's
scope. This run therefore illustrates the observation layer's MECHANICS on a real trace, not
a validated candidate parameter point.

Writes data/review_v2/observation_layer_demo_summary.csv -- review-only, not
data/moments.csv, not a canonical target.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd

from scripts.observation_layer import (
    classify_trace,
    cumulative_active_months,
    episode_clock,
    long_term_candidate_share,
    transport_person_window_estimate,
)
from src.agents import WAGE
from src.config import Config
from src.model import CityModel
from src.moments import DAYS_PER_MONTH

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = REPO_ROOT / "data" / "review_v2" / "observation_layer_demo_summary.csv"

# Deliberately modest -- an illustration, not a calibration-representative or held-out run.
MODEST_N_AGENTS = 100
MODEST_N_STEPS = 1500
MODEST_SEED = 1  # CALIBRATION_SEEDS[0] -- reused, not a fresh validation seed; this is not a
# validation run and does not need a disjoint block.
MEASUREMENT_WINDOW = range(MODEST_N_STEPS - 300 + 1, MODEST_N_STEPS + 1)  # last 300 steps


def build_config() -> Config:
    base = Config.from_yaml(REPO_ROOT / "configs" / "baseline.yaml")
    return replace(
        base,
        n_agents=MODEST_N_AGENTS,
        n_steps=MODEST_N_STEPS,
        seed=MODEST_SEED,
        initial_search_capital=1.4962,  # Section 1: fixed initialisation setting
        firm_radius=2.5,  # Section 1: fixed, per the pre-calibration recommendation
        search_cost_per_trip=0.002514642203001423,  # published starting point, unchanged
        firm_kappa=0.22393789239458572,  # published starting point, unchanged
        # n_firms/n_vacancies scaled down from baseline's 5/15 (at n_agents=500) to preserve
        # the same firms-per-agent and vacancies-per-agent ratios at this demo's smaller
        # population -- an UNSCALED firm/vacancy count at 1/5 the population made hiring
        # trivially easy and produced zero long-term-unemployment observations under every
        # clock definition (including the existing canonical months_jobless measure, so this
        # was a demo-scale artefact, not a bug in the new code), which defeated the point of
        # illustrating the clock definitions' differences.
        n_firms=1,
        n_vacancies=3,
        trace_agent_ids=tuple(range(MODEST_N_AGENTS + 10)),  # over-covers actual unique_ids
    )


def main() -> None:
    cfg = build_config()
    model = CityModel(cfg)
    model.run()
    trace = pd.DataFrame(model.trace_history)
    trace = trace[trace["step"].isin(MEASUREMENT_WINDOW)]
    print(f"Trace rows in measurement window: {len(trace)} ({trace['unique_id'].nunique()} agents)")

    # --- Duration-clock candidates -----------------------------------------------------
    all_durations: dict[str, list] = {"k0": [], "k1": [], "k3": [], "kinf": [], "cumulative": []}
    all_categories: list[str] = []
    for _uid, g in trace.sort_values("step").groupby("unique_id"):
        cats = classify_trace(g.to_dict("records"))
        all_categories.extend(cats)
        all_durations["k0"].extend(episode_clock(cats, k=0))
        all_durations["k1"].extend(episode_clock(cats, k=1))
        all_durations["k3"].extend(episode_clock(cats, k=3))
        all_durations["kinf"].extend(episode_clock(cats, k=10**9))
        all_durations["cumulative"].extend(cumulative_active_months(cats))

    summary_rows = []
    for label, durations in all_durations.items():
        result = long_term_candidate_share(durations, all_categories, threshold_months=12)
        summary_rows.append(dict(quantity=f"long_term_share_candidate_{label}", **result))
        print(f"long_term_share candidate ({label}): {result}")

    # Also report the model's CURRENT canonical long_term_share (months_jobless-based, D11
    # pre-matching stock convention) over the same window, from self.history, for comparison
    # -- NOT recomputed here, read directly from the already-collected aggregate series.
    history = pd.DataFrame(model.history)
    hist_window = history[history["step"].isin(MEASUREMENT_WINDOW)]
    canonical_lts = (hist_window["n_long_term"] / hist_window["u"].replace(0, pd.NA)).mean()
    summary_rows.append(
        dict(
            quantity="long_term_share_canonical_months_jobless",
            share=canonical_lts,
            n_stock=None,
            n_long_term=None,
        )
    )
    print(f"long_term_share canonical (months_jobless, D11 stock convention): {canonical_lts}")

    # --- Transport estimator candidates -------------------------------------------------
    daily_wage = WAGE / DAYS_PER_MONTH
    traveller_records = []
    for row in trace.itertuples():
        if row.trips_this_step >= 1:
            cost_per_trip = cfg.search_cost_per_trip + cfg.transport_cost_rate * row.distance_to_cbd
            traveller_records.append(
                dict(
                    step=row.step,
                    agent_id=row.unique_id,
                    spend=row.trips_this_step * cost_per_trip,
                    trips=row.trips_this_step,
                )
            )
    window_steps = list(MEASUREMENT_WINDOW)
    equal_person = transport_person_window_estimate(traveller_records, window_steps, "equal_person")
    trip_weighted = transport_person_window_estimate(
        traveller_records, window_steps, "trip_weighted"
    )
    for label, result in [
        ("equal_person_PRIMARY", equal_person),
        ("trip_weighted_SENSITIVITY", trip_weighted),
    ]:
        ratio = result["estimate"] / daily_wage if result["estimate"] is not None else None
        summary_rows.append(
            dict(
                quantity=f"transport_person_window_{label}",
                share=ratio,
                n_stock=result["n_months_used"],
                n_long_term=result["n_months_empty"],
            )
        )
        print(
            f"transport_budget_share candidate ({label}): cost={result['estimate']}, ratio={ratio}"
        )

    # Current canonical transport_budget_share, same window, from self.history directly.
    total_spend = hist_window["transport_spend"].sum()
    total_trips = hist_window["total_trips"].sum()
    canonical_transport = (total_spend / (total_trips * daily_wage)) if total_trips > 0 else None
    summary_rows.append(
        dict(
            quantity="transport_budget_share_canonical_trip_mean",
            share=canonical_transport,
            n_stock=None,
            n_long_term=None,
        )
    )
    print(f"transport_budget_share canonical (pooled trip-mean): {canonical_transport}")

    pd.DataFrame(summary_rows).to_csv(OUT_PATH, index=False)
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
