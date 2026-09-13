"""Validation pilot for a staged, bounded adaptive burn-in -- corrected rule, second pass.

The first pilot's rule (two consecutive checkpoints with a small absolute step) failed: the fast
(fitted) candidate never accepted within the 9,000-step limit (blocked by
`distance_gradient_slope`'s own per-checkpoint noise), while every slow `firm_kappa` candidate
accepted at the earliest possible checkpoint, reporting values 5-6x too low. A revised rule
(three consecutive passes, raw absolute step required to be non-increasing) was independently
checked by Astra, exactly as specified, against the *same, already-collected* checkpoint data:
**it accepts none of the four candidates, including the fitted one, through step 9,000** --
re-verified here (an earlier draft of this docstring wrongly claimed the `firm_kappa` candidates
accepted at step 2,250; that claim only checked the threshold half of the rule, not the
non-increasing half combined with it, and was wrong). Diagnosis of why the combined rule is
simply too strict to ever fire: a non-overlapping 450-step window's raw checkpoint-to-checkpoint
difference has no reason to shrink monotonically just because the process has converged --
successive differences of an already-flat, noisy series are themselves noisy, not decreasing, so
requiring three of them in a row to be non-increasing is a near-impossible bar even when the true
process is flat.

## The corrected rule: a local trend test, not a raw-step test

At each checkpoint, for each of the three stopping-decision moments (`distance_gradient_slope`
is excluded from the *decision* -- see below), fit an ordinary-least-squares slope of the
moment's value against step index over the last `TREND_WINDOW` checkpoints, and test it against
zero using that moment's own known simulation standard error (`results/review_v2/
settled_regime/precision_decomposition.csv`'s settled-window `sim_var_of_mean`) rather than the
regression's own (very noisy, only `TREND_WINDOW` points) residual variance -- the true
per-checkpoint noise is known externally from the 15-seed simulation-covariance work, and using
it directly gives a properly powered test instead of one starved of degrees of freedom.
Convergence is accepted once this joint (all three moments) flatness test passes for
`CONSECUTIVE_PASSES_REQUIRED` consecutive checkpoints in a row -- verified directly against the
first pilot's own checkpoint data before any new simulation was run (development discipline,
not re-collection): the fitted candidate now accepts at step 4,500, and none of the three
`firm_kappa` candidates (0.9, 1.4, 2.0) accepts by step 9,000, matching what the horizon
extension campaigns independently already showed about how far those points are from settled.

**Disclosure: step 4,500 is this rule's mechanical earliest-possible acceptance point, not an
empirical finding about the fitted candidate specifically.** `TREND_WINDOW`=4 means the first
testable trend estimate needs checkpoints 900/1350/1800/2250; `CONSECUTIVE_PASSES_REQUIRED`=3
means three such estimates must pass in a row, i.e. the ones ending at 2250, 3150 and 4500 --
so no candidate, however fast it truly settles, could ever be accepted before checkpoint 4,500
under these parameters. That the fitted candidate accepts at exactly that floor is consistent
with fast convergence, but does not by itself demonstrate it; a genuinely still-noisy or slower
process would simply fail to reach three consecutive passes and stay unresolved, which is what
happened for all three `firm_kappa` candidates. This method's known open problem (not yet
resolved -- see the specification's discussion of test power) is that failing to reject a flat
trend is not the same as confirming one: at low degrees of freedom the test can lack the power to
detect a real, ongoing drift, so an early acceptance should be read as "not contradicted by this
test" rather than "proven flat."

## Validation now covers what the stopping decision excludes

`distance_gradient_slope` never drives the stopping decision (its own per-checkpoint noise is
structurally unsuited to a trend test at only 15 seeds -- see the settled-regime assessment for
why its *calibration* precision is fine regardless, at the full 15-seed average). It is still
computed, recorded and validated at every checkpoint and in the final report. The capital
distribution -- both the whole-population and non-employed-only mean and quantiles
(`scripts/diagnose_window_stability.py`'s `_capital_quantile_row`, reused rather than
reimplemented) -- is added for the same reason: excluding a quantity from what decides when to
stop must not exempt it from being checked against the long-run reference.

## Cost of this pass

The first pilot's `trajectories.csv` records only the four calibration moments -- no capital
diagnostics were collected. Adding them requires re-simulating every (candidate, seed) pair from
scratch (this script steps `CityModel` directly rather than going through the cached
`run_moments_many` pipeline, so nothing here is cache-eligible); the added per-checkpoint
capital-quantile computation itself is cheap (rank statistics over 500 agents). Same candidates,
same `CALIBRATION_SEEDS` -- this is still the *development* pass, not held-out validation.

Usage:
    python -m scripts.adaptive_burn_in_pilot \
        --config configs/baseline.yaml --params results/published/calibration_result.json \
        --precision-csv results/review_v2/settled_regime/precision_decomposition.csv \
        --output-dir results/review_v2/settled_regime/adaptive_pilot_v2
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.diagnose_horizon import _source_fingerprint  # noqa: E402
from scripts.diagnose_window_stability import _capital_quantile_row  # noqa: E402
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

STOPPING_MOMENTS = ("discouraged_share", "transport_budget_share", "long_term_share")
VALIDATED_ONLY_KEYS = (
    "distance_gradient_slope",
    "capital_non_employed_mean",
    "capital_non_employed_q50",
    "capital_all_mean",
    "capital_all_q50",
)

TREND_WINDOW = 4  # checkpoints used in each local OLS trend fit
Z_CRITICAL = 1.645  # one-sided 95% -- "not distinguishable from a flat trend"
CONSECUTIVE_PASSES_REQUIRED = 3

CANDIDATES: dict[str, dict[str, float]] = {
    "fitted": {},
    "firm_kappa_0.9": {"firm_kappa": 0.9},
    "firm_kappa_1.4": {"firm_kappa": 1.4},
    "firm_kappa_2.0": {"firm_kappa": 2.0},
}


def _window_row(history: pd.DataFrame, model: CityModel, lo: int, hi: int, n_agents: int) -> dict:
    window = history[(history["step"] >= lo) & (history["step"] <= hi)]
    row = {
        "discouraged_share": discouraged_share(window, n_agents),
        "transport_budget_share": transport_budget_share(window),
        "long_term_share": long_term_share(window),
        "distance_gradient_slope": distance_gradient_slope(model),
    }
    row.update(_capital_quantile_row(model))
    return row


def _run_one_trajectory(config: Config, label: str, seed: int) -> list[dict]:
    """Steps one model to HORIZON, recording every checkpoint window, the measurement block
    that would follow each checkpoint, and the long reference window -- all from one continuous
    trajectory, now including the capital-distribution diagnostics the first pass omitted."""
    run_cfg = replace(config, seed=seed, n_steps=HORIZON)
    model = CityModel(run_cfg)
    rows = []
    checkpoint_set = set(CHECKPOINTS)
    measurement_ends = {c + MEASUREMENT_BLOCK for c in CHECKPOINTS}
    for step_idx in range(1, HORIZON + 1):
        model.step()
        if step_idx in checkpoint_set:
            history = pd.DataFrame(model.history)
            row = _window_row(
                history, model, step_idx - DETECTION_WINDOW + 1, step_idx, run_cfg.n_agents
            )
            rows.append(
                {"label": label, "seed": seed, "kind": "checkpoint", "step": step_idx, **row}
            )
        if step_idx in measurement_ends:
            checkpoint = step_idx - MEASUREMENT_BLOCK
            history = pd.DataFrame(model.history)
            row = _window_row(history, model, checkpoint + 1, step_idx, run_cfg.n_agents)
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
    ref_row = _window_row(history, model, *REFERENCE_WINDOW, run_cfg.n_agents)
    rows.append({"label": label, "seed": seed, "kind": "reference", "step": HORIZON, **ref_row})
    return rows


def _trend_flat(
    by_checkpoint: pd.DataFrame, moment: str, end_idx: int, sigma: float
) -> tuple[float, float, bool]:
    """OLS slope of `moment` over the TREND_WINDOW checkpoints ending at `end_idx`, tested
    against zero using the moment's externally-known simulation SE (`sigma`) rather than the
    regression's own few-point residual variance."""
    window = by_checkpoint.iloc[end_idx - TREND_WINDOW + 1 : end_idx + 1]
    x = window.index.to_numpy(dtype=float) / 1000.0  # steps in thousands, numerical stability
    y = window[moment].to_numpy()
    x_bar = x.mean()
    s_xx = ((x - x_bar) ** 2).sum()
    b = ((x - x_bar) * (y - y.mean())).sum() / s_xx
    se_b = sigma / np.sqrt(s_xx)
    return b, se_b, abs(b) <= Z_CRITICAL * se_b


