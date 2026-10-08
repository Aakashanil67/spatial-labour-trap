"""Run the four search-cost and job-supply scenarios and write tables and figures.

Scenarios (every other parameter at its default), in this order:
    0  Normal cost, 150 jobs     cost_multiplier 1.0
    1  Half cost, 150 jobs       cost_multiplier 0.5
    2  Normal cost, 300 jobs     cost_multiplier 1.0
    3  Half cost, 300 jobs       cost_multiplier 0.5
Each scenario is run with seeds 1000..1029 for periods 0..120. A run is summarised by its mean
over periods 91..120; the scenario summary is the mean and the 10th and 90th percentiles of
those run means across the 30 seeds.

Usage: python -m honours_simple.run --output <directory>
"""

import argparse
import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from matplotlib.colors import to_rgba
from matplotlib.figure import Figure

from honours_simple.model import GROUPS, Params, simulate

REPO_ROOT = Path(__file__).resolve().parent.parent

SCENARIOS = [  # (label, cost_multiplier, jobs); the scenario id is the position in this list
    ("Normal cost, 150 jobs", 1.0, 150),
    ("Half cost, 150 jobs", 0.5, 150),
    ("Normal cost, 300 jobs", 1.0, 300),
    ("Half cost, 300 jobs", 0.5, 300),
]
SEEDS = list(range(1000, 1030))
WINDOW_FIRST, WINDOW_LAST = 91, 120
WORKERS_PER_GROUP = Params().workers_per_group

SCENARIO_COLUMNS = ["scenario_id", "label", "cost_multiplier", "jobs"]
RUN_METRICS = (
    ["employed"]
    + [f"employment_share_{g}" for g in GROUPS]
    + ["hires", "hires_round_1", "hires_round_2", "hires_round_3"]
    + ["open_jobs_after_sep", "jobs_left_open"]
    + [f"apps_per_unemployed_{g}" for g in GROUPS]
    + [f"periods_used_{g}" for g in GROUPS]
)

# Blue family = 150 jobs, orange family = 300 jobs (Okabe-Ito colours, safe for colour blindness).
# Line style and bar hatch differ too, so the scenarios also separate in greyscale.
COLOURS = ["#0072B2", "#56B4E9", "#D55E00", "#E69F00"]
LINESTYLES = ["-", "--", "-.", (0, (3, 1, 1, 1, 1, 1))]
HATCHES = ["", "////", "xxxx", "...."]
FOOTNOTE = "Illustrative parameters; bands/bars show 10th-90th percentile across 30 runs"


def run_all_scenarios():
    """One DataFrame holding every period of every run, with the scenario and seed up front."""
    runs = []
    for scenario_id, (label, cost_multiplier, jobs) in enumerate(SCENARIOS):
        params = Params(cost_multiplier=cost_multiplier, jobs=jobs)
        for seed in SEEDS:
            run = simulate(params, seed)
            identifiers = {
                "scenario_id": scenario_id,
                "label": label,
                "cost_multiplier": cost_multiplier,
                "jobs": jobs,
                "seed": seed,
            }
            for position, (name, value) in enumerate(identifiers.items()):
                run.insert(position, name, value)
            runs.append(run)
    return pd.concat(runs, ignore_index=True)


def summarise_runs(periods):
    """One row per scenario and seed: equal-weight means over the summary window."""
    window = periods[periods["period"].between(WINDOW_FIRST, WINDOW_LAST)].copy()
    window["jobs_left_open"] = window["jobs"] - window["employed"]
    for g in GROUPS:
        window[f"employment_share_{g}"] = window[f"employed_{g}"] / WORKERS_PER_GROUP
        # The ratio is undefined when nobody is unemployed in the group, so those periods become
        # NaN: the mean skips them and they are not counted in periods_used.
        unemployed = window[f"unemployed_after_sep_{g}"]
        ratio = window[f"applications_{g}"] / unemployed.where(unemployed > 0)
        window[f"apps_per_unemployed_{g}"] = ratio
        window[f"periods_used_{g}"] = ratio.notna()

    grouped = window.groupby(SCENARIO_COLUMNS + ["seed"])
    means = grouped[[m for m in RUN_METRICS if not m.startswith("periods_used")]].mean()
    counts = grouped[[m for m in RUN_METRICS if m.startswith("periods_used")]].sum()
    return means.join(counts).reset_index()[SCENARIO_COLUMNS + ["seed"] + RUN_METRICS]


def summarise_scenarios(run_summary):
    """One row per scenario: mean and 10th/90th percentile of each run metric across seeds."""
    grouped = run_summary.groupby(SCENARIO_COLUMNS)
    columns = {"runs": grouped.size()}
    for metric in RUN_METRICS:
        columns[f"{metric}_mean"] = grouped[metric].mean()
        columns[f"{metric}_p10"] = grouped[metric].quantile(0.1)
        columns[f"{metric}_p90"] = grouped[metric].quantile(0.9)
    return pd.DataFrame(columns).reset_index()


