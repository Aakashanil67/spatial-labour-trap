"""P1.1: reproducible temporal/resource diagnostic.

Extends the original A7 scratch diagnostic (never committed -- see EXECUTION_STATUS.md) into a
proper, reusable script, closing the specific gaps the execution plan names against it:

  - the published measurement window (steps burn_in+1..150) is reported explicitly and
    separately from the initial transient, which A7's first "1-150" window conflated with it
  - capital is tracked for a fixed panel of individual agents over the whole horizon, not only
    as a changing population mean, using the model's own existing trace mechanism
    (config.trace_agent_ids / model.trace_dataframe()) rather than new instrumentation
  - each agent's resource balance is reconciled every step: opening capital + credited inflow
    - paid search cost = closing capital, verified exactly rather than assumed

No source file is modified. Capital-quantile-by-ever-employed and never-employed-share tracking,
which nothing in the committed code already records, are added by external monkeypatching only
-- the same technique B4a and the original A7 diagnostic used, formalised here into one script
instead of a one-off.

Usage:
    python -m scripts.diagnose_horizon --config configs/baseline.yaml \
        --params results/published/calibration_result.json \
        --seeds 1001:1003 --steps 1200 \
        --output-dir results/review_v2/temporal_<campaign_id>

Outputs, under --output-dir:
    manifest.json        config, seeds, code fingerprint, command, resource-balance result
    time_series.csv      one row per (config_label, seed, step): every share, flow count and
                          capital quantile the window/capital summaries are built from
    window_summary.csv   one row per (config_label, seed, window): windowed means
    capital_summary.csv  one row per (config_label, seed, step, ever_employed): capital
                          quantiles among the non-employed, split by employment history
    trace_<config_label>_<seed>.csv   the fixed-panel individual trajectories for one run
    horizon_diagnostic.png            one figure per config_label, reusing A7's layout
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.agents import JobSeeker, SeekerState  # noqa: E402
from src.config import Config  # noqa: E402
from src.model import CityModel  # noqa: E402

CAPITAL_QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)
_SOURCE_FILES = ("src/agents.py", "src/model.py", "src/moments.py", "src/config.py")


def _source_fingerprint() -> str:
    hasher = hashlib.sha256()
    for rel_path in _SOURCE_FILES:
        hasher.update((REPO / rel_path).read_bytes())
    return hasher.hexdigest()[:16]


def _parse_seed_spec(spec: str) -> list[int]:
    if ":" in spec:
        lo, hi = spec.split(":", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(s) for s in spec.split(",")]


def _first_seeker_ids_by_quartile(config: Config, n_per_quartile: int = 1) -> tuple[int, ...]:
    """Picks a small, fixed panel of agents spanning wealth quartiles, using the same
    probe-a-throwaway-model pattern tests/test_spatial.py already establishes -- unique_ids
    are assigned at construction (firms first, then agents), so this has to inspect a real
    model instance rather than guess an offset."""
    probe = CityModel(config)
    by_quartile: dict[int, list[int]] = {0: [], 1: [], 2: [], 3: []}
    for agent in sorted(probe._seekers(), key=lambda a: a.unique_id):
        by_quartile[agent.wealth_quartile].append(agent.unique_id)
    chosen = []
    for q in (0, 1, 2, 3):
        chosen.extend(by_quartile[q][:n_per_quartile])
    return tuple(chosen)


def _run_instrumented(config: Config) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Runs one simulation with external instrumentation for exactly what the committed history
    does not already record: ever-employed status per agent, and the resource-balance components
    (credited inflow, paid search cost) needed to reconcile opening/closing capital every step.

    Returns (history, capital_panel, balance_result). `history` is the model's own recorded
    per-step aggregate (u, l, discouraged, m, n_separations, n_reentries, n_belief_inactive,
    mean_search_capital, ...) -- reused rather than re-derived, since it is already correct and
    re-deriving hires/separations/reentries from before/after snapshots would risk a subtly
    different (and unverified) timing convention from the one the model itself uses.
    `capital_panel` is one row per (step, agent_id): capital, state, ever_employed -- built here
    since nothing in the committed code records this breakdown. `balance_result` reports whether
    the resource identity held exactly and, if not, the largest violation found.

    The fixed-individual trace (config.trace_agent_ids) is deliberately not captured here: this
    function runs every seed of the main sweep, and the trace is wanted for one illustrative run
    per config_label, not every seed -- see main()'s dedicated trace runs below."""
    ever_employed: set[int] = set()
    capital_rows: list[dict] = []
    balance_violations: list[tuple[int, int, float]] = []

    orig_resolve_hire = JobSeeker.resolve_hire
    orig_step_searching = JobSeeker.step_searching
    orig_step_discouraged = JobSeeker.step_discouraged
    orig_step = CityModel.step

    inflow_this_step: dict[int, float] = {}
    cost_this_step: dict[int, float] = {}

    def patched_resolve_hire(self):
        ever_employed.add(self.unique_id)
        return orig_resolve_hire(self)

    def patched_step_searching(self):
        orig_step_searching(self)
        cost_this_step[self.unique_id] = self.trips_this_step * self.cost_per_trip

    def patched_step_discouraged(self):
        cfg = self.model.config
        inflow_this_step[self.unique_id] = cfg.household_inflow
        orig_step_discouraged(self)

    def patched_step(self):
        capital_before = {a.unique_id: a.search_capital for a in self._seekers()}
        inflow_this_step.clear()
        cost_this_step.clear()
        orig_step(self)
        for agent in self._seekers():
            before = capital_before[agent.unique_id]
            inflow = inflow_this_step.get(agent.unique_id, 0.0)
            cost = cost_this_step.get(agent.unique_id, 0.0)
            expected_after = before + inflow - cost
            actual_after = agent.search_capital
            discrepancy = abs(actual_after - expected_after)
            if discrepancy > 1e-9:
                balance_violations.append((self.steps, agent.unique_id, discrepancy))
            if agent.state is not SeekerState.EMPLOYED:
                capital_rows.append(
                    {
                        "step": self.steps,
                        "agent_id": agent.unique_id,
                        "search_capital": agent.search_capital,
                        "ever_employed": agent.unique_id in ever_employed,
                    }
                )

    JobSeeker.resolve_hire = patched_resolve_hire
    JobSeeker.step_searching = patched_step_searching
    JobSeeker.step_discouraged = patched_step_discouraged
    CityModel.step = patched_step
    try:
        model = CityModel(config)
        history = model.run()
    finally:
        JobSeeker.resolve_hire = orig_resolve_hire
        JobSeeker.step_searching = orig_step_searching
        JobSeeker.step_discouraged = orig_step_discouraged
        CityModel.step = orig_step

    never_employed_share = (
        pd.DataFrame(capital_rows)
        .assign(never_employed=lambda d: ~d["ever_employed"])
        .groupby("step")["never_employed"]
        .mean()
        if capital_rows
        else pd.Series(dtype=float)
    )
    history = history.copy()
    history["never_employed_share_of_non_employed"] = history["step"].map(never_employed_share)

    balance_result = {
        "n_violations": len(balance_violations),
        "max_discrepancy": max((d for _, _, d in balance_violations), default=0.0),
        "n_agent_steps_checked": config.n_agents * config.n_steps,
    }

    capital_df = pd.DataFrame(capital_rows)
    return history, capital_df, balance_result


