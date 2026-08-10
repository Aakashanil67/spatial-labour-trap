"""Job seeker agent: search, discouragement, and re-entry.

Two distinct reasons a searching agent can end up not looking for work this step, and the
model tracks both separately rather than collapsing them into one "discouraged" bucket (M10):

- capital exhaustion: the agent cannot afford even one trip. This is the model's literal,
  proposal-defined discouragement -- "the state reached when accumulated transport costs have
  exhausted an agent's search capital" -- and is a hard state (SeekerState.DISCOURAGED)
  requiring the household inflow to recover from.
- belief-driven inactivity: the agent can afford to search but, given its (possibly biased)
  perceived offer rate, judges it isn't worth the cost this step. This is closer to StatsSA's
  actual discouraged-work-seeker definition ("believes no jobs are available") and doesn't
  change the hard state -- the agent remains SEARCHING and can resume next step without
  waiting on the household inflow.

Reporting both, and their union, is how the model closes the gap between its own mechanism and
the QLFS definition it's calibrated against (see DECISIONS.md).
"""

from __future__ import annotations

from enum import Enum, auto

from mesa import Agent


class SeekerState(Enum):
    SEARCHING = auto()
    EMPLOYED = auto()
    DISCOURAGED = auto()


WAGE = 1.0  # D10 numeraire -- not a config field, see config.py


class JobSeeker(Agent):
    def __init__(self, model, initial_capital: float):
        super().__init__(model)
        self.state = SeekerState.SEARCHING
        self.search_capital = initial_capital
        self.trips_this_step = 0
        self.belief_inactive_this_step = False
        self.months_in_state = 0  # spell length in the current state, for the duration moment

    def can_afford_one_trip(self) -> bool:
        return self.search_capital >= self.model.config.search_cost_per_trip

    def decide_trips(self) -> int:
        """How many trips to make this step, given the agent's (biased) perceived return.

        `belief_multiplier` scales the model's *observed* hire rate per trip, so an agent with
        beta > 1 overestimates its chances and searches harder than the realised rate would
        justify; beta < 1 is the mirror case. In the MVM there's only one location, so belief
        only biases how much to search, not where -- the targeting half of D2 needs the spatial
        grid (Week 2).

        Idiosyncratic perception noise (+/-10% of the observed rate) is added on top of beta.
        Without it, agents that are homogeneous in every config parameter also make an
        identical trips decision every step, which synchronises the whole population: everyone
        floods the market on a step the rate looks good, drives the realised rate down to
        exactly the point where a repeat of that identical calculation says "not worth it" for
        every agent simultaneously, and the market oscillates between all-search and no-search
        rather than settling. A tiny per-agent draw breaks the synchrony -- it's the difference
        between agents observing the same public signal and each perceiving it identically.

        Intensity scales continuously with how favourable the perceived return is relative to
        cost, rather than gating on a hard "worth it or not" threshold. A first version used a
        hard cutoff and got stuck: with a pessimistic starting belief, every agent decided
        against a single trip on the very first step, nobody ever generated a real observation
        to correct that belief with, and the market never held up (all zeros for a 20-step
        test run, capital never spent because nobody paid for a trip -- a proposal that says
        job seekers actively search and grind down their capital over time cannot be built on
        agents who refuse to try at all from a shaky prior). Scaling means an agent at exactly
        break-even still searches at full intensity, and one who thinks the market is bad
        throttles down smoothly instead of refusing outright -- which is also what actually
        lets a pessimistic prior get corrected by real experience."""
        cfg = self.model.config
        noise = self.model.rng.uniform(0.9, 1.1)
        perceived_rate = self.model.observed_hire_rate_per_trip * cfg.belief_multiplier * noise
        if cfg.search_cost_per_trip <= 0:
            intensity = 1.0
        else:
            intensity = min(1.0, (perceived_rate * WAGE) / cfg.search_cost_per_trip)
        desired = round(cfg.max_trips_per_step * intensity)
        affordable = int(self.search_capital // cfg.search_cost_per_trip)
        return max(0, min(desired, affordable, cfg.max_trips_per_step))

    def step_searching(self) -> None:
        cfg = self.model.config
        self.trips_this_step = self.decide_trips()
        self.belief_inactive_this_step = self.trips_this_step == 0
        self.search_capital -= self.trips_this_step * cfg.search_cost_per_trip
        self.months_in_state += 1

    def step_discouraged(self) -> None:
        cfg = self.model.config
        self.search_capital += cfg.household_inflow
        self.months_in_state += 1
        if self.search_capital >= cfg.reentry_threshold:
            self.state = SeekerState.SEARCHING
            self.months_in_state = 0

    def step_employed(self) -> None:
        """Exogenous separation (M1). Without this, employment is absorbing: u -> 0 and the
        matching function has no (u, v, m) variation left to fit."""
        if self.random.random() < self.model.config.separation_rate:
            self.state = SeekerState.SEARCHING
            self.months_in_state = 0

    def resolve_hire(self) -> None:
        self.state = SeekerState.EMPLOYED
        self.months_in_state = 0