def git_output(*args):
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def write_manifest(path):
    manifest = {
        # orig_argv[0] is the launcher's target on Windows venvs, so name the real interpreter
        "command_line": " ".join([sys.executable, *sys.orig_argv[1:]]),
        "git_commit": git_output("rev-parse", "HEAD"),
        "git_working_tree_clean": git_output("status", "--porcelain") == "",
        "versions": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "scenarios": [
            {
                "scenario_id": scenario_id,
                "label": label,
                "params": dataclasses.asdict(Params(cost_multiplier=cost_multiplier, jobs=jobs)),
            }
            for scenario_id, (label, cost_multiplier, jobs) in enumerate(SCENARIOS)
        ],
        "seeds": SEEDS,
        "periods": {"first": 0, "last": Params().periods},
        "summary_window": {"first": WINDOW_FIRST, "last": WINDOW_LAST},
    }
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def write_csv(table, path):
    table.to_csv(path, index=False, lineterminator="\n")  # same bytes on every operating system


def new_figure():
    fig = Figure(figsize=(5.5, 4.2), facecolor="white")
    ax = fig.subplots()
    ax.spines[["top", "right"]].set_visible(False)
    return fig, ax


def save_figure(fig, ax, path, extra_footnotes=()):
    """Legend above the plot, footnote under it, PNG at 200 dpi on white."""
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=2, frameon=False, fontsize=8.5)
    footnotes = [FOOTNOTE, *extra_footnotes]
    fig.subplots_adjust(left=0.15, right=0.97, top=0.84, bottom=0.13 + 0.035 * len(footnotes))
    fig.text(0.02, 0.012, "\n".join(footnotes), fontsize=7.5, color="#444444", va="bottom")
    fig.savefig(path, dpi=200, facecolor="white")


def plot_employment_paths(periods, path):
    by_period = periods.groupby(["scenario_id", "period"])["employed"]
    mean = by_period.mean().unstack("scenario_id")
    p10 = by_period.quantile(0.1).unstack("scenario_id")
    p90 = by_period.quantile(0.9).unstack("scenario_id")

    fig, ax = new_figure()
    for jobs in (150, 300):
        ax.axhline(jobs, color="#666666", linestyle=":", linewidth=1)
        ax.text(Params().periods, jobs + 4, f"{jobs} jobs", fontsize=8, color="#444444", ha="right")
    for scenario_id, (label, _, _) in enumerate(SCENARIOS):
        colour = COLOURS[scenario_id]
        ax.fill_between(mean.index, p10[scenario_id], p90[scenario_id], color=colour, alpha=0.2)
        ax.plot(
            mean.index,
            mean[scenario_id],
            color=colour,
            linestyle=LINESTYLES[scenario_id],
            linewidth=1.8,
            label=label,
        )
    ax.set_xlim(0, Params().periods)
    ax.set_ylim(0, 330)
    ax.set_xlabel("Model period")
    ax.set_ylabel("Workers in a job (mean of 30 runs)")
    save_figure(fig, ax, path)


def plot_group_bars(summary, metric, ylabel, top, path, extra_footnotes=()):
    """Grouped bars: one cluster per worker group, one bar per scenario, with 10-90 error bars."""
    fig, ax = new_figure()
    width = 0.2
    centres = np.arange(len(GROUPS))
    for _, row in summary.iterrows():
        scenario_id = int(row["scenario_id"])
        x = centres + (scenario_id - 1.5) * width
        mean = np.array([row[f"{metric}_{g}_mean"] for g in GROUPS])
        p10 = np.array([row[f"{metric}_{g}_p10"] for g in GROUPS])
        p90 = np.array([row[f"{metric}_{g}_p90"] for g in GROUPS])
        ax.bar(
            x,
            mean,
            width,
            yerr=[mean - p10, p90 - mean],
            color=to_rgba(COLOURS[scenario_id], 0.6),
            edgecolor="black",
            linewidth=0.6,
            hatch=HATCHES[scenario_id],
            capsize=2,
            error_kw={"linewidth": 0.9},
            label=row["label"],
        )
        for bar_x, value in zip(x, mean, strict=True):
            if value == 0:  # a bar of height zero is invisible and would read as missing data
                ax.annotate("0", (bar_x, 0), xytext=(0, 2), textcoords="offset points", ha="center")
    ax.set_xticks(centres, GROUPS)
    ax.set_xlabel("Worker group by distance from the jobs")
    ax.set_ylabel(ylabel)
    ax.set_ylim(bottom=0, top=top)  # top=None keeps the automatic upper limit
    save_figure(fig, ax, path, extra_footnotes)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True, help="directory to write into")
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=True)

    periods = run_all_scenarios()
    run_summary = summarise_runs(periods)
    summary = summarise_scenarios(run_summary)

    write_manifest(output / "manifest.json")
    write_csv(periods, output / "periods.csv")
    write_csv(run_summary, output / "run_summary.csv")
    write_csv(summary, output / "summary.csv")

    window_note = f"Averages over periods {WINDOW_FIRST}-{WINDOW_LAST} of each run."
    plot_employment_paths(periods, output / "fig1_employment_paths.png")
    plot_group_bars(
        summary,
        "employment_share",
        "Share of the group in a job",
        1.0,
        output / "fig2_employment_by_group.png",
        [window_note],
    )
    plot_group_bars(
        summary,
        "apps_per_unemployed",
        "Applications per unemployed worker",
        None,
        output / "fig3_applications_by_group.png",
        [window_note, "Periods with no unemployed worker in the group are excluded."],
    )


if __name__ == "__main__":
    main()