def _windows(n_steps: int, burn_in: int) -> list[tuple[int, int]]:
    """The published window (burn_in+1..150) always appears first and separately, per the
    plan's explicit correction to A7's own first window (1-150), which included the initial
    transient. Subsequent windows are consecutive 150-step blocks from 151 to n_steps."""
    windows = [(burn_in + 1, 150)]
    start = 151
    while start + 149 <= n_steps:
        windows.append((start, start + 149))
        start += 150
    if start <= n_steps:
        windows.append((start, n_steps))  # a final, possibly shorter, trailing window
    return windows


def build_window_summary(
    history: pd.DataFrame, config_label: str, seed: int, burn_in: int
) -> pd.DataFrame:
    rows = []
    for lo, hi in _windows(int(history["step"].max()), burn_in):
        window = history[(history["step"] >= lo) & (history["step"] <= hi)]
        if window.empty:
            continue
        n = window["u"].iloc[0] + window["l"].iloc[0] + window["discouraged"].iloc[0]
        rows.append(
            {
                "config_label": config_label,
                "seed": seed,
                "window": f"{lo}-{hi}",
                "n_steps_in_window": len(window),
                "employment_share": (window["l"] / n).mean(),
                "hard_discouraged_share": (window["discouraged"] / n).mean(),
                "broad_inactive_share": (
                    (window["discouraged"] + window["n_belief_inactive"]) / n
                ).mean(),
                "active_search_share": ((window["u"] - window["n_belief_inactive"]) / n).mean(),
                "never_employed_share_of_non_employed": window[
                    "never_employed_share_of_non_employed"
                ].mean(),
                "mean_hires_per_step": window["m"].mean(),
                "mean_separations_per_step": window["n_separations"].mean(),
                "mean_reentries_per_step": window["n_reentries"].mean(),
                "mean_new_discouraged_per_step": window["n_new_discouraged"].mean(),
                "mean_search_capital": window["mean_search_capital"].mean(),
            }
        )
    return pd.DataFrame(rows)


def build_capital_summary(capital_df: pd.DataFrame, config_label: str, seed: int) -> pd.DataFrame:
    if capital_df.empty:
        return pd.DataFrame()
    rows = []
    for (step, ever), group in capital_df.groupby(["step", "ever_employed"]):
        quantiles = group["search_capital"].quantile(CAPITAL_QUANTILES)
        row = {
            "config_label": config_label,
            "seed": seed,
            "step": step,
            "ever_employed": ever,
            "n": len(group),
            "mean": group["search_capital"].mean(),
        }
        for q in CAPITAL_QUANTILES:
            row[f"q{int(q * 100)}"] = quantiles.loc[q]
        rows.append(row)
    return pd.DataFrame(rows)


