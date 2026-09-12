"""Bounded pre-calibration assessment of the provisional 2,250-step burn-in.

Aakash chose burn-in = 2,250 steps (the conservative option `scripts/diagnose_window_stability.py`
laid out) as provisional, not locked, and asked for four checks before any recalibration runs:

1. Initial-condition differences measured against the moments' own accuracy requirements (their
   `data/moments.csv` standard errors), not merely the range across three seeds.
2. Whether `distance_gradient_slope`'s simulation precision is adequate.
3. Sensitivity/identification of the three remaining estimated parameters (`search_cost_per_trip`,
   `firm_radius`, `firm_kappa`) in the settled regime.
4. A justified post-burn-in window length, compared against a later window.

This calls `src.moments.compute_moments` through `src.runner.run_moments_many` -- the exact
calibration pipeline, not a reimplementation -- for every check, so nothing here can silently
diverge from what a real calibration run would compute. `scripts/diagnose_window_stability.py`
handles the separate, complementary question of whether plausible settings of the three
parameters change how long convergence takes (its `--vary-param` option); this script assumes a
fixed horizon and asks whether the fit there is already adequate.

Seeds: a fresh block (3001+), disjoint from CALIBRATION_SEEDS (1-15), VALIDATION_SEEDS
(1001-1050) and WEIGHT_SEEDS (2001-2050) -- this is a diagnostic, not part of the estimator, and
must not contaminate any seed set an eventual weight matrix or reported fit would use.

Usage:
    python -m scripts.assess_settled_regime \
        --config configs/baseline.yaml --params results/published/calibration_result.json \
        --output-dir results/review_v2/settled_regime

Outputs, under --output-dir:
    replicate_seeds.csv          one row per (window_label, seed): all four moments, transient
                                  vs settled window, same 50 seeds
    parameter_sensitivity.csv    one row per (param, value, seed): all four moments at the
                                  settled window
    window_length_comparison.csv one row per (window_label, seed): all four moments at several
                                  post-burn-in window lengths and a later window
    manifest.json
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

from scripts.diagnose_horizon import _source_fingerprint  # noqa: E402
from src.calibrate import MOMENT_KEYS  # noqa: E402
from src.config import Config  # noqa: E402
from src.runner import run_moments_many  # noqa: E402

REPLICATE_SEEDS: tuple[int, ...] = tuple(range(3001, 3051))  # 50 seeds
SENSITIVITY_SEEDS: tuple[int, ...] = tuple(range(3001, 3009))  # 8 seeds
WINDOW_SEEDS: tuple[int, ...] = tuple(range(3001, 3016))  # 15 seeds, matches CALIBRATION_SEEDS

PROVISIONAL_BURN_IN = 2250
PUBLISHED_BURN_IN = 50
PUBLISHED_N_STEPS = 150

# Bound endpoints and the fitted value -- same spread scripts/diagnose_window_stability.py's
# --vary-param convergence-speed campaigns used, for a like-for-like comparison.
PARAM_VALUES: dict[str, tuple[float, float, float]] = {
    "search_cost_per_trip": (0.0015, 0.0025146203001423, 0.006),
    "firm_radius": (1.0, 1.641069983236403, 4.0),
    "firm_kappa": (0.2, 0.22393789239458572, 2.0),
}


def _moments_rows(config: Config, seeds: tuple[int, ...], label: str, **extra: float) -> list[dict]:
    per_seed = run_moments_many(config, list(seeds))
    rows = []
    for seed, moments in zip(seeds, per_seed, strict=True):
        row = {"label": label, "seed": seed, **extra, **{k: moments[k] for k in MOMENT_KEYS}}
        rows.append(row)
    return rows


def assess_replicate_noise(base_config: Config) -> pd.DataFrame:
    transient = replace(base_config, burn_in_steps=PUBLISHED_BURN_IN, n_steps=PUBLISHED_N_STEPS)
    settled = replace(
        base_config,
        burn_in_steps=PROVISIONAL_BURN_IN,
        n_steps=PROVISIONAL_BURN_IN + PUBLISHED_N_STEPS,
    )
    rows = _moments_rows(transient, REPLICATE_SEEDS, "transient_51-150")
    rows += _moments_rows(settled, REPLICATE_SEEDS, "settled_2251-2400")
    return pd.DataFrame(rows)


def assess_parameter_sensitivity(base_config: Config) -> pd.DataFrame:
    settled = replace(
        base_config,
        burn_in_steps=PROVISIONAL_BURN_IN,
        n_steps=PROVISIONAL_BURN_IN + PUBLISHED_N_STEPS,
    )
    rows = []
    for param, values in PARAM_VALUES.items():
        for value in values:
            cfg = replace(settled, **{param: value})
            rows += _moments_rows(cfg, SENSITIVITY_SEEDS, param, value=value)
    return pd.DataFrame(rows)


def assess_window_length(base_config: Config) -> pd.DataFrame:
    windows = {
        "settled_150": (PROVISIONAL_BURN_IN, PROVISIONAL_BURN_IN + 150),
        "settled_300": (PROVISIONAL_BURN_IN, PROVISIONAL_BURN_IN + 300),
        "settled_600": (PROVISIONAL_BURN_IN, PROVISIONAL_BURN_IN + 600),
        "later_150": (2 * PROVISIONAL_BURN_IN, 2 * PROVISIONAL_BURN_IN + 150),
    }
    rows = []
    for label, (burn_in, n_steps) in windows.items():
        cfg = replace(base_config, burn_in_steps=burn_in, n_steps=n_steps)
        rows += _moments_rows(cfg, WINDOW_SEEDS, label, window_length=n_steps - burn_in)
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded pre-calibration settled-regime checks")
    parser.add_argument("--config", required=True)
    parser.add_argument("--params", default=None)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    base_config = Config.from_yaml(args.config)
    if args.params:
        overrides = json.loads(Path(args.params).read_text(encoding="utf-8"))["params"]
        base_config = replace(base_config, **overrides)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    replicate = assess_replicate_noise(base_config)
    replicate.to_csv(out_dir / "replicate_seeds.csv", index=False)

    sensitivity = assess_parameter_sensitivity(base_config)
    sensitivity.to_csv(out_dir / "parameter_sensitivity.csv", index=False)

    window_length = assess_window_length(base_config)
    window_length.to_csv(out_dir / "window_length_comparison.csv", index=False)

    manifest = {
        "command": "python -m scripts.assess_settled_regime " + " ".join(sys.argv[1:]),
        "config_path": args.config,
        "params_path": args.params,
        "provisional_burn_in": PROVISIONAL_BURN_IN,
        "replicate_seeds": list(REPLICATE_SEEDS),
        "sensitivity_seeds": list(SENSITIVITY_SEEDS),
        "window_seeds": list(WINDOW_SEEDS),
        "param_values": PARAM_VALUES,
        "code_fingerprint": _source_fingerprint(),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
