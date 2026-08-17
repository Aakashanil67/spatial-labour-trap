"""Method of simulated moments over the four free parameters -- search_cost_per_trip (c),
initial_search_capital (W0), firm_radius (rho), firm_kappa (kappa) -- against the four moments
in data/moments.csv (locked commitment 3). Exactly identified: four parameters, four moments,
no slack for a formal overidentification test -- the out-of-calibration validation against
Banerjee and Sequeira's null result is the actual substitute (see DECISIONS.md).

**The weight matrix is fixed for the whole of one search, not recomputed at each candidate.**
An earlier version of this module weighted each candidate's deviation by the inverse of (data
SE^2 + that candidate's own simulation variance) -- so a candidate landing in a noisier region
of parameter space got a smaller weight and therefore a cheaper loss for the same deviation,
purely because it was noisy. McFadden (1989) does support using fixed common random draws as
parameters change and folding simulation error into the estimator's uncertainty (p.1006), but
neither of those licenses recomputing a diagonal inverse-variance weight from the candidate's
own noise at every evaluation. This module now builds one MSMWeights matrix ahead of a search
and holds it fixed throughout: a two-step procedure (W0 = data variance alone for a preliminary
search, W1 = data variance + simulation covariance estimated at the preliminary optimum for the
final search), matching McFadden's decomposition without re-opening the discount-noisy-
candidates hole. See DECISIONS.md, "The MSM weight matrix was quietly rewarding noisy
candidates, not just missing a simulation-variance term."

Common random numbers (D12): CALIBRATION_SEEDS is reused at every evaluation during both the
Latin hypercube and Nelder-Mead stages, so the loss is a deterministic function of the
parameters -- Nelder-Mead has no defence against a noisy objective otherwise. Three restarts
from the three best distinct LHS points, under the same seeds and the same fixed weight matrix,
guard against a single unlucky simplex; a calibration where no restart converges raises rather
than silently returning a non-answer. VALIDATION_SEEDS (disjoint) is used only once, at the
reported optimum, so the fit quality isn't measured on the seeds the optimiser fitted to.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import qmc

from src.config import CALIBRATION_SEEDS, VALIDATION_SEEDS, Config
from src.runner import run_moments_many

PARAM_NAMES: tuple[str, ...] = (
    "search_cost_per_trip",
    "initial_search_capital",
    "firm_radius",
    "firm_kappa",
)

# The second-stage simulation-covariance estimate (W1) is drawn from its own fixed seed set,
# disjoint from CALIBRATION_SEEDS (1-15) and VALIDATION_SEEDS (1001-1050): reusing either would
# let the weight matrix leak information from the search seeds into itself, or contaminate the
# seeds the final fit quality is reported on.
WEIGHT_SEEDS: tuple[int, ...] = tuple(range(2001, 2051))  # 50 seeds

# Wide enough to let the optimiser move, centred on baseline.yaml's own already-validated
# values, not picked from nothing -- see configs/baseline.yaml for what those are.
#
# firm_radius's upper bound is 2 * baseline.yaml's cbd_radius (2.0) = 4.0, not 6.0: with
# belief_multiplier=1, search tickets and firms are both drawn uniformly within a disk of
# radius cbd_radius, so no ticket-firm pair can ever be more than 2*cbd_radius apart. A bound
# past that diameter makes every firm reachable from every ticket regardless of firm_radius's
# exact value -- the loss stops responding to it entirely, which is exactly what the audit
# found: firm_radius=4.1 and 6.0 produced identical histories at the reported calibrated
# values. See DECISIONS.md, "The search-position draw oversampled the CBD centre, and it
# explains the flat firm_radius calibration region."
DEFAULT_BOUNDS: dict[str, tuple[float, float]] = {
    "search_cost_per_trip": (0.005, 0.05),
    "initial_search_capital": (0.2, 1.5),
    "firm_radius": (1.0, 4.0),
    "firm_kappa": (0.2, 2.0),
}

# A calibrated estimate this close to a bound (as a fraction of the bound's own magnitude) is
# reported as boundary-adjacent and weakly identified, not treated as a genuine interior
# optimum merely because its floating-point value happens to sit inside the box.
_BOUNDARY_ADJACENCY_FRACTION = 0.01

MOMENT_KEYS: tuple[str, ...] = (
    "distance_gradient_slope",
    "discouraged_share",
    "transport_budget_share",
    "long_term_share",
)

# The LHS design's own randomness (which points get sampled), not the model's RNG -- fixed so
# the coarse sweep itself is reproducible run to run, same reasoning as CALIBRATION_SEEDS.
_LHS_SEED = 0


@dataclass(frozen=True)
class EmpiricalMoments:
    values: dict[str, float]
    standard_errors: dict[str, float]


def load_empirical_moments(path: str = "data/moments.csv") -> EmpiricalMoments:
    """Loads the four calibration targets. Refuses to calibrate against a still-provisional
    moment (D7: the moment set freezes at the start of Week 4, and Week 4 is exactly where
    this function gets called) -- silently calibrating to a placeholder would be worse than
    refusing to run at all."""
    df = pd.read_csv(path)
    missing = set(MOMENT_KEYS) - set(df["key"])
    if missing:
        raise ValueError(f"{path} is missing required moment(s): {sorted(missing)}")
    df = df[df["key"].isin(MOMENT_KEYS)]
    duplicated = sorted(df.loc[df["key"].duplicated(), "key"].unique().tolist())
    if duplicated:
        raise ValueError(f"{path} has duplicate rows for moment(s): {duplicated}")
    if df["provisional"].any():
        still_provisional = df.loc[df["provisional"], "key"].tolist()
        raise ValueError(
            f"cannot calibrate: {still_provisional} still provisional in {path} -- "
            "see D7 in DECISIONS.md."
        )
    if df["value"].isna().any() or df["standard_error"].isna().any():
        raise ValueError(f"{path} has a null value or standard_error for a required moment.")
    if not np.isfinite(df["value"]).all() or not np.isfinite(df["standard_error"]).all():
        raise ValueError(f"{path} has a non-finite value or standard_error.")
    if (df["standard_error"] <= 0).any():
        non_positive = df.loc[df["standard_error"] <= 0, "key"].tolist()
        raise ValueError(f"{path} has a non-positive standard_error for {non_positive}.")
    values = dict(zip(df["key"], df["value"], strict=True))
    ses = dict(zip(df["key"], df["standard_error"], strict=True))
    return EmpiricalMoments(values=values, standard_errors=ses)


def _config_with_params(base: Config, params: dict[str, float]) -> Config:
    return replace(base, **params)


def simulate_moments(
    base: Config, params: dict[str, float], seeds: tuple[int, ...]
) -> dict[str, tuple[float, float]]:
    """Runs `base` with `params` overridden at every seed in `seeds`, returning
    {moment_key: (mean, variance_of_the_mean)} across seeds. The variance is of the *mean*
    estimator (per-seed variance divided by the seed count), matching what McFadden's
    simulation-variance term actually measures -- not the raw spread across seeds."""
    cfg = _config_with_params(base, params)
    per_seed = run_moments_many(cfg, list(seeds))
    result: dict[str, tuple[float, float]] = {}
    for key in MOMENT_KEYS:
        draws = np.array([m[key] for m in per_seed], dtype=float)
        if np.isnan(draws).any():
            # distance_gradient_slope returns nan in a degenerate spatial config -- propagate
            # rather than silently drop, since a nan moment means this parameter point can't
            # be scored at all, not that it scores zero.
            result[key] = (float("nan"), float("nan"))
            continue
        n = len(draws)
        variance_of_mean = draws.var(ddof=1) / n if n > 1 else float("inf")
        result[key] = (float(draws.mean()), float(variance_of_mean))
    return result


def _simulate_moment_matrix(
    base: Config, params: dict[str, float], seeds: tuple[int, ...]
) -> np.ndarray:
    """Raw per-seed moments as an (n_seeds, 4) matrix, ordered by MOMENT_KEYS -- the input a
    genuine simulation *covariance* estimate needs (np.cov), as opposed to simulate_moments'
    per-moment variance-only summary."""
    cfg = _config_with_params(base, params)
    per_seed = run_moments_many(cfg, list(seeds))
    return np.array([[m[key] for key in MOMENT_KEYS] for m in per_seed], dtype=float)


@dataclass(frozen=True)
class MSMWeights:
    """A weight matrix fixed for the duration of one search stage. `estimated_at_params` and
    `weight_seeds` record where the simulation-covariance component (if any) came from, so a
    reader can tell a W0 (data variance only, no simulation component yet estimated) from a W1
    (data + simulation covariance, estimated at a specific point) without re-deriving it."""

    moment_keys: tuple[str, ...]
    weight_matrix: np.ndarray
    estimated_at_params: dict[str, float]
    weight_seeds: tuple[int, ...]
    ridge: float = 0.0  # documented numerical ridge added if the covariance sum was rank-deficient


def quadratic_loss(deviations: np.ndarray, weight_matrix: np.ndarray) -> float:
    """g.T @ W @ g -- the pure MSM quadratic form, independent of how W or g were built."""
    return float(deviations @ weight_matrix @ deviations)


def _data_covariance(empirical: EmpiricalMoments) -> np.ndarray:
    """Diagonal S_data from the empirical standard errors. Off-diagonal entries are zero:
    discouraged_share and long_term_share are both QLFS-derived, but come from separate
    notebooks (01, 03) with independent bootstraps that never estimated their joint sampling
    covariance -- zero is documented here as "not estimated," not silently assumed to be the
    right answer, per Task 6's instruction to use a full empirical covariance block only where
    one has actually been estimated."""
    variances = np.array([empirical.standard_errors[key] ** 2 for key in MOMENT_KEYS])
    return np.diag(variances)


def _pinv_with_ridge(covariance: np.ndarray) -> tuple[np.ndarray, float]:
    """pinv of `covariance`, adding a documented ridge scaled to the matrix trace only if
    `covariance` is rank-deficient -- never an arbitrary constant hidden inside the inverse
    call. Returns (weight_matrix, ridge_used) so the exact value can be stored, not just
    applied."""
    rank = np.linalg.matrix_rank(covariance)
    if rank < covariance.shape[0]:
        ridge = 1e-8 * float(np.trace(covariance))
        covariance = covariance + ridge * np.eye(covariance.shape[0])
    else:
        ridge = 0.0
    return np.linalg.pinv(covariance), ridge


def _weights_from_covariance(
    covariance: np.ndarray,
    estimated_at_params: dict[str, float],
    weight_seeds: tuple[int, ...],
) -> MSMWeights:
    weight_matrix, ridge = _pinv_with_ridge(covariance)
    return MSMWeights(
        moment_keys=MOMENT_KEYS,
        weight_matrix=weight_matrix,
        estimated_at_params=dict(estimated_at_params),
        weight_seeds=weight_seeds,
        ridge=ridge,
    )


def msm_loss(
    param_vector: np.ndarray,
    base: Config,
    empirical: EmpiricalMoments,
    weights: MSMWeights,
    seeds: tuple[int, ...] = CALIBRATION_SEEDS,
) -> float:
    """g.T @ W @ g against a `weights` matrix that's FIXED for the whole search -- see the
    module docstring for why a candidate-dependent weight (this module's earlier design) is
    wrong: it silently discounts a candidate's own deviation whenever that candidate happens to
    land in a noisier region, rather than only ever changing because the deviation itself
    changed. Simulation variance at a candidate is not read here at all; it only ever enters
    through the fixed `weights.weight_matrix` computed once, ahead of the search, by
    calibrate(). Returns inf for a parameter point that produces a nan moment (an infeasible or
    degenerate region of the parameter space), so the optimiser is steered away from it rather
    than crashing on it."""
    params = dict(zip(PARAM_NAMES, param_vector, strict=True))
    simulated = simulate_moments(base, params, seeds)

    deviations = np.empty(len(weights.moment_keys))
    for i, key in enumerate(weights.moment_keys):
        sim_mean, _sim_var = simulated[key]
        if np.isnan(sim_mean):
            return float("inf")
        deviations[i] = sim_mean - empirical.values[key]
    return quadratic_loss(deviations, weights.weight_matrix)


@dataclass(frozen=True)
class CalibrationResult:
    params: dict[str, float]
    loss_at_optimum: float
    lhs_best_loss: float  # the best loss found during the coarse (final-stage) sweep
    validation_moments: dict[str, tuple[float, float]]  # (mean, variance_of_mean), 50 seeds
    n_lhs_points: int
    n_nelder_mead_evaluations: int  # summed across every restart of the final stage
    # Parameter names whose calibrated value sits within _BOUNDARY_ADJACENCY_FRACTION of either
    # edge of its search box -- weakly identified, not a genuine interior optimum. Empty on a
    # clean run; a non-empty tuple is itself a finding, not something to round away.
    boundary_adjacent_params: tuple[str, ...] = ()
    # Optimiser status of the SELECTED (lowest-loss, converged) restart of the final stage.
    success: bool = True
    message: str = ""
    selected_restart_index: int = 0
    n_restarts: int = 1
    n_converged_restarts: int = 1
    # The fixed weight matrix (W1: data variance + simulation covariance) the final stage was
    # searched under -- travels with the result so a reader can see exactly what was held fixed.
    weights: MSMWeights | None = None
    preliminary_params: dict[str, float] | None = None  # the W0-stage optimum W1 was built from


def _validate_firm_radius_bound(base: Config, bounds: dict[str, tuple[float, float]]) -> None:
    """Rejects a firm_radius upper bound past the geometric identification limit. With
    belief_multiplier=1 (D2's unbiased disk), both search tickets (agents.py's
    search_positions()) and firms (model.py's firm placement) are drawn uniformly within a
    disk of radius cbd_radius around the CBD, so no ticket-firm pair can ever be more than
    2*cbd_radius apart. A firm_radius at or beyond that diameter makes every firm reachable
    from every ticket regardless of its exact value: the calibration loss stops responding to
    firm_radius at all, and any estimate the optimiser reports there is an artefact of a
    mis-specified search box, not a genuine finding. Skipped when belief_multiplier != 1, since
    a biased search radius scales the ticket-side disk too and the same geometric argument no
    longer applies directly."""
    if base.belief_multiplier != 1.0:
        return
    geometric_max = 2 * base.cbd_radius
    upper = bounds["firm_radius"][1]
    if upper > geometric_max:
        raise ValueError(
            f"firm_radius upper bound {upper} exceeds the geometric identification limit "
            f"2 * cbd_radius = {geometric_max}: beyond this point every ticket-firm pair is "
            "within reach regardless of firm_radius's exact value, so the calibration loss "
            "goes flat there and any resulting estimate is unidentified, not a genuine "
            "optimum. Lower the bound or raise cbd_radius."
        )


def _boundary_adjacent_params(
    params: dict[str, float], bounds: dict[str, tuple[float, float]]
) -> tuple[str, ...]:
    """Flags a parameter within _BOUNDARY_ADJACENCY_FRACTION of a bound's own magnitude (not
    the box's span) -- matching Task 8's no-false-success gate, "within one per cent of its
    numerical or geometric bound," literally."""
    flagged = []
    for name, value in params.items():
        low, high = bounds[name]
        near_low = abs(value - low) <= _BOUNDARY_ADJACENCY_FRACTION * abs(low)
        near_high = abs(value - high) <= _BOUNDARY_ADJACENCY_FRACTION * abs(high)
        if near_low or near_high:
            flagged.append(name)
    return tuple(flagged)


def _lhs_points(bounds: dict[str, tuple[float, float]], n_points: int) -> list[dict[str, float]]:
    sampler = qmc.LatinHypercube(d=len(PARAM_NAMES), seed=_LHS_SEED)
    unit_samples = sampler.random(n=n_points)
    lows = np.array([bounds[name][0] for name in PARAM_NAMES])
    highs = np.array([bounds[name][1] for name in PARAM_NAMES])
    scaled = qmc.scale(unit_samples, lows, highs)
    return [dict(zip(PARAM_NAMES, row, strict=True)) for row in scaled]


@dataclass(frozen=True)
class _RestartSearchResult:
    """Internal: the outcome of one LHS-then-multi-restart search stage under one fixed
    MSMWeights matrix."""

    params: dict[str, float]
    loss: float
    lhs_best_loss: float
    n_nelder_mead_evaluations: int
    message: str
    selected_restart_index: int
    n_restarts: int
    n_converged_restarts: int


def _restart_search(
    base: Config,
    bounds: dict[str, tuple[float, float]],
    empirical: EmpiricalMoments,
    weights: MSMWeights,
    n_lhs_points: int,
    calibration_seeds: tuple[int, ...],
    n_restarts: int,
) -> _RestartSearchResult:
    """One LHS sweep, then Nelder-Mead from the `n_restarts` best distinct LHS points, all
    under the same `weights` and `calibration_seeds`. Selects the lowest-loss CONVERGED
    restart; raises RuntimeError with every restart's SciPy status if none converged, rather
    than returning a parameter vector that was never actually validated as an optimum."""
    lhs_params = _lhs_points(bounds, n_lhs_points)
    lhs_losses = [
        msm_loss(
            np.array([p[name] for name in PARAM_NAMES]), base, empirical, weights, calibration_seeds
        )
        for p in lhs_params
    ]
    order = np.argsort(lhs_losses)
    best_lhs_loss = float(lhs_losses[order[0]])

    starts: list[dict[str, float]] = []
    seen: set[tuple[float, ...]] = set()
    for idx in order:
        point = lhs_params[idx]
        key = tuple(point[name] for name in PARAM_NAMES)
        if key in seen:
            continue
        seen.add(key)
        starts.append(point)
        if len(starts) == n_restarts:
            break

    restart_results = []
    for start in starts:
        x0 = np.array([start[name] for name in PARAM_NAMES])
        nm_result = minimize(
            msm_loss,
            x0,
            args=(base, empirical, weights, calibration_seeds),
            method="Nelder-Mead",
            bounds=[bounds[name] for name in PARAM_NAMES],
            options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 500},
        )
        restart_results.append(nm_result)

    converged_indices = [i for i, r in enumerate(restart_results) if r.success]
    if not converged_indices:
        statuses = "; ".join(
            f"restart {i} (status={r.status}): {r.message}" for i, r in enumerate(restart_results)
        )
        raise RuntimeError(
            f"no Nelder-Mead restart converged out of {len(restart_results)}: {statuses}"
        )

    winner_i = min(converged_indices, key=lambda i: restart_results[i].fun)
    winner = restart_results[winner_i]

    return _RestartSearchResult(
        params=dict(zip(PARAM_NAMES, winner.x, strict=True)),
        loss=float(winner.fun),
        lhs_best_loss=best_lhs_loss,
        n_nelder_mead_evaluations=sum(r.nfev for r in restart_results),
        message=str(winner.message),
        selected_restart_index=winner_i,
        n_restarts=len(restart_results),
        n_converged_restarts=len(converged_indices),
    )


def calibrate(
    base: Config,
    bounds: dict[str, tuple[float, float]] | None = None,
    n_lhs_points: int = 200,
    n_restarts: int = 3,
    calibration_seeds: tuple[int, ...] = CALIBRATION_SEEDS,
    validation_seeds: tuple[int, ...] = VALIDATION_SEEDS,
    weight_seeds: tuple[int, ...] = WEIGHT_SEEDS,
    empirical: EmpiricalMoments | None = None,
) -> CalibrationResult:
    """Two-step fixed-weight MSM, each step an LHS sweep followed by `n_restarts` Nelder-Mead
    restarts from the best distinct LHS points, all under common random numbers
    (`calibration_seeds`):

    1. W0 = pinv(data variance alone). Search under W0 for a preliminary estimate.
    2. Simulate `weight_seeds` at that preliminary estimate, estimate the simulation
       covariance there, build W1 = pinv(data variance + simulation covariance / len(weight_seeds)).
    3. Search again, from scratch, under W1 -- the returned CalibrationResult is this final
       search's outcome.

    Reports validation moments at `validation_seeds` (disjoint from both `calibration_seeds`
    and `weight_seeds`), so the fit quality shown isn't measured on seeds the optimiser or the
    weight matrix ever saw."""
    bounds = bounds or DEFAULT_BOUNDS
    empirical = empirical or load_empirical_moments()
    _validate_firm_radius_bound(base, bounds)

    data_cov = _data_covariance(empirical)
    w0 = _weights_from_covariance(data_cov, estimated_at_params={}, weight_seeds=())
    preliminary = _restart_search(
        base, bounds, empirical, w0, n_lhs_points, calibration_seeds, n_restarts
    )

    sim_cov = np.cov(
        _simulate_moment_matrix(base, preliminary.params, weight_seeds), rowvar=False, ddof=1
    )
    combined_cov = data_cov + sim_cov / len(weight_seeds)
    w1 = _weights_from_covariance(
        combined_cov, estimated_at_params=preliminary.params, weight_seeds=weight_seeds
    )
    final = _restart_search(
        base, bounds, empirical, w1, n_lhs_points, calibration_seeds, n_restarts
    )

    validation_moments = simulate_moments(base, final.params, validation_seeds)

    return CalibrationResult(
        params=final.params,
        loss_at_optimum=final.loss,
        lhs_best_loss=final.lhs_best_loss,
        validation_moments=validation_moments,
        n_lhs_points=n_lhs_points,
        n_nelder_mead_evaluations=final.n_nelder_mead_evaluations,
        boundary_adjacent_params=_boundary_adjacent_params(final.params, bounds),
        success=True,
        message=final.message,
        selected_restart_index=final.selected_restart_index,
        n_restarts=final.n_restarts,
        n_converged_restarts=final.n_converged_restarts,
        weights=w1,
        preliminary_params=preliminary.params,
    )


def _sha256_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git_commit_hash() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def _write_published_outputs(
    out_dir: str,
    config_path: str,
    moments_path: str,
    base: Config,
    empirical: EmpiricalMoments,
    result: CalibrationResult,
) -> None:
    """Task 8's fingerprinted outputs: an unrounded parameter/status record a reader can
    identify the exact run from without a chat transcript or local session log, and a per-
    moment fit table with standardised residuals."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    fingerprint = {
        "code_commit": _git_commit_hash(),
        "moments_csv_sha256": _sha256_file(moments_path),
        "config_path": config_path,
        "config_canonical_json": base.canonical_json(),
        "calibration_seeds": list(CALIBRATION_SEEDS),
        "validation_seeds": list(VALIDATION_SEEDS),
    }
    weights_record = None
    if result.weights is not None:
        weights_record = {
            "moment_keys": list(result.weights.moment_keys),
            "weight_matrix": result.weights.weight_matrix.tolist(),
            "estimated_at_params": result.weights.estimated_at_params,
            "weight_seeds": list(result.weights.weight_seeds),
            "ridge": result.weights.ridge,
        }

    record = {
        "fingerprint": fingerprint,
        "params": result.params,
        "preliminary_params": result.preliminary_params,
        "loss_at_optimum": result.loss_at_optimum,
        "lhs_best_loss": result.lhs_best_loss,
        "n_lhs_points": result.n_lhs_points,
        "n_nelder_mead_evaluations": result.n_nelder_mead_evaluations,
        "success": result.success,
        "message": result.message,
        "selected_restart_index": result.selected_restart_index,
        "n_restarts": result.n_restarts,
        "n_converged_restarts": result.n_converged_restarts,
        "boundary_adjacent_params": list(result.boundary_adjacent_params),
        "weights": weights_record,
    }
    (out / "calibration_result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

    rows = []
    for key in MOMENT_KEYS:
        sim_mean, sim_var = result.validation_moments[key]
        data_value = empirical.values[key]
        data_se = empirical.standard_errors[key]
        residual_se = float(np.sqrt(data_se**2 + sim_var))
        standardized_residual = (
            (sim_mean - data_value) / residual_se if residual_se > 0 else float("nan")
        )
        rows.append(
            {
                "moment": key,
                "simulated_mean": sim_mean,
                "simulated_se": float(np.sqrt(sim_var)),
                "empirical_value": data_value,
                "empirical_se": data_se,
                "standardized_residual": standardized_residual,
            }
        )
    pd.DataFrame(rows).to_csv(out / "calibration_fit.csv", index=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibrate the four free parameters by MSM.")
    parser.add_argument("--config", required=True, help="base YAML config (spatial, n_firms>0)")
    parser.add_argument("--moments", default="data/moments.csv", help="empirical moments CSV")
    parser.add_argument("--n-lhs-points", type=int, default=200)
    parser.add_argument("--n-restarts", type=int, default=3)
    parser.add_argument(
        "--out-dir", default=None, help="write calibration_result.json/calibration_fit.csv here"
    )
    args = parser.parse_args(argv)

    base = Config.from_yaml(args.config)
    empirical = load_empirical_moments(args.moments)
    result = calibrate(
        base, n_lhs_points=args.n_lhs_points, n_restarts=args.n_restarts, empirical=empirical
    )

    if args.out_dir:
        _write_published_outputs(args.out_dir, args.config, args.moments, base, empirical, result)

    print(f"base config: {args.config}")
    print(f"LHS points: {result.n_lhs_points}  (best loss {result.lhs_best_loss:.6f})")
    print(f"Nelder-Mead evaluations: {result.n_nelder_mead_evaluations}")
    print(
        f"restarts: {result.n_converged_restarts}/{result.n_restarts} converged "
        f"(selected #{result.selected_restart_index}: {result.message})"
    )
    if result.weights is not None:
        ridge_note = f", ridge={result.weights.ridge:.3e}" if result.weights.ridge else ""
        print(
            f"final weight matrix estimated at {result.weights.weight_seeds and 'W1' or 'W0'} "
            f"stage over {len(result.weights.weight_seeds)} weight seeds{ridge_note}"
        )
    print(f"loss at optimum: {result.loss_at_optimum:.6f}")
    print()
    print("calibrated parameters:")
    for name, value in result.params.items():
        print(f"  {name} = {value:.6f}")
    if result.boundary_adjacent_params:
        print(
            f"  WARNING: boundary-adjacent (within 1% of a bound), weakly identified: "
            f"{', '.join(result.boundary_adjacent_params)}"
        )
    print()
    print(f"moments at optimum (validation seeds, n={len(VALIDATION_SEEDS)}):")
    for key in MOMENT_KEYS:
        sim_mean, sim_var = result.validation_moments[key]
        data_value = empirical.values[key]
        print(
            f"  {key}: simulated={sim_mean:.4f} (se={sim_var**0.5:.4f})  "
            f"empirical={data_value:.4f} (se={empirical.standard_errors[key]:.4f})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
