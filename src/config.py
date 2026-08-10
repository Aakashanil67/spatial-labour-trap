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
    n_vacancies: int
    initial_search_capital: float  # W0. Homogeneous across agents in the MVM (Week 2 draws it).
    search_cost_per_trip: float  # c
    separation_rate: float  # lambda, monthly probability an employed agent is separated (M1)
    belief_multiplier: float  # beta -- biases perceived offer rate away from the observed one (M6)
    household_inflow: float  # g, added to a discouraged agent's capital every step
    reentry_threshold: float  # capital level a discouraged agent needs to resume searching
    max_trips_per_step: int  # bound on the search-intensity margin (M5)
    n_steps: int
    seed: int
    shuffled_activation: bool = True  # D1 robustness switch: shuffled vs fixed activation order

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
