"""Corrects two things in the settled-regime assessment (results/review_v2/settled_regime/):

1. The distance_gradient_slope precision comparison used an ad hoc ratio (this script's own
   replicate-seed standard deviation against `moments.csv`'s standard_error) instead of the
   estimator's own approved construction: `combined_cov = data_cov + sim_cov / len
   (calibration_seeds)`, built from `src.calibrate._data_covariance` and
   `src.calibrate._simulate_moment_matrix` exactly as `calibrate.py`'s real weight-matrix build
   does (`WEIGHT_SEEDS`, not an ad hoc block) -- the same functions, not a reimplementation.

2. The parameter-sensitivity table showed each of the three remaining parameters' one-at-a-time
   effect on the raw moments across their full bound range, and called `firm_radius` "weakly
   identified" and `firm_kappa` "strongly identified" on that basis. That is sensitivity, not
   identification -- calibrate.py's own docstring already warns that a weight's magnitude "is
   not itself evidence the moment is unidentified", and a wide bound-to-bound sweep can hide
   nonlinearities a local check would catch. Local identification is instead assessed by the
   rank/conditioning of J'WJ, where J is the *local* Jacobian of the moment vector at the fitted
   point (central differences, common random numbers = CALIBRATION_SEEDS, matching what the
   loss function actually averages over) and W is the settled-window weight matrix from (1).

Usage:
    python -m scripts.assess_identification \
        --config configs/baseline.yaml --params results/published/calibration_result.json \
        --output-dir results/review_v2/settled_regime
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.diagnose_horizon import _source_fingerprint  # noqa: E402
from src.calibrate import (  # noqa: E402
    CALIBRATION_SEEDS,
    DEFAULT_BOUNDS,
    MOMENT_KEYS,
    WEIGHT_SEEDS,
    _data_covariance,
    _simulate_moment_matrix,
    _weights_from_covariance,
    load_empirical_moments,
)
from src.config import Config  # noqa: E402
from src.runner import run_moments_many  # noqa: E402

PROVISIONAL_BURN_IN = 2250
PUBLISHED_BURN_IN = 50
PUBLISHED_N_STEPS = 150

REMAINING_PARAMS = ("search_cost_per_trip", "firm_radius", "firm_kappa")
RELATIVE_STEP = 0.05  # 5% of the fitted value, central difference


def _window_config(base: Config, burn_in: int, window_length: int) -> Config:
    """`n_steps` is burn_in + window_length -- correct for a window measured *after* burn-in
    ends (the settled-window convention this project uses throughout). It is NOT correct for
    the published transient window, whose own `n_steps` (150) already includes its 50-step
    burn-in: that window is steps 51-150, a 100-step window, not a 150-step one starting at 51.
    An earlier version of this function was reused for both cases and silently computed the
    transient reference over steps 51-200 instead -- see DECISIONS_PENDING.md's correction."""
    return replace(base, burn_in_steps=burn_in, n_steps=burn_in + window_length)


def build_combined_cov(config: Config) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (data_cov, sim_cov_of_the_mean, combined_cov), all 4x4, diagonal-only for
    data_cov but full for the other two -- exactly calibrate.py's own build_weights formula,
    called on `config`'s own window rather than reconstructing it."""
    empirical = load_empirical_moments()
    data_cov = _data_covariance(empirical)
    sim_matrix = _simulate_moment_matrix(config, {}, WEIGHT_SEEDS)
    sim_cov = np.cov(sim_matrix, rowvar=False, ddof=1)
    sim_cov_of_mean = sim_cov / len(CALIBRATION_SEEDS)
    combined_cov = data_cov + sim_cov_of_mean
    return data_cov, sim_cov_of_mean, combined_cov


