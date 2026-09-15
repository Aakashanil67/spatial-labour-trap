"""Bounded DEVELOPMENT feasibility screen (Aakash, 2026-09-15, following
`REVIEW_AND_NEXT_BATCH.md`'s recommended milestone). NOT a held-out validation campaign, NOT
a calibration search -- uses already-used DEVELOPMENT seeds {1,2,3} (`CALIBRATION_SEEDS`' own
first three), explicitly preserving the fresh held-out block (4001-4015,
`validation_manifest_2026-09-15.md`) for later use.

Purpose: decide whether the approved model/observation specification can jointly approach the
target region at all, before spending the ~89-minute validation-manifest budget. Directly
informed by the replenished-capital budget bound
(`data/review_v2/replenished_capital_budget_bound.md`): does the model's REPLENISHED
population (agents who have been hard-discouraged at least once) ever produce k=0-clock
long-term search, and how much of the U population is replenished vs. still spending down
initial capital, at three points along a 3,000-step transition.

Uses the streaming collectors (`scripts/observation_layer.py`) hooked directly into the live
step loop -- no full per-agent trace collection (see `validation_manifest_2026-09-15.md`
F6.6 for why: memory would scale with agents x steps, not steps alone).

Grid (9 combinations x 3 development seeds = 27 trajectories, 3,000 steps each):
`search_cost_per_trip` (a) in {0.002514642203001423 (published anchor), 0.0074, 0.02
(admissible upper bound)} x `firm_kappa` in {0.22393789239458572 (anchor), 0.9, 2.0}. All
other config fields at their approved/baseline values: n_agents=500,
initial_search_capital=1.4962 FIXED, firm_radius=2.5 FIXED, transport_cost_rate=0.000145
(primary slope) -- none of these are estimated or varied here.

Windows (three SEPARATE transition diagnostics, NOT merged, NOT claimed stationary): steps
[51,150], [1351,1500], [2851,3000]. Duration-clock state is carried through the WHOLE
3,000-step run continuously (the F3 lesson) -- windows only control which steps'
observations are aggregated into each reported row, never reset any clock.

Writes:
    results/review_v2/settled_regime/feasibility_screen_2026-09-15.csv (long format)
    results/review_v2/settled_regime/feasibility_screen_2026-09-15_manifest.json
        (configuration, seeds, code fingerprint, commands, output hash -- per instruction)

Usage:
    python -m scripts.feasibility_screen --smoke-test   # one trajectory, times/measures it
    python -m scripts.feasibility_screen                # the full 27-trajectory screen
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
import tracemalloc
from dataclasses import replace
from pathlib import Path

from joblib import Parallel, delayed

from scripts.diagnose_window_stability import _capital_quantile_row
from scripts.observation_layer import (
    StreamingCumulativeActiveState,
    StreamingEpisodeClockState,
    StreamingMonthlySummary,
    StreamingTransportSummary,
    classify_observation,
)
from src.agents import WAGE, SeekerState
from src.config import Config
from src.model import CityModel
from src.moments import DAYS_PER_MONTH

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "results" / "review_v2" / "settled_regime"
CSV_PATH = OUT_DIR / "feasibility_screen_2026-09-15.csv"
MANIFEST_PATH = OUT_DIR / "feasibility_screen_2026-09-15_manifest.json"

# CALIBRATION_SEEDS' own first three -- already-used DEVELOPMENT seeds, NOT the held-out
# 4001-4015 block reserved for the validation manifest.
DEV_SEEDS = (1, 2, 3)
A_GRID = (0.002514642203001423, 0.0074, 0.02)
KAPPA_GRID = (0.22393789239458572, 0.9, 2.0)
N_STEPS = 3000
WINDOWS = {"w1_51_150": (51, 150), "w2_1351_1500": (1351, 1500), "w3_2851_3000": (2851, 3000)}
CLOCK_KS = {"k0": 0, "k1": 1, "k3": 3, "kinf": 10**9}
N_JOBS = 6


def build_config(a: float, kappa: float, seed: int) -> Config:
    base = Config.from_yaml(REPO_ROOT / "configs" / "baseline.yaml")
    return replace(
        base,
        n_agents=500,
        n_steps=N_STEPS,
        seed=seed,
        initial_search_capital=1.4962,
        firm_radius=2.5,
        transport_cost_rate=0.000145,
        search_cost_per_trip=a,
        firm_kappa=kappa,
    )


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def run_one_trajectory(a: float, kappa: float, seed: int) -> list[dict]:
    """One 3,000-step trajectory, streaming-collector-instrumented throughout. Returns one
    row per (window, metric)."""
    cfg = build_config(a, kappa, seed)
    model = CityModel(cfg)

    episode_states: dict[int, dict[str, StreamingEpisodeClockState]] = {}
    cumulative_states: dict[int, StreamingCumulativeActiveState] = {}
    monthly_summaries = {
        label: StreamingMonthlySummary(threshold_months=12) for label in (*CLOCK_KS, "cumulative")
    }
    transport_summary = StreamingTransportSummary()
    ever_discouraged: dict[int, bool] = {}
    daily_wage = WAGE / DAYS_PER_MONTH

    n_u_replenished: dict[int, int] = {}
    n_u_replenished_lt: dict[int, int] = {}
    n_u_initial: dict[int, int] = {}
    n_u_initial_lt: dict[int, int] = {}
    n_d_total: dict[int, int] = {}
    n_observed_total: dict[int, int] = {}
    capital_snapshots: dict[int, dict] = {}
    window_ends = {hi for _, hi in WINDOWS.values()}

    for _ in range(cfg.n_steps):
        model.step()
        step = model.steps
        for agent in model._seekers():
            uid = agent.unique_id
            if uid not in episode_states:
                episode_states[uid] = {
                    label: StreamingEpisodeClockState(k) for label, k in CLOCK_KS.items()
                }
                cumulative_states[uid] = StreamingCumulativeActiveState()
                ever_discouraged[uid] = False

            category = classify_observation(agent.state.name, agent.belief_inactive_this_step)
            n_observed_total[step] = n_observed_total.get(step, 0) + 1
            if category == "D":
                n_d_total[step] = n_d_total.get(step, 0) + 1

            was_ever_discouraged = ever_discouraged[uid]
            if agent.state is SeekerState.DISCOURAGED:
                ever_discouraged[uid] = True

            for label in CLOCK_KS:
                duration = episode_states[uid][label].observe(category)
                monthly_summaries[label].observe(step, category, duration)
                if label == "k0" and category == "U":
                    if was_ever_discouraged:
                        n_u_replenished[step] = n_u_replenished.get(step, 0) + 1
                        if duration is not None and duration >= 12:
                            n_u_replenished_lt[step] = n_u_replenished_lt.get(step, 0) + 1
                    else:
                        n_u_initial[step] = n_u_initial.get(step, 0) + 1
                        if duration is not None and duration >= 12:
                            n_u_initial_lt[step] = n_u_initial_lt.get(step, 0) + 1

            cum_duration = cumulative_states[uid].observe(category)
            monthly_summaries["cumulative"].observe(step, category, cum_duration)

            if agent.trips_this_step >= 1:
                cost = cfg.search_cost_per_trip + cfg.transport_cost_rate * agent.distance_to_cbd
                transport_summary.observe(step, agent.trips_this_step * cost, agent.trips_this_step)

        if step in window_ends:
            capital_snapshots[step] = _capital_quantile_row(model)

    rows: list[dict] = []

    def base_row(window_label: str, metric: str) -> dict:
        return dict(
            candidate_a=a, candidate_kappa=kappa, seed=seed, window=window_label, metric=metric
        )

    for window_label, (lo, hi) in WINDOWS.items():
        window_steps = range(lo, hi + 1)
        for label in (*CLOCK_KS, "cumulative"):
            result = monthly_summaries[label].result(window_steps)
            rows.append(
                dict(**base_row(window_label, f"long_term_share_{label}_equal_month"), **result)
            )

        for weighting in ("equal_person", "trip_weighted"):
            result = transport_summary.result(window_steps, weighting)
            ratio = result["estimate"] / daily_wage if result["estimate"] is not None else None
            r = base_row(window_label, f"transport_ratio_{weighting}")
            r.update(
                share=ratio,
                n_months_used=result["n_months_used"],
                n_months_empty=result["n_months_empty"],
            )
            rows.append(r)

        d_shares, n_empty = [], 0
        for s in window_steps:
            total = n_observed_total.get(s, 0)
            if total == 0:
                n_empty += 1
                continue
            d_shares.append(n_d_total.get(s, 0) / total)
        r = base_row(window_label, "discouraged_share_EUD_post_matching_equal_month")
        r.update(
            share=(sum(d_shares) / len(d_shares)) if d_shares else None,
            n_months_used=len(d_shares),
            n_months_empty=n_empty,
        )
        rows.append(r)

        for pop_label, n_dict, n_lt_dict in (
            ("replenished", n_u_replenished, n_u_replenished_lt),
            ("initial_capital_supported", n_u_initial, n_u_initial_lt),
        ):
            total_u = sum(n_dict.get(s, 0) for s in window_steps)
            total_lt = sum(n_lt_dict.get(s, 0) for s in window_steps)
            total_all_u = sum(
                n_u_replenished.get(s, 0) + n_u_initial.get(s, 0) for s in window_steps
            )
            r = base_row(window_label, f"k0_long_term_share_within_{pop_label}_U")
            r.update(
                share=(total_lt / total_u) if total_u else None,
                n_stock=total_u,
                sample_share_of_U=(total_u / total_all_u) if total_all_u else None,
            )
            rows.append(r)

        snap = capital_snapshots.get(hi, {})
        for key in (
            "capital_all_mean",
            "capital_all_q50",
            "capital_non_employed_mean",
            "capital_non_employed_q50",
        ):
            r = base_row(window_label, key)
            r.update(share=snap.get(key))
            rows.append(r)

    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--smoke-test", action="store_true", help="Run only the anchor point, seed 1."
    )
    args = parser.parse_args()

    import pandas as pd  # local import: keep module import light for --smoke-test timing

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.smoke_test:
        print("=== SMOKE TEST: one trajectory (anchor a, anchor kappa, seed=1) ===")
        tracemalloc.start()
        t0 = time.perf_counter()
        rows = run_one_trajectory(A_GRID[0], KAPPA_GRID[0], DEV_SEEDS[0])
        t1 = time.perf_counter()
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        print(f"Wall clock: {t1 - t0:.2f}s for {N_STEPS} steps ({(t1 - t0) / N_STEPS:.5f} s/step)")
        print(f"Peak traced memory: {peak / 1e6:.1f} MB")
        print(f"Rows produced: {len(rows)}")
        est_27 = (t1 - t0) * 27 / N_JOBS
        print(
            f"Extrapolated full screen (27 trajectories, N_JOBS={N_JOBS}): "
            f"~{est_27:.0f}s (~{est_27 / 60:.1f} min)"
        )
        return

    jobs = [(a, k, s) for a in A_GRID for k in KAPPA_GRID for s in DEV_SEEDS]
    print(f"Running {len(jobs)} trajectories at N_JOBS={N_JOBS}...")
    t0 = time.perf_counter()
    results = Parallel(n_jobs=N_JOBS)(delayed(run_one_trajectory)(a, k, s) for a, k, s in jobs)
    t1 = time.perf_counter()
    print(f"Wall clock: {t1 - t0:.2f}s for {len(jobs)} trajectories")

    all_rows = [row for traj_rows in results for row in traj_rows]
    df = pd.DataFrame(all_rows)
    df.to_csv(CSV_PATH, index=False)
    print(f"Wrote {CSV_PATH} ({len(df)} rows)")

    output_hash = hashlib.sha256(CSV_PATH.read_bytes()).hexdigest()
    manifest = dict(
        commands=["python -m scripts.feasibility_screen"],
        code_fingerprint_git_commit=_git_commit(),
        dev_seeds=list(DEV_SEEDS),
        a_grid=list(A_GRID),
        kappa_grid=list(KAPPA_GRID),
        n_steps=N_STEPS,
        windows={k: list(v) for k, v in WINDOWS.items()},
        n_trajectories=len(jobs),
        wall_clock_seconds=t1 - t0,
        n_jobs=N_JOBS,
        output_csv=str(CSV_PATH.relative_to(REPO_ROOT)),
        output_csv_sha256=output_hash,
        output_rows=len(df),
    )
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
