"""Validation pilot for a staged, bounded adaptive burn-in.

The settled-regime assessment (`results/review_v2/settled_regime/assessment.md`) found that
`firm_kappa`'s convergence speed varies enormously across its own calibration bounds -- fast
near the fitted point, needing on the order of 9,000 steps near the upper bound. A single fixed
burn-in cannot serve both cheaply. Aakash's chosen fix, kept out of `calibrate.py` until this
pilot validates it: detect convergence per candidate against prespecified checkpoints and a
prespecified criterion, up to a prespecified computational limit; candidates that reach the
limit are UNRESOLVED, not scored as poor fits; and the moments actually reported come from a
fresh measurement block collected *after* convergence is accepted, never from the same window
used to detect it (using the detection window for both would condition the reported value on
its own apparent stability -- a look-elsewhere bias, not a design detail).

## Specification (prespecified, not tuned against this pilot's own results)

- Detection window length: 450 steps (3x the standard 150-step window; the settled-regime
  assessment's window-length check found the extra length buys a real, if modest, precision
  gain over 150).
- Checkpoints (window END step): 900, 1350, 1800, 2250, 3150, 4500, 6300, 9000. Spacing is
  uniform (450 steps) through the region the fitted point already settles in, then widens by
  about 1.5x per step so a slow candidate isn't charged for many redundant fine-grained checks
  it has no chance of passing yet.
- Computational limit: 9,000 steps, the last checkpoint -- chosen from the settled-regime
  assessment's own extrapolation of firm_kappa=2.0's decay rate to full convergence.
- Convergence rule: at checkpoint k (k >= 3, i.e. at least two consecutive comparisons
  available), for all four calibration moments, the absolute change in the moment's
  window-average between checkpoint k and k-1 must be no larger than that moment's own
  simulation standard error of the mean at 15 seeds (`results/review_v2/settled_regime/
  precision_decomposition.csv`'s settled-window `sim_var_of_mean`) -- and this must hold for
  two consecutive checkpoint-to-checkpoint comparisons in a row, not one. Convergence is
  accepted at the later of the two checkpoints.
- Measurement block: steps [accepted_checkpoint + 1, accepted_checkpoint + 150] -- a window
  never used in the convergence decision.
- A candidate that never satisfies the rule by checkpoint 9,000 is UNRESOLVED: its last
  measurement block is still recorded, tagged as unresolved, and must not be scored as if it
  were a converged, poor-fitting point.

## Validation design

Each candidate is stepped to 15,000 steps once, per seed, recording every checkpoint window
along the way plus a long, low-noise reference window (13,501-15,000, 1,500 steps) used as the
best available approximation to the "true" settled value. Since the checkpoint windows and the
reference window come from the *same* simulated trajectory (same config, same seed), this is an
exact paired comparison, not two independent estimates -- the adaptive procedure's reported
moments, whatever checkpoint they were accepted at, are compared against a later window drawn
from the identical path. `distance_gradient_slope` is cross-sectional, read at step 15,000
itself, not window-averaged; the settled-regime assessment already found this moment may still
be drifting even past step 4,650, so 15,000 is the best available reference, not a guaranteed
settled one, and is reported as such rather than assumed.

Representative candidates: the fitted point (`search_cost_per_trip`, `firm_radius`,
`firm_kappa` all at their published values -- expected fast), `firm_kappa` = 0.9
(`configs/baseline.yaml`'s original default -- expected slow) and 1.4 (expected slower), and
`firm_kappa` = 2.0 (the calibration upper bound -- expected to reach the limit unresolved).

Usage:
    python -m scripts.adaptive_burn_in_pilot \
        --config configs/baseline.yaml --params results/published/calibration_result.json \
        --precision-csv results/review_v2/settled_regime/precision_decomposition.csv \
        --output-dir results/review_v2/settled_regime/adaptive_pilot
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd
from joblib import Parallel, delayed

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.diagnose_horizon import _source_fingerprint  # noqa: E402
from src.calibrate import CALIBRATION_SEEDS  # noqa: E402
from src.config import Config  # noqa: E402
from src.model import CityModel  # noqa: E402
from src.moments import (  # noqa: E402
    discouraged_share,
    distance_gradient_slope,
    long_term_share,
    transport_budget_share,
)

DETECTION_WINDOW = 450
CHECKPOINTS: tuple[int, ...] = (900, 1350, 1800, 2250, 3150, 4500, 6300, 9000)
COMPUTATIONAL_LIMIT = CHECKPOINTS[-1]
MEASUREMENT_BLOCK = 150
REFERENCE_WINDOW = (13501, 15000)
HORIZON = 15000
N_JOBS = 6

CANDIDATES: dict[str, dict[str, float]] = {
    "fitted": {},
    "firm_kappa_0.9": {"firm_kappa": 0.9},
    "firm_kappa_1.4": {"firm_kappa": 1.4},
    "firm_kappa_2.0": {"firm_kappa": 2.0},
}


def _history_window_moments(history: pd.DataFrame, lo: int, hi: int, n_agents: int) -> dict:
    window = history[(history["step"] >= lo) & (history["step"] <= hi)]
    return {
        "discouraged_share": discouraged_share(window, n_agents),
        "transport_budget_share": transport_budget_share(window),
        "long_term_share": long_term_share(window),
    }


def _run_one_trajectory(config: Config, label: str, seed: int) -> list[dict]:
    """Steps one model to HORIZON, recording every checkpoint window, the measurement blocks
    that would follow each checkpoint (needed regardless of which one is eventually accepted,
    since the acceptance decision is made in post-processing here, not during stepping), and
    the long reference window -- all from one continuous trajectory."""
    run_cfg = replace(config, seed=seed, n_steps=HORIZON)
    model = CityModel(run_cfg)
    rows = []
    checkpoint_set = set(CHECKPOINTS)
    measurement_ends = {c + MEASUREMENT_BLOCK for c in CHECKPOINTS}
    for step_idx in range(1, HORIZON + 1):
        model.step()
        if step_idx in checkpoint_set:
            history = pd.DataFrame(model.history)
            row = _history_window_moments(
                history, step_idx - DETECTION_WINDOW + 1, step_idx, run_cfg.n_agents
            )
            row["distance_gradient_slope"] = distance_gradient_slope(model)
            rows.append(
                {"label": label, "seed": seed, "kind": "checkpoint", "step": step_idx, **row}
            )
        if step_idx in measurement_ends:
            checkpoint = step_idx - MEASUREMENT_BLOCK
            history = pd.DataFrame(model.history)
            row = _history_window_moments(history, checkpoint + 1, step_idx, run_cfg.n_agents)
            row["distance_gradient_slope"] = distance_gradient_slope(model)
            rows.append(
                {
                    "label": label,
                    "seed": seed,
                    "kind": "measurement_block",
                    "step": checkpoint,
                    **row,
                }
            )
    history = pd.DataFrame(model.history)
    ref_row = _history_window_moments(history, *REFERENCE_WINDOW, run_cfg.n_agents)
    ref_row["distance_gradient_slope"] = distance_gradient_slope(model)
    rows.append({"label": label, "seed": seed, "kind": "reference", "step": HORIZON, **ref_row})
    return rows


def apply_stopping_rule(
    checkpoint_df: pd.DataFrame, thresholds: dict[str, float], moment_keys: list[str]
) -> dict[str, dict]:
    """Applies the prespecified convergence rule to already-simulated checkpoint data,
    per label, averaging each checkpoint's window across seeds first (matching how a real
    evaluation averages `calibration_seeds`) before comparing consecutive checkpoints."""
    decisions = {}
    for label, group in checkpoint_df.groupby("label"):
        by_checkpoint = group.groupby("step")[moment_keys].mean().sort_index()
        steps = by_checkpoint.index.tolist()
        consecutive_ok = 0
        accepted_at = None
        for i in range(1, len(steps)):
            deltas = (by_checkpoint.loc[steps[i]] - by_checkpoint.loc[steps[i - 1]]).abs()
            within = all(deltas[k] <= thresholds[k] for k in moment_keys)
            consecutive_ok = consecutive_ok + 1 if within else 0
            if consecutive_ok >= 2:
                accepted_at = steps[i]
                break
        decisions[label] = {
            "accepted_at": accepted_at,
            "resolved": accepted_at is not None,
            "steps_checked": steps,
        }
    return decisions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Adaptive burn-in validation pilot")
    parser.add_argument("--config", required=True)
    parser.add_argument("--params", default=None)
    parser.add_argument(
        "--precision-csv",
        required=True,
        help="precision_decomposition.csv from scripts.assess_identification, settled window",
    )
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    base_config = Config.from_yaml(args.config)
    if args.params:
        overrides = json.loads(Path(args.params).read_text(encoding="utf-8"))["params"]
        base_config = replace(base_config, **overrides)

    precision = pd.read_csv(args.precision_csv)
    settled = precision[precision["label"] == "settled_2251-2400"].set_index("moment")
    thresholds = settled["sim_var_of_mean"].pow(0.5).to_dict()
    moment_keys = list(thresholds.keys())

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    jobs = [
        (label, replace(base_config, **overrides), seed)
        for label, overrides in CANDIDATES.items()
        for seed in CALIBRATION_SEEDS
    ]

    start = time.perf_counter()
    results = Parallel(n_jobs=N_JOBS, backend="loky")(
        delayed(_run_one_trajectory)(cfg, label, seed) for label, cfg, seed in jobs
    )
    elapsed = time.perf_counter() - start

    all_rows = [row for trajectory in results for row in trajectory]
    full = pd.DataFrame(all_rows)
    full.to_csv(out_dir / "trajectories.csv", index=False)

    checkpoint_rows = full[full["kind"] == "checkpoint"]
    decisions = apply_stopping_rule(checkpoint_rows, thresholds, moment_keys)

    measurement = full[full["kind"] == "measurement_block"]
    reference = full[full["kind"] == "reference"].groupby("label")[moment_keys].mean()

    validation_rows = []
    for label, decision in decisions.items():
        row = {"label": label, **decision}
        if decision["resolved"]:
            reported = measurement[
                (measurement["label"] == label) & (measurement["step"] == decision["accepted_at"])
            ][moment_keys].mean()
            for k in moment_keys:
                row[f"reported_{k}"] = reported[k]
                row[f"reference_{k}"] = reference.loc[label, k]
                row[f"bias_{k}"] = reported[k] - reference.loc[label, k]
        else:
            for k in moment_keys:
                row[f"reported_{k}"] = None
                row[f"reference_{k}"] = reference.loc[label, k]
                row[f"bias_{k}"] = None
        validation_rows.append(row)
    validation = pd.DataFrame(validation_rows)
    validation.to_csv(out_dir / "validation.csv", index=False)

    manifest = {
        "command": "python -m scripts.adaptive_burn_in_pilot " + " ".join(sys.argv[1:]),
        "detection_window": DETECTION_WINDOW,
        "checkpoints": CHECKPOINTS,
        "computational_limit": COMPUTATIONAL_LIMIT,
        "measurement_block": MEASUREMENT_BLOCK,
        "reference_window": REFERENCE_WINDOW,
        "horizon": HORIZON,
        "thresholds": thresholds,
        "candidates": CANDIDATES,
        "n_seeds_per_candidate": len(CALIBRATION_SEEDS),
        "n_jobs": N_JOBS,
        "wall_clock_seconds": elapsed,
        "code_fingerprint": _source_fingerprint(),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"wrote {out_dir}, wall clock {elapsed:.1f}s")
    print(validation.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
