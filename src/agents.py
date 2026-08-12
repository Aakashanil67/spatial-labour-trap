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

import math
from enum import Enum, auto

from mesa import Agent


class SeekerState(Enum):
    SEARCHING = auto()
    EMPLOYED = auto()
    DISCOURAGED = auto()


WAGE = 1.0  # D10 numeraire -- not a config field, see config.py


class JobSeeker(Agent):
    def __init__(self, model, initial_capital: float, home_x: float = 0.0, home_y: float = 0.0):
        super().__init__(model)
        self.state = SeekerState.SEARCHING
        self.search_capital = initial_capital
        self.trips_this_step = 0
        self.belief_inactive_this_step = False
        self.months_in_state = 0  # spell length in the current state, for the duration moment

        # Week 2 spatial fields. home_x/home_y default to the CBD centre (0, 0 in the model's
        # own centred coordinate frame), so distance_to_cbd is 0 and cost_per_trip reduces
        # exactly to the flat search_cost_per_trip when the model isn't spatially configured.
        self.home_x = home_x
        self.home_y = home_y
        cfg = model.config
        raw_distance = ((home_x - model.cbd_x) ** 2 + (home_y - model.cbd_y) ** 2) ** 0.5
        self.distance_to_cbd = max(0.0, raw_distance - cfg.cbd_radius)
        # Assigned once, never updated -- D3/the wealth-quartile lesson applies here too: a
        # heterogeneity cut keyed on where an agent GOES would be an artefact of the very
        # policy experiment being measured, not a description of who it helped.
        self.distance_band = model.distance_band_for(self.distance_to_cbd)

    @property
    def cost_per_trip(self) -> float:
        cfg = self.model.config
        return cfg.search_cost_per_trip + cfg.transport_cost_rate * self.distance_to_cbd

    def can_afford_one_trip(self) -> bool:
        return self.search_capital >= self.cost_per_trip

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
        cost = self.cost_per_trip
        noise = self.model.rng.uniform(0.9, 1.1)
        perceived_rate = self.model.observed_hire_rate_per_trip * cfg.belief_multiplier * noise
        if cost <= 0:
            intensity = 1.0
        else:
            intensity = min(1.0, (perceived_rate * WAGE) / cost)
        desired = round(cfg.max_trips_per_step * intensity)
        affordable = int(self.search_capital // cost) if cost > 0 else cfg.max_trips_per_step
        return max(0, min(desired, affordable, cfg.max_trips_per_step))

    def step_searching(self) -> None:
        self.trips_this_step = self.decide_trips()
        self.belief_inactive_this_step = self.trips_this_step == 0
        self.search_capital -= self.trips_this_step * self.cost_per_trip
        self.months_in_state += 1

    def search_positions(self) -> list[tuple[float, float]]:
        """One effective search position per trip made this step, for the per-firm
        neighbourhood matching (n_firms > 0 mode). D2's targeting bias: unbiased agents
        (beta == 1) draw uniformly within the CBD zone, which is also where firms sit, so an
        unbiased agent's trips land where the real vacancies are by construction. A biased
        agent's draw is scaled by beta around the CBD centre -- beta > 1 wanders further out
        than the CBD zone actually extends, beta < 1 stays too close to the centre -- either
        way shrinking the overlap with real firm positions without the agent ever being told
        the true vacancy locations. This is the actual mechanism behind "mistargeted search"
        (Banerjee and Sequeira 2023), not a price effect (see D2 in DECISIONS.md)."""
        cfg = self.model.config
        model = self.model
        positions = []
        for _ in range(self.trips_this_step):
            radius = cfg.cbd_radius * cfg.belief_multiplier * model.rng.uniform(0.0, 1.0)
            angle = model.rng.uniform(0.0, 2 * math.pi)
            x = model.cbd_x + radius * math.cos(angle)
            y = model.cbd_y + radius * math.sin(angle)
            positions.append((x, y))
        return positions

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


class Firm(Agent):
    """Posts vacancies endogenously from a profit heuristic (M4, locked commitment 5): a
    wage subsidy has to have a real channel to raise employment through, which requires firms
    that actually respond to the subsidised wage rather than a fixed vacancy count.

    The heuristic is disciplined against Pissarides's free-entry condition
    (2000, p.11-12): `p - w = (r + lambda) * pc / q(theta)`. It is not the literal condition --
    the firm is boundedly rational and doesn't solve the DMP Bellman equation (locked
    commitment 4) -- but every term of that condition appears in the heuristic: `r` and
    `lambda` discount the value of a filled job, `q` is this firm's own fill-probability
    estimate, and `pc` is the posting cost. See DECISIONS.md, "Two corrections to not-yet-
    built code", for why a heuristic that merely drives profit toward zero without these terms
    would pass a weaker free-entry test through pure market congestion rather than the real
    thing.
    """

    # A firm quiet for this many consecutive periods posts one trial vacancy regardless of
    # what its own computed target says -- see decide_vacancies for why this is load-bearing,
    # not decorative. Fixed and documented rather than exposed as a free calibration knob,
    # same reasoning as the fill-probability learning rate below.
    _EXPLORATION_PATIENCE = 3

    def __init__(self, model, x: float, y: float, initial_vacancies: int = 0):
        super().__init__(model)
        self.x = x
        self.y = y
        self.vacancies = initial_vacancies
        self.hires_this_step = 0
        self.quiet_streak = 0
        # Naive uninformed prior: a rough geometric guess at what fraction of the population
        # could plausibly fall within this firm's radius, before any real observation exists.
        # Same "don't start at zero" lesson as the model-level observed_hire_rate_per_trip --
        # starting at exactly 0 would mean the firm never expects to fill a vacancy and so
        # never posts one, a permanent no-vacancy deadlock with no way out.
        cfg = model.config
        area_fraction = min(1.0, (cfg.firm_radius / max(cfg.grid_size, 1)) ** 2)
        self.fill_prob_estimate = max(0.05, min(1.0, area_fraction))

    def decide_vacancies(self) -> None:
        """Set this period's vacancy count from expected profit per hire, discounted the way
        Pissarides's free-entry condition discounts it, scaled by kappa.

        Below the exploration patience, a computed target of zero is trusted and the firm
        posts nothing. Past it, the firm posts one trial vacancy anyway. Without this, a firm
        whose belief ever decays low enough that the formula rounds to zero is stuck there
        permanently: posting zero means update_fill_probability's quiet-period rule correctly
        leaves the belief untouched, so the belief that produced zero can never be revised by
        a fresh observation, and the firm is locked out for the rest of the run. Caught in
        testing on a 10-firm config where one bad-luck zero-hire period (not a quiet period --
        the firm posted, it just filled none of them) was enough to trigger this before the
        exponential-average fix below existed; the smoothing reduces how fast a firm decays
        toward the trap, the exploration floor is what actually stops it arriving."""
        cfg = self.model.config
        expected_value_per_hire = (cfg.firm_productivity * self.model.productivity_shock - WAGE) / (
            cfg.discount_rate + cfg.separation_rate
        )
        target = cfg.firm_kappa * (
            self.fill_prob_estimate * expected_value_per_hire - cfg.firm_posting_cost
        )
        computed = max(0, round(target))
        if computed == 0 and self.quiet_streak >= self._EXPLORATION_PATIENCE:
            self.vacancies = 1
        else:
            self.vacancies = computed
        self.quiet_streak = 0 if self.vacancies > 0 else self.quiet_streak + 1
        self.hires_this_step = 0

    # Smoothing weight on a fresh observation, not a free calibration parameter -- kappa and
    # the posting cost are the knobs meant to move; this just stops one unlucky period from
    # overwriting the whole belief (see the docstring below for the failure mode it fixes).
    _FILL_PROB_LEARNING_RATE = 0.3

    def update_fill_probability(self) -> None:
        """Only updates on a period this firm actually posted vacancies -- a quiet period
        (vacancies == 0) carries no information about the true fill probability and must
        leave the estimate where it was, not reset it (the same bug class as the model-level
        observed_hire_rate_per_trip in Week 1).

        The update itself is an exponential moving average, not a hard replace. A hard replace
        was tried first and produced a second, subtler deadlock: a firm that posts a handful
        of vacancies and (by ordinary local demand variance, not a quiet period) fills none of
        them gets its belief set to exactly 0.0, which then implies negative expected profit
        forever -- a single unlucky draw permanently kills the firm, with no path back to a
        new observation, the same structural failure as the Week 1 zero-search deadlock but
        arrived at through bad luck instead of a bad prior. Smoothing means one bad period
        pulls the estimate down without being able to zero it out completely."""
        if self.vacancies > 0:
            observed = self.hires_this_step / self.vacancies
            rate = self._FILL_PROB_LEARNING_RATE
            self.fill_prob_estimate = (1 - rate) * self.fill_prob_estimate + rate * observed
