"""The minimum viable model: one CBD, homogeneous seekers, fixed vacancies.

Step order is deliberately explicit rather than folded into one per-agent `step()` method, so
D11 (measurement timing) is enforced by construction: u_t and v_t are recorded as start-of-
period stocks, strictly before the matching call that would otherwise contaminate them with
this period's outcome.

Mesa 3.5.1 runs on a discrete-event core, discovered by reading the installed source after a
first pass silently double-counted every step. `Model.__init__` captures whatever `self.step`
resolves to at construction time as `self._user_step` (here, this class's `step` below), then
overwrites the *instance* attribute `self.step` with `self._wrapped_step`, which advances a
scheduled event queue by one time unit. That scheduled event is `_do_step`, which itself does
`self.steps += 1` before calling `self._user_step()`. A model-level `self.steps += 1` inside
this method would therefore double-count on every call to `model.step()` from the outside --
confirmed empirically (a 10-agent, 3-step run reported step 2, 4, 6) before being fixed here.
"""

from __future__ import annotations

import pandas as pd
from mesa import Model

from src.agents import JobSeeker, SeekerState
from src.config import Config


class CityModel(Model):
    def __init__(self, config: Config):
        super().__init__(rng=config.seed)
        self.config = config
        # Backward-looking realised hire rate agents perceive (subject to their own beta
        # bias) when deciding this step's trips. Simple realised rate, not an EMA -- there's
        # no persistence process yet for an EMA to smooth over (that's M2's AR(1) shock,
        # arriving with the spatial grid in Week 2).
        #
        # Initialised to the naive vacancy-to-seeker ratio, not zero: at t=0 every agent is
        # searching, so v/u is the rate an uninformed searcher could reasonably expect before
        # any real observation exists (it's the DMP job-finding-rate concept before any
        # friction has had a chance to bind). Starting at exactly 0.0 was a real bug caught in
        # the first smoke test: with observed_hire_rate_per_trip == 0, every agent's expected
        # gain per trip is 0, so decide_trips() always returns 0, so total_trips stays 0
        # forever, so the observed rate never updates away from 0 -- a self-fulfilling
        # zero-search equilibrium with no way out.
        self.observed_hire_rate_per_trip = config.n_vacancies / config.n_agents
        self.history: list[dict] = []

        for _ in range(config.n_agents):
            JobSeeker(self, initial_capital=config.initial_search_capital)

    def _activate(self, agent_set, method_name: str) -> None:
        """D1: shuffled vs fixed-order activation, toggled from config for the activation-
        order robustness test. Every per-agent method here only reads and writes its own
        state plus model-level scalars fixed at the start of the step (never a sibling
        agent's just-updated state), so this MVM's outcome is order-invariant by
        construction -- the test currently passes trivially. That stops being true once
        Week 2 adds neighbourhood-radius hiring, where local competition for a nearby
        vacancy can plausibly depend on processing order; keeping the switch and the test
        now means it's a live regression guard the moment that changes, not a retrofit."""
        agent_set.shuffle_do(method_name) if self.config.shuffled_activation else agent_set.do(
            method_name
        )

    def step(self) -> None:
        cfg = self.config
        # No manual self.steps increment here -- Mesa's _do_step already does it before
        # calling this method (see the module docstring for why).

        # 1. Separations: employed -> searching (M1). Without this, employment is absorbing.
        employed = self.agents.select(lambda a: a.state is SeekerState.EMPLOYED)
        n_searching_pre = len(self.agents.select(lambda a: a.state is SeekerState.SEARCHING))
        self._activate(employed, "step_employed")
        n_separations = (
            len(self.agents.select(lambda a: a.state is SeekerState.SEARCHING)) - n_searching_pre
        )

        # 2. Re-entry: discouraged -> searching, given this step's household inflow (locked
        #    commitment 6 -- discouragement is not absorbing).
        discouraged = self.agents.select(lambda a: a.state is SeekerState.DISCOURAGED)
        n_disc_pre = len(discouraged)
        self._activate(discouraged, "step_discouraged")
        n_reentries = n_disc_pre - len(
            self.agents.select(lambda a: a.state is SeekerState.DISCOURAGED)
        )

        # 3. Capital-exhaustion check, using capital as it stands entering this step -- i.e.
        #    from trips paid for last step. An agent that can no longer afford one trip
        #    becomes discouraged before this period's u_t is recorded, not after.
        searching = self.agents.select(lambda a: a.state is SeekerState.SEARCHING)
        n_searching_pre_exhaustion = len(searching)
        for agent in searching:
            if not agent.can_afford_one_trip():
                agent.state = SeekerState.DISCOURAGED
                agent.months_in_state = 0
        searching = self.agents.select(lambda a: a.state is SeekerState.SEARCHING)
        n_new_discouraged = n_searching_pre_exhaustion - len(searching)

        # 4. Record start-of-period stocks (D11), strictly before matching runs.
        u_t = len(searching)
        v_t = cfg.n_vacancies
        l_t = len(self.agents.select(lambda a: a.state is SeekerState.EMPLOYED))
        disc_t = len(self.agents.select(lambda a: a.state is SeekerState.DISCOURAGED))

        # 5. Trip decisions and payment (the intensity margin, M5).
        self._activate(searching, "step_searching")
        n_belief_inactive = sum(1 for a in searching if a.belief_inactive_this_step)
        total_trips = sum(a.trips_this_step for a in searching)

        # 6. Matching: one lottery ticket per trip, draw min(V, distinct candidates) hires
        #    without replacement. An agent needs only one job even if several of its own
        #    trips would have "won", so hires are deduplicated by agent, not by ticket. No
        #    equation here says vacancy scarcity lowers matching efficiency -- efficiency is
        #    recovered later by fitting the matching function to the (u, v, m) series this
        #    produces (locked commitment 1), never assumed in the mechanism itself.
        candidates = [a for a in searching if a.trips_this_step > 0]
        m_t = 0
        if candidates and v_t > 0:
            tickets = [a for a in candidates for _ in range(a.trips_this_step)]
            self.random.shuffle(tickets)
            n_draw = min(v_t, len(candidates))
            hired: list[JobSeeker] = []
            seen_ids: set[int] = set()
            for a in tickets:
                if len(hired) >= n_draw:
                    break
                if a.unique_id not in seen_ids:
                    hired.append(a)
                    seen_ids.add(a.unique_id)
            for a in hired:
                a.resolve_hire()
            m_t = len(hired)

        # Only update the observed rate when this step actually produced an observation. A
        # step where nobody searched carries no information about the hire rate and should
        # leave the belief where it was -- resetting it to 0.0 here was a second real bug
        # caught in testing: it made a temporary all-quiet step permanent, since a rate of
        # exactly 0.0 can never recommend searching again on its own.
        if total_trips > 0:
            self.observed_hire_rate_per_trip = m_t / total_trips

        self.history.append(
            {
                "step": self.steps,
                "u": u_t,
                "v": v_t,
                "l": l_t,
                "discouraged": disc_t,
                "m": m_t,
                "total_trips": total_trips,
                "n_separations": n_separations,
                "n_reentries": n_reentries,
                "n_new_discouraged": n_new_discouraged,
                "n_belief_inactive": n_belief_inactive,
                "mean_search_capital": sum(a.search_capital for a in self.agents) / cfg.n_agents,
            }
        )

    def run(self) -> pd.DataFrame:
        for _ in range(self.config.n_steps):
            self.step()
        return pd.DataFrame(self.history)