def build_figure(time_series: pd.DataFrame, output_path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))

    ax = axes[0]
    for config_label, sub in time_series.groupby("config_label"):
        by_step = sub.groupby("step")["broad_inactive_share_step"].mean()
        ax.plot(by_step.index, by_step.values, label=config_label, alpha=0.85)
    ax.set_xlabel("step")
    ax.set_ylabel("broad inactive share (mean across seeds)")
    ax.set_title("Discouraged + belief-inactive share over the horizon")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    ax = axes[1]
    for config_label, sub in time_series.groupby("config_label"):
        by_step = sub.groupby("step")["never_employed_share_of_non_employed"].mean()
        ax.plot(by_step.index, by_step.values, label=config_label, alpha=0.85)
    ax.set_xlabel("step")
    ax.set_ylabel("never-employed share of the non-employed population")
    ax.set_title("Composition of the non-employed population")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P1.1 temporal/resource diagnostic")
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--params", default=None, help="calibration_result.json to override estimated params"
    )
    parser.add_argument("--seeds", required=True, help='e.g. "1001:1003" or "1001,1002,1003"')
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument(
        "--household-inflow",
        default=None,
        help="comma list of household_inflow overrides, one config_label per value, e.g. "
        "0.004,0.008,0.016. Omit to run --config's own value once, labelled 'base'.",
    )
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    base_config = Config.from_yaml(args.config)
    if args.params:
        overrides = json.loads(Path(args.params).read_text(encoding="utf-8"))["params"]
        base_config = replace(base_config, **overrides)
    base_config = replace(base_config, n_steps=args.steps)
    burn_in = base_config.burn_in_steps

    seeds = _parse_seed_spec(args.seeds)
    if args.household_inflow:
        inflow_values = [float(x) for x in args.household_inflow.split(",")]
        configs = {f"inflow_{v}": replace(base_config, household_inflow=v) for v in inflow_values}
    else:
        configs = {"base": base_config}

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_time_series = []
    all_window_summaries = []
    all_capital_summaries = []
    balance_results = {}

    for config_label, cfg in configs.items():
        for seed in seeds:
            run_cfg = replace(cfg, seed=seed)
            history, capital_df, balance_result = _run_instrumented(run_cfg)
            balance_results[f"{config_label}/{seed}"] = balance_result

            n = history["u"] + history["l"] + history["discouraged"]
            history = history.assign(
                config_label=config_label,
                seed=seed,
                employment_share_step=history["l"] / n,
                broad_inactive_share_step=(history["discouraged"] + history["n_belief_inactive"])
                / n,
            )
            all_time_series.append(history)
            all_window_summaries.append(build_window_summary(history, config_label, seed, burn_in))
            all_capital_summaries.append(build_capital_summary(capital_df, config_label, seed))

    time_series = pd.concat(all_time_series, ignore_index=True)
    window_summary = pd.concat(all_window_summaries, ignore_index=True)
    capital_summary = pd.concat(all_capital_summaries, ignore_index=True)

    time_series.to_csv(out_dir / "time_series.csv", index=False)
    window_summary.to_csv(out_dir / "window_summary.csv", index=False)
    capital_summary.to_csv(out_dir / "capital_summary.csv", index=False)
    build_figure(time_series, out_dir / "horizon_diagnostic.png")

    # Fixed-panel individual trajectories, one file per (config_label, first seed) using the
    # model's own existing trace mechanism.
    for config_label, cfg in configs.items():
        first_seed = seeds[0]
        trace_ids = _first_seeker_ids_by_quartile(replace(cfg, seed=first_seed), n_per_quartile=2)
        traced_cfg = replace(cfg, seed=first_seed, trace_agent_ids=trace_ids)
        traced_model = CityModel(traced_cfg)
        traced_model.run()
        traced_model.trace_dataframe().to_csv(
            out_dir / f"trace_{config_label}_{first_seed}.csv", index=False
        )

    total_violations = sum(r["n_violations"] for r in balance_results.values())
    max_discrepancy = max((r["max_discrepancy"] for r in balance_results.values()), default=0.0)
    total_checked = sum(r["n_agent_steps_checked"] for r in balance_results.values())

    manifest = {
        "command": "python -m scripts.diagnose_horizon " + " ".join(sys.argv[1:]),
        "config_path": args.config,
        "params_path": args.params,
        "seeds": seeds,
        "steps": args.steps,
        "burn_in_steps": burn_in,
        "config_labels": list(configs.keys()),
        "code_fingerprint": _source_fingerprint(),
        "resource_balance": {
            "total_agent_steps_checked": total_checked,
            "total_violations": total_violations,
            "max_discrepancy": max_discrepancy,
            "reconciled_exactly": total_violations == 0,
        },
        "per_run_balance": balance_results,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"wrote {out_dir}")
    print(
        f"resource balance: {total_checked} agent-steps checked, {total_violations} violations, "
        f"max discrepancy {max_discrepancy:.2e}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