def assess_precision_decomposition(base_config: Config) -> pd.DataFrame:
    # The published transient window is exactly configs/baseline.yaml's own (burn_in_steps=50,
    # n_steps=150) -- steps 51-150, a 100-step window -- passed straight through, not built
    # from _window_config's burn_in-plus-length convention (see that function's docstring).
    transient_cfg = replace(base_config, burn_in_steps=PUBLISHED_BURN_IN, n_steps=PUBLISHED_N_STEPS)
    settled_cfg = _window_config(base_config, PROVISIONAL_BURN_IN, PUBLISHED_N_STEPS)
    rows = []
    for label, cfg in (("transient_51-150", transient_cfg), ("settled_2251-2400", settled_cfg)):
        data_cov, sim_cov_of_mean, combined_cov = build_combined_cov(cfg)
        for i, key in enumerate(MOMENT_KEYS):
            rows.append(
                {
                    "label": label,
                    "moment": key,
                    "data_var": data_cov[i, i],
                    "sim_var_of_mean": sim_cov_of_mean[i, i],
                    "combined_var": combined_cov[i, i],
                    "data_se": np.sqrt(data_cov[i, i]),
                    "combined_se": np.sqrt(combined_cov[i, i]),
                    "sim_share_of_combined_variance": sim_cov_of_mean[i, i] / combined_cov[i, i],
                    "combined_se_over_data_se": np.sqrt(combined_cov[i, i] / data_cov[i, i]),
                }
            )
    return pd.DataFrame(rows)


def _mean_moments(config: Config, seeds: tuple[int, ...]) -> np.ndarray:
    per_seed = run_moments_many(config, list(seeds))
    return np.array([np.mean([m[k] for m in per_seed]) for k in MOMENT_KEYS])


def local_jacobian(
    base_config: Config,
    fitted_params: dict[str, float],
    seeds: tuple[int, ...],
    relative_step: float = RELATIVE_STEP,
) -> tuple[np.ndarray, dict[str, tuple[float, float]]]:
    """Central-difference Jacobian of the 4-moment vector w.r.t. the 3 remaining parameters, at
    the fitted point, common random numbers (`seeds`) shared across every evaluation so the
    finite difference isn't itself dominated by independent simulation noise at each point.
    `relative_step` is exposed (not hardcoded) so a robustness sweep can call this at several
    step sizes and check the result isn't an artefact of one particular choice."""
    steps: dict[str, tuple[float, float]] = {}
    columns = []
    for name in REMAINING_PARAMS:
        value = fitted_params[name]
        h = relative_step * value
        up_cfg = replace(base_config, **{name: value + h})
        down_cfg = replace(base_config, **{name: value - h})
        up = _mean_moments(up_cfg, seeds)
        down = _mean_moments(down_cfg, seeds)
        columns.append((up - down) / (2 * h))
        steps[name] = (value - h, value + h)
    jacobian = np.column_stack(columns)  # (4 moments, 3 params)
    return jacobian, steps


def _box_widths() -> np.ndarray:
    """Each remaining parameter's own calibration-bound width -- the same box the LHS search
    samples uniformly within. Rescaling the Jacobian by this (not by the parameter's raw units)
    answers "how much does the moment move if this parameter traverses its own search box",
    which is comparable across parameters with different natural units and ranges; a raw,
    unscaled Jacobian is not, for the same reason calibrate.py's own docstring already warns a
    weight matrix's raw diagonal magnitude says nothing about identification."""
    return np.array(
        [DEFAULT_BOUNDS[name][1] - DEFAULT_BOUNDS[name][0] for name in REMAINING_PARAMS]
    )


def _condition_number(matrix: np.ndarray) -> tuple[np.ndarray, float]:
    eigenvalues = np.linalg.eigvalsh(matrix)
    condition_number = (
        float(eigenvalues[-1] / eigenvalues[0]) if eigenvalues[0] > 0 else float("inf")
    )
    return eigenvalues, condition_number


