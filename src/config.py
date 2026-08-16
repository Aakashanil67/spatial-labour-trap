"""Model configuration.

Wage is deliberately not a config field: D10 normalises it to 1 as the numeraire, since c, W0,
the household inflow and the wage gap are all money quantities and scaling them together leaves
the model's behaviour unchanged. Making wage a free field would silently reopen that hole.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Config:
    n_agents: int
    n_vacancies: int  # MVM fixed-pool mode when n_firms == 0; ignored otherwise (see n_firms)
    initial_search_capital: float  # W0. Mean of the draw once initial_capital_spread > 0.
    search_cost_per_trip: float  # c -- the flat/base component; see transport_cost_rate
    separation_rate: float  # lambda, monthly probability an employed agent is separated (M1)
    belief_multiplier: float  # beta -- biases perceived offer rate away from the observed one (M6)
    household_inflow: float  # g, added to a discouraged agent's capital every step
    reentry_threshold: float  # capital level a discouraged agent needs to resume searching
    max_trips_per_step: int  # bound on the search-intensity margin (M5)
    n_steps: int
    seed: int
    shuffled_activation: bool = True  # D1 robustness switch: shuffled vs fixed activation order

    # -- Week 2: spatial grid. All default to values that collapse to the MVM's single-CBD-cell
    # behaviour (everyone at distance 0), so configs/mvm.yaml is unaffected and stays a genuine
    # regression test -- see the design note in DECISIONS.md.
    grid_size: int = 1  # city width/height in grid units
    cbd_radius: float = 0.5  # radius of the CBD zone around the grid centre
    n_townships: int = 0  # 0 = no spatial draw; every agent's home is the CBD centre
    township_distance_min: float = 0.0  # min distance from CBD centre for a township cluster
    township_distance_max: float = 0.0  # max distance from CBD centre for a township cluster
    township_spread: float = 0.0  # std dev of home draws around their township's centre
    # rand per grid-unit distance per trip, on top of search_cost_per_trip
    transport_cost_rate: float = 0.0
    n_distance_bands: int = 4  # for the D3 cell collector; irrelevant when n_townships == 0

    # -- Week 2: endogenous firm vacancy posting (M4). n_firms == 0 keeps the MVM's flat
    # fixed-vacancy-pool behaviour; n_firms > 0 switches to real Firm agents.
    n_firms: int = 0
    firm_radius: float = 0.0  # rho -- neighbourhood matching radius, deliberately not "rho_A"
    firm_productivity: float = 1.0  # p, scaled by the AR(1) shock A_t each step
    firm_posting_cost: float = 0.0  # c_post, per vacancy posted
    firm_kappa: float = 0.0  # posting sensitivity; 0 keeps vacancies at their initial count
    # r, monthly. Rebased from Chen (2025)'s quarterly 0.004 via (1 + r_q) = (1 + r_m)^3 -- see
    # DECISIONS.md's AR(1)/separation-rate note for the same monthly-vs-quarterly convention
    # applied consistently across every borrowed parameter.
    discount_rate: float = 0.001332

    # -- Week 2: AR(1) aggregate productivity shock (M2). Deliberately named rho_A/sigma_A, not
    # rho/sigma, so the calibration optimiser can never conflate shock persistence with the
    # firm's neighbourhood radius -- see DECISIONS.md.
    rho_A: float = 0.0  # persistence; 0 = no persistence (degenerate constant productivity)
    sigma_A: float = 0.0  # shock std dev; 0 = no shock (deterministic productivity = 1)

    # -- Week 2: wealth heterogeneity (prompt 3.1). 0 keeps the MVM's single shared W0 --
    # every agent gets exactly initial_search_capital and wealth_quartile is meaningless
    # (all agents share cell 0). > 0 draws each agent's own capital from a lognormal with
    # that coefficient of variation, matching the shape of real wealth data (skewed, never
    # negative) rather than a normal draw that would need truncating.
    initial_capital_spread: float = 0.0

    # -- Week 2: moment burn-in (prompt 4.2 / the plan's "windows stated numerically"
    # requirement). Steps <= burn_in_steps are excluded from every time-averaged moment, so
    # the cold-start transient documented in DECISIONS.md never contaminates a calibration
    # target. 0 keeps every step -- fine for a short MVM run, wrong for anything meant to
    # calibrate against.
    burn_in_steps: int = 0

    # -- Week 2: per-agent tracing (D3). Off by default (empty tuple, fixed and tiny even when
    # set) -- a full per-step panel for a HANDFUL of named agents, not the population panel D3
    # rejected. This is what the single-agent trajectory figure comes from, and it's what gets
    # narrated to prove locked commitment 6 (discouragement is not absorbing) is actually
    # implemented rather than asserted in a comment. A tuple, not a list, so it stays hashable
    # for the run cache's canonical JSON.
    trace_agent_ids: tuple[int, ...] = ()

    @classmethod
    def from_yaml(cls, path: str | Path) -> Config:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return cls(**raw)

    def canonical_json(self) -> str:
        """Stable hash input for the run cache (I1). No rounding, no quantisation -- see
        DECISIONS.md on why quantising floats here would cause silent false-positive cache
        hits during Nelder-Mead's late, tiny-step contractions."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


# -- D12: common random numbers for the calibration search. One fixed seed list, reused at
# every parameter evaluation during both the Latin hypercube and Nelder-Mead stages, so the
# MSM loss is a deterministic function of the parameters being searched over -- without this,
# the simplex can contract onto a random fluctuation in independently-redrawn seeds and report
# a false convergence. VALIDATION_SEEDS is disjoint from CALIBRATION_SEEDS on purpose: the fit
# quality reported at the optimum is never measured on the exact seeds the optimiser was
# allowed to fit to. Plain integer ranges, not drawn from any RNG -- there's nothing to be
# random about here, only fixed and disjoint.
CALIBRATION_SEEDS: tuple[int, ...] = tuple(range(1, 16))  # 15 seeds, D12/prompt 4.2
VALIDATION_SEEDS: tuple[int, ...] = tuple(range(1001, 1051))  # 50 seeds, disjoint from above
