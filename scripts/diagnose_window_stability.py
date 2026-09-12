"""P2 gate: locate a settled observation window under the ongoing-labour-market framing.

Aakash's decision on Question 1 (`DECISIONS_PENDING.md`): calibrate against a sufficiently
settled baseline, not the raw transient window P1.2 found the published one to be, and demote
`initial_search_capital` from an estimated stationary parameter to an initialisation setting only
once its influence is demonstrably negligible. His explicit instruction is not to pick that
window from `discouraged_share` alone -- every retained calibration moment, and the capital
distribution, have to be checked across initial conditions and seeds.

This computes the actual four calibration moments, imported directly from `src/moments.py` (not
reimplemented, so this cannot silently drift from what a real calibration run computes) at a
series of candidate window endpoints, crossed with the same initial-capital-multiplier x
initialisation-scheme sweep P1.2 used (`scripts/diagnose_horizon.py`'s snapshot/transplant
helpers are imported, not duplicated).

`distance_gradient_slope` is cross-sectional on the model's *current* state (see its docstring in
moments.py), not window-averaged, so it is read directly off the live model object at each
window's end step, in the same continuous run used for the time-averaged moments below --
avoiding the divergent-RNG-path problem a series of independent truncated re-runs would have.

Usage:
    python -m scripts.diagnose_window_stability --config configs/baseline.yaml \
        --params results/published/calibration_result.json \
        --seeds 1001:1003 --steps 2400 \
        --initial-capital-multiplier 0.5,1,2 --mixed-state-donor-steps 600 \
        --output-dir results/review_v2/window_stability

Outputs, under --output-dir:
    manifest.json       config, seeds, code fingerprint, command
    moment_summary.csv   one row per (config_label, seed, window): all four calibration moments
                         plus non-employed and whole-population capital quantiles at the
                         window's end step
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.diagnose_horizon import (  # noqa: E402
    _apply_dynamic_state,
    _parse_seed_spec,
    _snapshot_dynamic_state,
    _source_fingerprint,
    _windows,
)
from src.agents import SeekerState  # noqa: E402
from src.config import Config  # noqa: E402
from src.model import CityModel  # noqa: E402
from src.moments import (  # noqa: E402
    discouraged_share,
    distance_gradient_slope,
    long_term_share,
    transport_budget_share,
)

CAPITAL_QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)


def _capital_quantile_row(model: CityModel) -> dict:
    seekers = list(model._seekers())
    non_employed = [a.search_capital for a in seekers if a.state is not SeekerState.EMPLOYED]
    everyone = [a.search_capital for a in seekers]
    row = {"n_non_employed": len(non_employed), "n_agents": len(everyone)}
    for label, values in (("non_employed", non_employed), ("all", everyone)):
        s = pd.Series(values, dtype=float)
        for q in CAPITAL_QUANTILES:
            row[f"capital_{label}_q{int(q * 100)}"] = s.quantile(q) if len(s) else float("nan")
        row[f"capital_{label}_mean"] = s.mean() if len(s) else float("nan")
    return row


def _step_and_checkpoint(model: CityModel, checkpoint_ends: set[int]) -> dict[int, dict]:
    """Steps an already-constructed model to its configured horizon, reading the cross-sectional
    moment and the capital snapshot off the live model at each window's end step -- in the same
    RNG path `model.history` is recorded from, rather than a separate re-run."""
    checkpoints: dict[int, dict] = {}
    for step_idx in range(1, model.config.n_steps + 1):
        model.step()
        if step_idx in checkpoint_ends:
            row = _capital_quantile_row(model)
            row["distance_gradient_slope"] = distance_gradient_slope(model)
            checkpoints[step_idx] = row
    return checkpoints


def _run_checkpointed(config: Config) -> tuple[pd.DataFrame, dict[int, dict]]:
    model = CityModel(config)
    checkpoint_ends = {hi for _, hi in _windows(config.n_steps, config.burn_in_steps)}
    checkpoints = _step_and_checkpoint(model, checkpoint_ends)
    history = pd.DataFrame(model.history)
    return history, checkpoints


def build_moment_summary(
    history: pd.DataFrame,
    checkpoints: dict[int, dict],
    config_label: str,
    seed: int,
    n_agents: int,
    burn_in: int,
) -> pd.DataFrame:
    rows = []
    for lo, hi in _windows(int(history["step"].max()), burn_in):
        window = history[(history["step"] >= lo) & (history["step"] <= hi)]
        if window.empty or hi not in checkpoints:
            continue
        row = {
            "config_label": config_label,
            "seed": seed,
            "window": f"{lo}-{hi}",
            "discouraged_share": discouraged_share(window, n_agents),
            "transport_budget_share": transport_budget_share(window),
            "long_term_share": long_term_share(window),
            **checkpoints[hi],
        }
        rows.append(row)
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P2 gate: settled-window search")
    parser.add_argument("--config", required=True)
    parser.add_argument("--params", default=None)
    parser.add_argument("--seeds", required=True, help='e.g. "1001:1003" or "1001,1002,1003"')
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument(
        "--burn-in", type=int, default=None, help="override the config's own burn_in_steps"
    )
    parser.add_argument("--initial-capital-multiplier", default=None)
    parser.add_argument(
        "--vary-param",
        default=None,
        help="a Config field to sweep instead of initial_search_capital, e.g. "
        "search_cost_per_trip, firm_radius, firm_kappa. Absolute values, not multipliers -- "
        "see --vary-values.",
    )
    parser.add_argument(
        "--vary-values",
        default=None,
        help="comma list of absolute values for --vary-param, one config_label per value.",
    )
    parser.add_argument("--mixed-state-donor-steps", type=int, default=None)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    base_config = Config.from_yaml(args.config)
    if args.params:
        overrides = json.loads(Path(args.params).read_text(encoding="utf-8"))["params"]
        base_config = replace(base_config, **overrides)
    base_config = replace(base_config, n_steps=args.steps)
    if args.burn_in is not None:
        base_config = replace(base_config, burn_in_steps=args.burn_in)
    burn_in = base_config.burn_in_steps

    seeds = _parse_seed_spec(args.seeds)
    configs: dict[str, Config] = {}
    if args.vary_param:
        for value in (float(x) for x in args.vary_values.split(",")):
            configs[f"{args.vary_param}_{value}"] = replace(base_config, **{args.vary_param: value})
    else:
        multipliers = (
            [float(x) for x in args.initial_capital_multiplier.split(",")]
            if args.initial_capital_multiplier
            else [None]
        )
        for mult in multipliers:
            if mult is None:
                configs["base"] = base_config
            else:
                configs[f"capital_{mult}x"] = replace(
                    base_config, initial_search_capital=base_config.initial_search_capital * mult
                )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_summaries = []
    for config_label, cfg in configs.items():
        for seed in seeds:
            run_cfg = replace(cfg, seed=seed)
            history, checkpoints = _run_checkpointed(run_cfg)
            all_summaries.append(
                build_moment_summary(
                    history, checkpoints, config_label, seed, run_cfg.n_agents, burn_in
                )
            )

            if args.mixed_state_donor_steps is not None:
                donor = CityModel(replace(run_cfg, n_steps=args.mixed_state_donor_steps))
                for _ in range(args.mixed_state_donor_steps):
                    donor.step()
                snapshot = _snapshot_dynamic_state(donor)

                recipient = CityModel(run_cfg)
                _apply_dynamic_state(recipient, snapshot)
                checkpoint_ends = {hi for _, hi in _windows(run_cfg.n_steps, burn_in)}
                mixed_checkpoints = _step_and_checkpoint(recipient, checkpoint_ends)
                mixed_history = pd.DataFrame(recipient.history)
                mixed_label = (
                    f"{config_label}_mixed_state" if config_label != "base" else "mixed_state"
                )
                all_summaries.append(
                    build_moment_summary(
                        mixed_history,
                        mixed_checkpoints,
                        mixed_label,
                        seed,
                        run_cfg.n_agents,
                        burn_in,
                    )
                )

    moment_summary = pd.concat(all_summaries, ignore_index=True)
    moment_summary.to_csv(out_dir / "moment_summary.csv", index=False)

    manifest = {
        "command": "python -m scripts.diagnose_window_stability " + " ".join(sys.argv[1:]),
        "config_path": args.config,
        "params_path": args.params,
        "seeds": seeds,
        "steps": args.steps,
        "burn_in_steps": burn_in,
        "config_labels": list(configs.keys()),
        "code_fingerprint": _source_fingerprint(),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"wrote {out_dir}")
    print(f"{len(moment_summary)} (config_label, seed, window) rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