def assess_identification(base_config: Config, fitted_params: dict[str, float]) -> dict:
    settled_cfg = _window_config(base_config, PROVISIONAL_BURN_IN, PUBLISHED_N_STEPS)
    _, _, combined_cov = build_combined_cov(settled_cfg)
    weights = _weights_from_covariance(combined_cov, estimated_at_params={}, weight_seeds=())
    box_widths = _box_widths()

    robustness = {}
    for relative_step in (0.02, RELATIVE_STEP, 0.10):
        jacobian, steps = local_jacobian(
            settled_cfg, fitted_params, CALIBRATION_SEEDS, relative_step
        )
        raw_eigenvalues, raw_condition = _condition_number(
            jacobian.T @ weights.weight_matrix @ jacobian
        )
        rescaled_jacobian = jacobian * box_widths  # broadcasts over columns (one per parameter)
        rescaled_eigenvalues, rescaled_condition = _condition_number(
            rescaled_jacobian.T @ weights.weight_matrix @ rescaled_jacobian
        )
        robustness[relative_step] = {
            "raw_condition_number": raw_condition,
            "raw_eigenvalues": raw_eigenvalues.tolist(),
            "rescaled_condition_number": rescaled_condition,
            "rescaled_eigenvalues": rescaled_eigenvalues.tolist(),
            "steps": steps,
            "jacobian": jacobian.tolist(),
        }

    # The step used elsewhere in this module's reporting (RELATIVE_STEP) is the headline result;
    # the other two steps in `robustness` exist only to check it isn't an artefact of that choice.
    headline = robustness[RELATIVE_STEP]
    jacobian = np.array(headline["jacobian"])
    rescaled_jacobian = jacobian * box_widths
    info_matrix = jacobian.T @ weights.weight_matrix @ jacobian
    rescaled_info_matrix = rescaled_jacobian.T @ weights.weight_matrix @ rescaled_jacobian
    return {
        "params": REMAINING_PARAMS,
        "box_widths": box_widths.tolist(),
        "perturbation_steps": headline["steps"],
        "jacobian": jacobian.tolist(),
        "rescaled_jacobian": rescaled_jacobian.tolist(),
        "moment_keys": MOMENT_KEYS,
        "information_matrix": info_matrix.tolist(),
        "rescaled_information_matrix": rescaled_info_matrix.tolist(),
        "step_size_robustness": {str(k): v for k, v in robustness.items()},
        "eigenvalues": headline["raw_eigenvalues"],
        "condition_number": headline["raw_condition_number"],
        "rescaled_eigenvalues": headline["rescaled_eigenvalues"],
        "rescaled_condition_number": headline["rescaled_condition_number"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Precision decomposition and local identification")
    parser.add_argument("--config", required=True)
    parser.add_argument("--params", default=None)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    base_config = Config.from_yaml(args.config)
    fitted_params = {}
    if args.params:
        fitted_params = json.loads(Path(args.params).read_text(encoding="utf-8"))["params"]
        base_config = replace(base_config, **fitted_params)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    precision = assess_precision_decomposition(base_config)
    precision.to_csv(out_dir / "precision_decomposition.csv", index=False)

    identification = assess_identification(
        base_config, {k: fitted_params[k] for k in REMAINING_PARAMS}
    )
    (out_dir / "identification.json").write_text(
        json.dumps(identification, indent=2), encoding="utf-8"
    )

    manifest = {
        "command": "python -m scripts.assess_identification " + " ".join(sys.argv[1:]),
        "config_path": args.config,
        "params_path": args.params,
        "weight_seeds": list(WEIGHT_SEEDS),
        "calibration_seeds": list(CALIBRATION_SEEDS),
        "relative_step": RELATIVE_STEP,
        "code_fingerprint": _source_fingerprint(),
    }
    (out_dir / "identification_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print(f"wrote {out_dir}")
    print(precision.to_string(index=False))
    print("raw condition number:", identification["condition_number"])
    print("rescaled (box-width) condition number:", identification["rescaled_condition_number"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
