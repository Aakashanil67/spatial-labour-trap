"""The city model: one CBD, seekers (homogeneous in the MVM, spatially heterogeneous once
n_townships > 0), a fixed vacancy pool or endogenous firms depending on config.

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

Week 2 adds a spatial grid, endogenous firm vacancy posting, and an AR(1) productivity shock,
all gated on config fields that default to values collapsing exactly to Week 1's MVM behaviour
(n_townships=0, n_firms=0, rho_A=sigma_A=0) -- so configs/mvm.yaml is an unaffected regression
test, not a special case threaded through every branch below. `self.agents` now mixes
JobSeeker and Firm instances once firms exist, so every seeker-only query below goes through
`self._seekers(...)` rather than a repeated inline filter.
"""

from __future__ import annotations

import math

import pandas as pd
from mesa import Model

from src.agents import Firm, JobSeeker, SeekerState
from src.config import Config

# Completed-spell histogram bucket edges, in months, chosen to match QLFS's own duration
# question (Q36TIMESEEK) exactly: <3, 3-6, 6-9, 9-12, 1-3yr, 3-5yr, >5yr. This is the
# DESCRIPTIVE secondary structure D3 calls for, not the calibration target -- completed spells
# under-represent long spells relative to a survey of the currently-unemployed stock under
# length-biased sampling (a shorter true spell is more likely to complete inside any fixed
# observation window). The actual long_term_share moment is computed fresh each step from
# agents currently in the SEARCHING state, matching QLFS's stock-based definition exactly; see
# DECISIONS.md D3.
SPELL_BUCKET_EDGES_MONTHS = (3, 6, 9, 12, 36, 60)
LONG_TERM_THRESHOLD_MONTHS = 12


