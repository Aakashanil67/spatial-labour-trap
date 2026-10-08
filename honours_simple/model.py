from dataclasses import dataclass

import numpy as np
import pandas as pd

GROUPS = ("near", "middle", "far")


@dataclass(frozen=True)
class Params:
    workers_per_group: int = 100
    distances: tuple[int, ...] = (1, 2, 3)  # near, middle, far
    cost_per_distance: float = 1.2
    cost_multiplier: float = 1.0  # 0.5 = cheaper search
    allowance: float = 3.0
    max_applications: int = 3
    jobs: int = 150
    separation_prob: float = 0.03
    periods: int = 120


def group_of_workers(params):
    return np.repeat(np.arange(len(params.distances)), params.workers_per_group)


def application_limits(params):
    """Applications a worker can afford per period: allowance / cost of one, rounded down."""
    cost = params.cost_multiplier * params.cost_per_distance * np.array(params.distances)
    by_group = np.minimum(params.max_applications, np.floor(params.allowance / cost))
    return by_group.astype(int)[group_of_workers(params)]


def match_round(applicants, open_jobs, rng):
    """One round: each applicant applies to one open job at random; each job hires one applicant.

    Shuffling first matters. Taking the first applicant listed for each job would always favour
    low worker ids; after a random shuffle the first one is uniform among that job's applicants.
    """
    if len(applicants) == 0 or len(open_jobs) == 0:
        return np.array([], dtype=int), np.array([], dtype=int)
    applicants = rng.permutation(applicants)
    applied_to = rng.choice(open_jobs, size=len(applicants))
    filled_jobs, first = np.unique(applied_to, return_index=True)
    return applicants[first], filled_jobs


def by_group(per_worker, group):
    return np.bincount(group, weights=per_worker, minlength=len(GROUPS)).astype(int)


def with_groups(name, counts):
    """The total as `name` plus one column per group, e.g. employed, employed_near, ..."""
    columns = {name: counts.sum()}
    for group_name, count in zip(GROUPS, counts, strict=True):
        columns[f"{name}_{group_name}"] = count
    return columns


def make_row(period, employed, unemployed, open_jobs, separations, hires_by_round, applications):
    return {
        "period": period,
        **with_groups("employed", employed),
        **with_groups("unemployed_after_sep", unemployed),
        "open_jobs_after_sep": open_jobs,
        "separations": separations,
        "hires": sum(hires_by_round),
        "hires_round_1": hires_by_round[0],
        "hires_round_2": hires_by_round[1],
        "hires_round_3": hires_by_round[2],
        **with_groups("applications", applications),
    }


def simulate(params, seed):
    """Run one economy and return one row per period, 0..periods.

    Order within a period: separations, then up to max_applications matching rounds. A worker
    who loses a job applies again the same period; a worker hired this period cannot lose the
    job before next period, because separations are drawn before any hiring.
    """
    rng = np.random.default_rng(seed)
    group = group_of_workers(params)
    limits = application_limits(params)
    job_of_worker = np.full(len(group), -1)  # -1 = unemployed
    job_filled = np.zeros(params.jobs, dtype=bool)

    no_flows = np.zeros(len(GROUPS), dtype=int)
    rows = [
        make_row(
            0, no_flows, by_group(job_of_worker < 0, group), params.jobs, 0, [0, 0, 0], no_flows
        )
    ]

    for t in range(1, params.periods + 1):
        employed_ids = np.flatnonzero(job_of_worker >= 0)
        lose_job = rng.random(len(employed_ids)) < params.separation_prob
        separated = employed_ids[lose_job]
        job_filled[job_of_worker[separated]] = False
        job_of_worker[separated] = -1

        unemployed = by_group(job_of_worker < 0, group)
        open_after_sep = int((~job_filled).sum())

        remaining = np.where(job_of_worker < 0, limits, 0)
        made = np.zeros(len(group), dtype=int)
        hires_by_round = [0, 0, 0]  # the output has columns for three rounds
        for r in range(params.max_applications):
            # a worker hired in an earlier round of this period stops applying
            eligible = np.flatnonzero((job_of_worker < 0) & (remaining > 0))
            open_jobs = np.flatnonzero(~job_filled)
            if len(eligible) == 0 or len(open_jobs) == 0:
                break
            hired, filled = match_round(eligible, open_jobs, rng)
            remaining[eligible] -= 1
            made[eligible] += 1
            job_of_worker[hired] = filled
            job_filled[filled] = True
            hires_by_round[r] = len(hired)

        employed = by_group(job_of_worker >= 0, group)
        applications = by_group(made, group)
        rows.append(
            make_row(
                t,
                employed,
                unemployed,
                open_after_sep,
                len(separated),
                hires_by_round,
                applications,
            )
        )

    return pd.DataFrame(rows)
