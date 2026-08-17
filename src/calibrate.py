"""Method of simulated moments over the four free parameters -- search_cost_per_trip (c),
initial_search_capital (W0), firm_radius (rho), firm_kappa (kappa) -- against the four moments
in data/moments.csv (locked commitment 3). Exactly identified: four parameters, four moments,
no slack for a formal overidentification test -- the out-of-calibration validation against
Banerjee and Sequeira's null result is the actual substitute (see DECISIONS.md).

The loss weights by inverse (data sampling variance + simulation variance), not data variance
alone (M9's correction to the original prompt library -- McFadden 1989 decomposes total MSM
estimator variance into a data term and a separate simulation term, and weighting by data
variance alone silently assumes the simulation term is negligible). Simulation variance is
estimated directly from the spread of the 15 common-random-number seeds at each evaluation, so
it's never assumed away.

Common random numbers (D12): CALIBRATION_SEEDS is reused at every evaluation during both the
Latin hypercube and Nelder-Mead stages, so the loss is a deterministic function of the
parameters -- Nelder-Mead has no defence against a noisy objective otherwise, and a restart
policy would treat the symptom, not the cause. VALIDATION_SEEDS (disjoint) is used only once,
at the reported optimum, so the fit quality isn't measured on the seeds the optimiser fitted to.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, replace

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


def msm_loss(
    param_vector: np.ndarray,
    base: Config,
    empirical: EmpiricalMoments,
    seeds: tuple[int, ...] = CALIBRATION_SEEDS,
) -> float:
    """Weighted sum of squared deviations, weights = 1 / (data_SE^2 + simulation_variance) --
    M9's corrected weight matrix, not data variance alone. Returns inf for a parameter point
    that produces a nan moment (an infeasible or degenerate region of the parameter space),
    so the optimiser is steered away from it rather than crashing on it."""
    params = dict(zip(PARAM_NAMES, param_vector, strict=True))
    simulated = simulate_moments(base, params, seeds)

    loss = 0.0
    for key in MOMENT_KEYS:
        sim_mean, sim_var = simulated[key]
        if np.isnan(sim_mean):
            return float("inf")
        data_value = empirical.values[key]
        data_se = empirical.standard_errors[key]
        weight = 1.0 / (data_se**2 + sim_var)
        loss += weight * (sim_mean - data_value) ** 2
    return float(loss)


@dataclass(frozen=True)
class CalibrationResult:
    params: dict[str, float]
    loss_at_optimum: float
    lhs_best_loss: float  # the best loss found during the coarse sweep, before refinement
    validation_moments: dict[str, tuple[float, float]]  # (mean, variance_of_mean), 50 seeds
    n_lhs_points: int
    n_nelder_mead_evaluations: int
    # Parameter names whose calibrated value sits within _BOUNDARY_ADJACENCY_FRACTION of either
    # edge of its search box -- weakly identified, not a genuine interior optimum. Empty on a
    # clean run; a non-empty tuple is itself a finding, not something to round away.
    boundary_adjacent_params: tuple[str, ...] = ()


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


def calibrate(
    base: Config,
    bounds: dict[str, tuple[float, float]] | None = None,
    n_lhs_points: int = 200,
    calibration_seeds: tuple[int, ...] = CALIBRATION_SEEDS,
    validation_seeds: tuple[int, ...] = VALIDATION_SEEDS,
    empirical: EmpiricalMoments | None = None,
) -> CalibrationResult:
    """Coarse Latin hypercube sweep over `bounds`, then Nelder-Mead from the best LHS point,
    both stages against the same `calibration_seeds`. Reports the final moments at
    `validation_seeds` (disjoint), so the fit quality shown isn't measured on the seeds the
    optimiser was allowed to fit to."""
    bounds = bounds or DEFAULT_BOUNDS
    empirical = empirical or load_empirical_moments()
    _validate_firm_radius_bound(base, bounds)

    lhs_params = _lhs_points(bounds, n_lhs_points)
    lhs_losses = [
        msm_loss(np.array([p[name] for name in PARAM_NAMES]), base, empirical, calibration_seeds)
        for p in lhs_params
    ]
    best_idx = int(np.argmin(lhs_losses))
    best_lhs_point = lhs_params[best_idx]
    best_lhs_loss = lhs_losses[best_idx]

    x0 = np.array([best_lhs_point[name] for name in PARAM_NAMES])
    nm_result = minimize(
        msm_loss,
        x0,
        args=(base, empirical, calibration_seeds),
        method="Nelder-Mead",
        bounds=[bounds[name] for name in PARAM_NAMES],
        options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 500},
    )

    final_params = dict(zip(PARAM_NAMES, nm_result.x, strict=True))
    validation_moments = simulate_moments(base, final_params, validation_seeds)

    return CalibrationResult(
        params=final_params,
        loss_at_optimum=float(nm_result.fun),
        lhs_best_loss=float(best_lhs_loss),
        validation_moments=validation_moments,
        n_lhs_points=n_lhs_points,
        n_nelder_mead_evaluations=int(nm_result.nfev),
        boundary_adjacent_params=_boundary_adjacent_params(final_params, bounds),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibrate the four free parameters by MSM.")
    parser.add_argument("--config", required=True, help="base YAML config (spatial, n_firms>0)")
    parser.add_argument("--moments", default="data/moments.csv", help="empirical moments CSV")
    parser.add_argument("--n-lhs-points", type=int, default=200)
    args = parser.parse_args(argv)

    base = Config.from_yaml(args.config)
    empirical = load_empirical_moments(args.moments)
    result = calibrate(base, n_lhs_points=args.n_lhs_points, empirical=empirical)

    print(f"base config: {args.config}")
    print(f"LHS points: {result.n_lhs_points}  (best loss {result.lhs_best_loss:.6f})")
    print(f"Nelder-Mead evaluations: {result.n_nelder_mead_evaluations}")
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
