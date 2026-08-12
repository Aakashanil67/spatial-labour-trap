"""Chen (2025) Appendix B: the frictionless DMP steady state, solved as an aggregate benchmark
only (locked commitment 4) -- this model's agents never solve this system, they follow local
heuristics, and nothing in src/model.py imports from here.

`a` is a required argument with no default. Locked commitment 1 says matching efficiency is
recovered, never imposed; feeding this system a default `a` would blur that line. The intended
caller fits `a` from the frictionless ABM configuration (matching.py) and passes that fitted
value in, so what this module actually checks is internal consistency of
`(l, u, v, w, q, theta)` given that `a` -- never the level of `a` itself, and never a target
the ABM is tuned toward.

Two unit mismatches with Chen's own paper, both load-bearing, not incidental:

  - Chen normalises productivity to 1 with the wage determined endogenously by Nash
    bargaining. This model normalises the wage to 1 instead (D10). Productivity `A` here is
    therefore a free parameter you choose, not fixed at 1 -- feeding this system Chen's own
    number without accounting for the different numeraire would silently rescale every result.
  - Chen's whole calibration is quarterly. This model steps monthly. Every parameter passed in
    (alpha, eta, phi, r, lambda_sep, c_post, b, A) must already be monthly-consistent -- this
    module does no unit conversion of its own. See DECISIONS.md's AR(1)/separation-rate note
    for the rebasing convention used elsewhere in this project.

`b` (the unemployment benefit) is a required parameter here, not solved for. Chen calibrates it
once as a fixed replacement rate times a baseline steady-state wage, then holds it fixed in
rand terms for subsequent solves -- not re-derived as a moving fraction of whatever wage this
particular solve produces, which would make the wage equation circular.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares


@dataclass(frozen=True)
class DMPParams:
    a: float  # matching efficiency -- fitted from the frictionless ABM, never a default
    alpha: float  # production function curvature, f(l) = A * l**alpha
    eta: float  # worker bargaining power (Hosios: eta == phi at the calibrated point)
    phi: float  # matching elasticity
    r: float  # discount rate, monthly
    lambda_sep: float  # separation rate, monthly
    c_post: float  # per-vacancy posting cost
    b: float  # unemployment benefit, fixed rand level (see module docstring)
    productivity: float  # A -- free here since the wage, not productivity, is normalised (D10)


@dataclass(frozen=True)
class DMPSolution:
    l: float
    u: float
    v: float
    w: float
    q: float
    theta: float
    converged: bool
    max_residual: float


def _residuals(x: np.ndarray, p: DMPParams) -> np.ndarray:
    l, u, v, w, q, theta = x
    return np.array(
        [
            w
            - (p.eta * p.alpha * p.productivity * l ** (p.alpha - 1))
            / (p.eta * p.alpha + 1 - p.eta)
            - (1 - p.eta) * p.b
            - p.eta * p.c_post * theta,
            p.lambda_sep * l - q * v,
            q - p.a * theta ** (-p.phi),
            theta - v / u,
            l + u - 1,
            p.alpha * p.productivity * l ** (p.alpha - 1)
            - (p.eta * p.alpha**2 * p.productivity * l ** (p.alpha - 1))
            / (p.eta * p.alpha + 1 - p.eta)
            - (1 - p.eta) * p.b
            - p.eta * p.c_post * theta
            - (p.r + p.lambda_sep) * p.c_post / q,
        ]
    )


def solve_steady_state(
    params: DMPParams,
    initial_guess: tuple[float, float, float, float, float, float] | None = None,
) -> DMPSolution:
    """Solves the six-equation system for (l, u, v, w, q, theta) given params.a as a fixed
    input. Bounded least_squares, not a bare fsolve -- fsolve is unbounded and will happily
    return a mathematically valid but economically nonsensical l < 0 or q > 1 from a poor
    starting point without complaint (see the module docstring)."""
    if initial_guess is None:
        l0 = 0.9
        u0 = 1 - l0
        theta0 = 0.5
        q0 = params.a * theta0 ** (-params.phi)
        v0 = theta0 * u0
        w0 = 0.9  # below the wage=1 numeraire ceiling, refined by the solve
        initial_guess = (l0, u0, v0, w0, q0, theta0)

    lower = (1e-6, 1e-6, 0.0, 0.0, 1e-6, 1e-6)
    upper = (1 - 1e-6, 1 - 1e-6, np.inf, np.inf, 1.0, np.inf)

    result = least_squares(
        _residuals, x0=np.array(initial_guess), bounds=(lower, upper), args=(params,)
    )
    l, u, v, w, q, theta = result.x
    max_residual = float(np.max(np.abs(result.fun)))
    return DMPSolution(
        l=l,
        u=u,
        v=v,
        w=w,
        q=q,
        theta=theta,
        converged=result.success and max_residual < 1e-6,
        max_residual=max_residual,
    )