class CityModel(Model):
    def __init__(self, config: Config):
        super().__init__(rng=config.seed)
        self.config = config
        self.cbd_x = 0.0
        self.cbd_y = 0.0

        # AR(1) aggregate productivity shock (M2). log A_t = rho_A * log A_{t-1} + eps. Starts
        # at the deterministic steady state A_0 = 1. With the MVM defaults (rho_A = sigma_A =
        # 0) this stays exactly 1.0 every step: 0 * log(1) + Normal(0, 0) = 0 -> A_t = 1.
        self.productivity_shock = 1.0

        # Backward-looking realised hire rate agents perceive (subject to their own beta
        # bias) when deciding this step's trips. Initialised to the naive vacancy-to-seeker
        # ratio, not zero -- starting at exactly 0.0 was a real bug caught in Week 1 testing
        # (see agents.py's decide_trips docstring): zero perceived value means zero trips
        # means zero observations means the belief never updates away from zero.
        self.observed_hire_rate_per_trip = config.n_vacancies / config.n_agents
        self.history: list[dict] = []
        # D3's second fixed-size structure: a completed-spell histogram, descriptive only
        # (see the module-level SPELL_BUCKET_EDGES_MONTHS docstring for why it is never the
        # calibration target itself). One count per bucket, incremented whenever a searching
        # spell ends -- by a hire or by capital exhaustion -- never reset during a run.
        self.completed_spell_counts: dict[int, int] = dict.fromkeys(
            range(len(SPELL_BUCKET_EDGES_MONTHS) + 1), 0
        )
        # D3's cell aggregates: one row per (distance_band, wealth_quartile) per step. This is
        # what the Week 5 heterogeneity cuts and the actual calibration target (the stock-based
        # long-term share, computed fresh each step from currently-searching agents) both read.
        self.cell_history: list[dict] = []
        # D3's per-agent trace: a full per-step panel, but only for the handful of agents
        # named in config.trace_agent_ids -- fixed and tiny even at N=5,000, never the
        # population panel D3 explicitly rejected.
        self.trace_history: list[dict] = []

        self._township_centres = self._draw_township_centres()
        self.firms: list[Firm] = self._create_firms()

        capitals, wealth_quartiles = self._draw_capitals()
        for capital, quartile in zip(capitals, wealth_quartiles, strict=True):
            home_x, home_y = self._draw_home()
            JobSeeker(
                self,
                initial_capital=capital,
                home_x=home_x,
                home_y=home_y,
                wealth_quartile=quartile,
            )
        traced_ids = set(config.trace_agent_ids)
        self._traced_agents = [a for a in self._seekers() if a.unique_id in traced_ids]

    # -- Agent-set filtering ---------------------------------------------------------------

    def _seekers(self, state: SeekerState | None = None):
        if state is None:
            return self.agents.select(lambda a: isinstance(a, JobSeeker))
        return self.agents.select(lambda a: isinstance(a, JobSeeker) and a.state is state)

    # -- Duration tracking (D3) --------------------------------------------------------------

    @staticmethod
    def _spell_bucket(months: int) -> int:
        bucket = 0
        for edge in SPELL_BUCKET_EDGES_MONTHS:
            if months < edge:
                break
            bucket += 1
        return bucket

    def _record_completed_spell(self, months: int) -> None:
        self.completed_spell_counts[self._spell_bucket(months)] += 1

    def _collect_cell_row(self, searching) -> None:
        """One row per (distance_band, wealth_quartile) cell, every step. Aggregates only --
        no agent identifiers -- see D3 in DECISIONS.md for why."""
        cells: dict[tuple[int, int], dict[str, int]] = {}

        def cell_for(agent) -> dict[str, int]:
            key = (agent.distance_band, agent.wealth_quartile)
            if key not in cells:
                cells[key] = {
                    "n_searching": 0,
                    "n_long_term": 0,
                    "n_employed": 0,
                    "n_discouraged": 0,
                }
            return cells[key]

        for agent in searching:
            row = cell_for(agent)
            row["n_searching"] += 1
            if agent.months_in_state >= LONG_TERM_THRESHOLD_MONTHS:
                row["n_long_term"] += 1
        for agent in self._seekers(SeekerState.EMPLOYED):
            cell_for(agent)["n_employed"] += 1
        for agent in self._seekers(SeekerState.DISCOURAGED):
            cell_for(agent)["n_discouraged"] += 1

        for (band, quartile), counts in cells.items():
            self.cell_history.append(
                {
                    "step": self.steps,
                    "distance_band": band,
                    "wealth_quartile": quartile,
                    **counts,
                }
            )

    # -- Wealth heterogeneity ----------------------------------------------------------------

    def _draw_capitals(self) -> tuple[list[float], list[int]]:
        """Draws every agent's initial search capital in one pass, then rank-assigns wealth
        quartiles from that single draw -- has to happen before any JobSeeker exists, since
        a quartile is a population-relative statistic and D3 requires it fixed at the
        *initial* draw, never recomputed from an agent's current (post-search) capital."""
        cfg = self.config
        if cfg.initial_capital_spread <= 0:
            capitals = [cfg.initial_search_capital] * cfg.n_agents
            return capitals, [0] * cfg.n_agents

        # Lognormal, not normal: real wealth data is skewed and never negative, and a normal
        # draw would need truncating (which distorts the mean away from initial_search_capital
        # in a way that depends on the spread, quietly breaking calibration's use of that
        # field as a target). Parametrised by coefficient of variation, not raw variance, so
        # initial_capital_spread has a units-free interpretation regardless of the wage scale.
        cv = cfg.initial_capital_spread
        sigma_sq = math.log(1 + cv**2)
        mu = math.log(cfg.initial_search_capital) - sigma_sq / 2
        capitals = [self.rng.lognormal(mu, math.sqrt(sigma_sq)) for _ in range(cfg.n_agents)]

        order = sorted(range(cfg.n_agents), key=lambda i: capitals[i])
        quartiles = [0] * cfg.n_agents
        for rank, idx in enumerate(order):
            quartiles[idx] = min(3, rank * 4 // cfg.n_agents)
        return capitals, quartiles

    # -- Spatial setup ----------------------------------------------------------------------

    def _draw_township_centres(self) -> list[tuple[float, float]]:
        cfg = self.config
        if cfg.n_townships <= 0:
            return []
        centres = []
        for _ in range(cfg.n_townships):
            distance = self.rng.uniform(cfg.township_distance_min, cfg.township_distance_max)
            angle = self.rng.uniform(0.0, 2 * math.pi)
            centres.append((distance * math.cos(angle), distance * math.sin(angle)))
        return centres

    def _draw_home(self) -> tuple[float, float]:
        if not self._township_centres:
            return self.cbd_x, self.cbd_y
        cfg = self.config
        cx, cy = self._township_centres[self.random.randrange(len(self._township_centres))]
        offset_x = self.rng.normal(0.0, cfg.township_spread) if cfg.township_spread > 0 else 0.0
        offset_y = self.rng.normal(0.0, cfg.township_spread) if cfg.township_spread > 0 else 0.0
        return cx + offset_x, cy + offset_y

    def distance_band_for(self, distance: float) -> int:
        """Evenly spaced bins from 0 to township_distance_max, fixed at construction time from
        config alone -- deliberately not population quantiles, which would need every agent's
        home drawn before the first one could be assigned a band. Degenerates to a single band
        (index 0) when the model isn't spatially configured."""
        cfg = self.config
        if cfg.township_distance_max <= 0 or cfg.n_distance_bands <= 1:
            return 0
        band_width = cfg.township_distance_max / cfg.n_distance_bands
        return min(cfg.n_distance_bands - 1, int(distance // band_width))

    def _create_firms(self) -> list[Firm]:
        cfg = self.config
        if cfg.n_firms <= 0:
            return []
        firms = []
        initial_each = cfg.n_vacancies // cfg.n_firms if cfg.n_vacancies else 0
        for _ in range(cfg.n_firms):
            radius = cfg.cbd_radius * math.sqrt(self.rng.uniform(0.0, 1.0))
            angle = self.rng.uniform(0.0, 2 * math.pi)
            x = self.cbd_x + radius * math.cos(angle)
            y = self.cbd_y + radius * math.sin(angle)
            firms.append(Firm(self, x=x, y=y, initial_vacancies=initial_each))
        return firms

    def _update_productivity_shock(self) -> None:
        cfg = self.config
        shock = self.rng.normal(0.0, cfg.sigma_A) if cfg.sigma_A > 0 else 0.0
        log_a = cfg.rho_A * math.log(self.productivity_shock) + shock
        self.productivity_shock = math.exp(log_a)

    def _activate(self, agent_set, method_name: str) -> None:
        """D1: shuffled vs fixed-order activation, toggled from config for the activation-
        order robustness test. In the flat-vacancy-pool MVM (n_firms == 0), every per-agent
        method only reads and writes its own state plus model-level scalars fixed at the start
        of the step, so that path's outcome is order-invariant by construction. That stops
        being true once n_firms > 0: two agents whose search positions both fall within an
        under-supplied firm's radius are now genuinely competing for a scarce local vacancy,
        and which of them gets processed first in a fixed-order run can matter -- which is
        exactly the live regression the switch and test exist to catch."""
        agent_set.shuffle_do(method_name) if self.config.shuffled_activation else agent_set.do(
            method_name
        )

    def step(self) -> None:
        cfg = self.config
        # No manual self.steps increment here -- Mesa's _do_step already does it before
        # calling this method (see the module docstring for why).

        # 1. Separations: employed -> searching (M1). Without this, employment is absorbing.
        employed = self._seekers(SeekerState.EMPLOYED)
        n_searching_pre = len(self._seekers(SeekerState.SEARCHING))
        self._activate(employed, "step_employed")
        n_separations = len(self._seekers(SeekerState.SEARCHING)) - n_searching_pre

        # 2. Re-entry: discouraged -> searching, given this step's household inflow (locked
        #    commitment 6 -- discouragement is not absorbing).
        discouraged = self._seekers(SeekerState.DISCOURAGED)
        n_disc_pre = len(discouraged)
        self._activate(discouraged, "step_discouraged")
        n_reentries = n_disc_pre - len(self._seekers(SeekerState.DISCOURAGED))

        # 3. Capital-exhaustion check, using capital as it stands entering this step -- i.e.
        #    from trips paid for last step. An agent that can no longer afford one trip
        #    becomes discouraged before this period's u_t is recorded, not after. This is one
        #    of the two places a searching spell ends -- record its completed length before
        #    the counter resets.
        searching = self._seekers(SeekerState.SEARCHING)
        n_searching_pre_exhaustion = len(searching)
        for agent in searching:
            if not agent.can_afford_one_trip():
                self._record_completed_spell(agent.months_in_state)
                agent.state = SeekerState.DISCOURAGED
                agent.months_in_state = 0
        searching = self._seekers(SeekerState.SEARCHING)
        n_new_discouraged = n_searching_pre_exhaustion - len(searching)

        # 3.5. Aggregate productivity shock, then firms decide this period's vacancies from
        #      it -- both happen before v_t is recorded, so v_t reflects this period's actual
        #      posting decision, not last period's.
        self._update_productivity_shock()
        for firm in self.firms:
            firm.decide_vacancies()

        # 4. Record start-of-period stocks (D11), strictly before matching runs. The
        #    long-term-share moment and the cell aggregates are stocks in exactly the same
        #    sense as u_t, so they're measured here too, not after matching resolves.
        u_t = len(searching)
        v_t = sum(f.vacancies for f in self.firms) if self.firms else cfg.n_vacancies
        l_t = len(self._seekers(SeekerState.EMPLOYED))
        disc_t = len(self._seekers(SeekerState.DISCOURAGED))
        n_long_term = sum(1 for a in searching if a.months_in_state >= LONG_TERM_THRESHOLD_MONTHS)
        self._collect_cell_row(searching)

        # 5. Trip decisions and payment (the intensity margin, M5). transport_spend is what
        #    moments.py's transport_budget_share moment sums over the burn-in window --
        #    captured here, not recomputed later, because step_searching has already
        #    decremented search_capital by the time this line runs.
        self._activate(searching, "step_searching")
        n_belief_inactive = sum(1 for a in searching if a.belief_inactive_this_step)
        total_trips = sum(a.trips_this_step for a in searching)
        transport_spend = sum(a.trips_this_step * a.cost_per_trip for a in searching)

        # 6. Matching.
        if self.firms:
            m_t = self._match_with_firms(searching)
        else:
            m_t = self._match_flat_pool(searching, v_t)

        # Only update the observed rate when this step actually produced an observation. A
        # step where nobody searched carries no information about the hire rate and should
        # leave the belief where it was -- resetting it to 0.0 here was a second real bug
        # caught in Week 1 testing: it made a temporary all-quiet step permanent.
        if total_trips > 0:
            self.observed_hire_rate_per_trip = m_t / total_trips

        mean_capital = sum(a.search_capital for a in self._seekers()) / cfg.n_agents
        self.history.append(
            {
                "step": self.steps,
                "u": u_t,
                "v": v_t,
                "l": l_t,
                "discouraged": disc_t,
                "n_long_term": n_long_term,
                "m": m_t,
                "total_trips": total_trips,
                "n_separations": n_separations,
                "n_reentries": n_reentries,
                "n_new_discouraged": n_new_discouraged,
                "n_belief_inactive": n_belief_inactive,
                "mean_search_capital": mean_capital,
                "transport_spend": transport_spend,
                "productivity_shock": self.productivity_shock,
            }
        )

        # Deliberately post-matching, not the D11 pre-matching convention the aggregate
        # history uses -- this is a narrative trace, not a calibration input, and a step
        # where an agent gets hired should show state=EMPLOYED at that step, not SEARCHING.
        if self._traced_agents:
            for agent in self._traced_agents:
                self.trace_history.append(
                    {
                        "step": self.steps,
                        "unique_id": agent.unique_id,
                        "state": agent.state.name,
                        "search_capital": agent.search_capital,
                        "months_in_state": agent.months_in_state,
                        "trips_this_step": agent.trips_this_step,
                        "distance_to_cbd": agent.distance_to_cbd,
                    }
                )

    def _match_flat_pool(self, searching, v_t: int) -> int:
        """Week 1's aggregate lottery, unchanged: one ticket per trip, draw min(V, distinct
        candidates) hires without replacement, deduplicated by agent. No equation here says
        vacancy scarcity lowers matching efficiency -- efficiency is recovered later by
        fitting the matching function to the (u, v, m) series this produces (locked
        commitment 1), never assumed in the mechanism itself."""
        candidates = [a for a in searching if a.trips_this_step > 0]
        if not candidates or v_t <= 0:
            return 0
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
            self._record_completed_spell(a.months_in_state)
            a.resolve_hire()
        return len(hired)

    def _match_with_firms(self, searching) -> int:
        """Per-firm neighbourhood matching (n_firms > 0): each searching agent's trips become
        search tickets at effective positions near the CBD (D2's targeting bias); each firm
        hires from tickets within its own radius, up to its own posted vacancy count. Firms
        are processed in a shuffled order each step (via self.random, seeded and
        reproducible) so that when two firms' radii overlap, which one gets first claim on a
        shared candidate isn't a fixed artefact of firm creation order."""
        candidates = [a for a in searching if a.trips_this_step > 0]
        for firm in self.firms:
            firm.hires_this_step = 0
        if not candidates:
            for firm in self.firms:
                firm.update_fill_probability()
            return 0

        tickets: list[tuple[JobSeeker, float, float]] = [
            (agent, x, y) for agent in candidates for x, y in agent.search_positions()
        ]

        hired_ids: set[int] = set()
        total_hired = 0
        firm_order = list(self.firms)
        self.random.shuffle(firm_order)
        for firm in firm_order:
            if firm.vacancies <= 0:
                continue
            local = [
                (agent, x, y)
                for agent, x, y in tickets
                if agent.unique_id not in hired_ids
                and math.hypot(x - firm.x, y - firm.y) <= self.config.firm_radius
            ]
            if not local:
                continue
            self.random.shuffle(local)
            distinct = {agent.unique_id for agent, _, _ in local}
            n_draw = min(firm.vacancies, len(distinct))
            firm_hired: list[JobSeeker] = []
            seen_here: set[int] = set()
            for agent, _, _ in local:
                if len(firm_hired) >= n_draw:
                    break
                if agent.unique_id not in seen_here:
                    firm_hired.append(agent)
                    seen_here.add(agent.unique_id)
            for agent in firm_hired:
                self._record_completed_spell(agent.months_in_state)
                agent.resolve_hire()
                hired_ids.add(agent.unique_id)
            firm.hires_this_step = len(firm_hired)
            total_hired += len(firm_hired)

        for firm in self.firms:
            firm.update_fill_probability()
        return total_hired

    def run(self) -> pd.DataFrame:
        for _ in range(self.config.n_steps):
            self.step()
        return pd.DataFrame(self.history)

    def cell_dataframe(self) -> pd.DataFrame:
        """D3's (distance_band x wealth_quartile x step) aggregates. Empty rows for a cell at
        a step where it happened to hold no agents are simply absent -- callers doing a
        heterogeneity cut should reindex against the full band/quartile product if they need
        explicit zeros."""
        return pd.DataFrame(self.cell_history)

    def completed_spell_dataframe(self) -> pd.DataFrame:
        """D3's descriptive completed-spell histogram, plus the right-censored bucket for
        agents still searching when the run ends -- their spell hasn't completed, but is
        known to be at least months_in_state long. Bucket labels match SPELL_BUCKET_EDGES_MONTHS
        exactly, so this is directly comparable to QLFS's Q36TIMESEEK coding once the real
        moment notebook is written."""
        labels = [
            f"<{SPELL_BUCKET_EDGES_MONTHS[0]}",
            *(
                f"{lo}-{hi}"
                for lo, hi in zip(
                    SPELL_BUCKET_EDGES_MONTHS[:-1], SPELL_BUCKET_EDGES_MONTHS[1:], strict=True
                )
            ),
            f">={SPELL_BUCKET_EDGES_MONTHS[-1]}",
        ]
        rows = [
            {"bucket": label, "censored": False, "count": self.completed_spell_counts[i]}
            for i, label in enumerate(labels)
        ]
        censored_counts: dict[int, int] = {}
        for agent in self._seekers(SeekerState.SEARCHING):
            bucket = self._spell_bucket(agent.months_in_state)
            censored_counts[bucket] = censored_counts.get(bucket, 0) + 1
        for bucket, count in censored_counts.items():
            rows.append({"bucket": labels[bucket], "censored": True, "count": count})
        return pd.DataFrame(rows)

    def trace_dataframe(self) -> pd.DataFrame:
        """The per-agent panel for whichever ids are named in config.trace_agent_ids. Empty
        if none were named -- the trace is opt-in, see the field's docstring in config.py."""
        return pd.DataFrame(self.trace_history)