def apply_stopping_rule(
    checkpoint_df: pd.DataFrame, thresholds: dict[str, float]
) -> dict[str, dict]:
    """The corrected rule: three consecutive checkpoints at which every stopping-decision
    moment's local trend is statistically indistinguishable from flat. `thresholds` maps each
    stopping moment to its simulation standard error at 15 seeds."""
    decisions = {}
    for label, group in checkpoint_df.groupby("label"):
        by_checkpoint = group.groupby("step")[list(STOPPING_MOMENTS)].mean().sort_index()
        steps = by_checkpoint.index.tolist()
        streak = 0
        accepted_at = None
        for end_idx in range(TREND_WINDOW - 1, len(steps)):
            joint = all(
                _trend_flat(by_checkpoint, m, end_idx, thresholds[m])[2] for m in STOPPING_MOMENTS
            )
            streak = streak + 1 if joint else 0
            if streak >= CONSECUTIVE_PASSES_REQUIRED:
                accepted_at = steps[end_idx]
                break
        decisions[label] = {
            "accepted_at": accepted_at,
            "resolved": accepted_at is not None,
            "steps_checked": steps,
        }
    return decisions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Adaptive burn-in validation pilot, corrected rule"
    )
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
    all_thresholds = settled["sim_var_of_mean"].pow(0.5).to_dict()
    thresholds = {m: all_thresholds[m] for m in STOPPING_MOMENTS}

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
    decisions = apply_stopping_rule(checkpoint_rows, thresholds)

    validated_keys = [*STOPPING_MOMENTS, *VALIDATED_ONLY_KEYS]
    measurement = full[full["kind"] == "measurement_block"]
    reference = full[full["kind"] == "reference"].groupby("label")[validated_keys].mean()

    validation_rows = []
    for label, decision in decisions.items():
        row = {"label": label, **decision}
        if decision["resolved"]:
            reported = measurement[
                (measurement["label"] == label) & (measurement["step"] == decision["accepted_at"])
            ][validated_keys].mean()
            for k in validated_keys:
                row[f"reported_{k}"] = reported[k]
                row[f"reference_{k}"] = reference.loc[label, k]
                row[f"bias_{k}"] = reported[k] - reference.loc[label, k]
        else:
            for k in validated_keys:
                row[f"reported_{k}"] = None
                row[f"reference_{k}"] = reference.loc[label, k]
                row[f"bias_{k}"] = None
        validation_rows.append(row)
    validation = pd.DataFrame(validation_rows)
    validation.to_csv(out_dir / "validation.csv", index=False)

    manifest = {
        "command": "python -m scripts.adaptive_burn_in_pilot " + " ".join(sys.argv[1:]),
        "rule_version": 2,
        "detection_window": DETECTION_WINDOW,
        "checkpoints": CHECKPOINTS,
        "computational_limit": COMPUTATIONAL_LIMIT,
        "measurement_block": MEASUREMENT_BLOCK,
        "reference_window": REFERENCE_WINDOW,
        "horizon": HORIZON,
        "trend_window": TREND_WINDOW,
        "z_critical": Z_CRITICAL,
        "consecutive_passes_required": CONSECUTIVE_PASSES_REQUIRED,
        "stopping_moments": STOPPING_MOMENTS,
        "validated_only_keys": VALIDATED_ONLY_KEYS,
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
