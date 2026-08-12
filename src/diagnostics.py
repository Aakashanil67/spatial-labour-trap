"""Four-panel sanity figure: unemployment rate, discouraged share, matches per period, mean
remaining search capital. Per prompt 2.2 -- eyeball pathologies before adding complexity."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from src.config import Config
from src.model import CityModel


def plot_diagnostics(history: pd.DataFrame, n_agents: int, title: str = "") -> plt.Figure:
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    step = history["step"]

    ax = axes[0, 0]
    ax.plot(step, history["u"] / n_agents)
    ax.set_title("Unemployment rate")
    ax.set_xlabel("step")
    ax.set_ylim(bottom=0)

    ax = axes[0, 1]
    ax.plot(step, history["discouraged"] / n_agents, color="tab:red")
    ax.set_title("Discouraged share")
    ax.set_xlabel("step")
    ax.set_ylim(bottom=0)

    ax = axes[1, 0]
    ax.plot(step, history["m"], color="tab:green")
    ax.set_title("Matches per period")
    ax.set_xlabel("step")
    ax.set_ylim(bottom=0)

    ax = axes[1, 1]
    ax.plot(step, history["mean_search_capital"], color="tab:purple")
    ax.set_title("Mean remaining search capital")
    ax.set_xlabel("step")
    ax.set_ylim(bottom=0)

    if title:
        fig.suptitle(title)
    fig.tight_layout()
    return fig


_STATE_COLOURS = {
    "SEARCHING": "#c6e6c6",
    "DISCOURAGED": "#f6c6c6",
    "EMPLOYED": "#c6d6f6",
}


def plot_agent_trajectory(trace: pd.DataFrame, agent_id: int, title: str = "") -> plt.Figure:
    """Locked commitment 6 (discouragement is not absorbing) as a picture, not just an
    assertion in a config comment -- search capital draining while SEARCHING, hitting the
    hard DISCOURAGED state, refilling from the household inflow while discouraged, and
    re-entering. State bands are shaded background spans, not a second line, so the capital
    trajectory itself stays the clearest thing in the figure."""
    g = trace[trace["unique_id"] == agent_id].sort_values("step")
    if g.empty:
        raise ValueError(f"agent {agent_id} not found in trace -- check config.trace_agent_ids")

    fig, ax = plt.subplots(figsize=(11, 4))
    steps = g["step"].to_numpy()
    states = g["state"].to_numpy()

    # Collapse consecutive identical states into spans so each transition gets exactly one
    # axvspan call, not one per step -- a run of 40 EMPLOYED steps is one coloured block.
    span_start = steps[0]
    for i in range(1, len(states) + 1):
        if i == len(states) or states[i] != states[i - 1]:
            span_end = steps[i] if i < len(states) else steps[-1] + 1
            ax.axvspan(
                span_start, span_end, color=_STATE_COLOURS.get(states[i - 1], "#eeeeee"), alpha=0.6
            )
            if i < len(states):
                span_start = steps[i]

    ax.plot(steps, g["search_capital"], color="black", linewidth=1.5)
    ax.set_xlabel("step (month)")
    ax.set_ylabel("search capital")
    ax.set_ylim(bottom=0)
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=colour, alpha=0.6) for colour in _STATE_COLOURS.values()
    ]
    ax.legend(handles, _STATE_COLOURS.keys(), loc="upper right", framealpha=0.9)
    ax.set_title(
        title or f"Agent {agent_id}: search capital through search, discouragement, re-entry"
    )
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Produce the four-panel diagnostics figure.")
    parser.add_argument("--config", required=True, help="path to a YAML config file")
    parser.add_argument(
        "--out",
        default="results/figures/diagnostics.png",
        help="output path for the figure (default: results/figures/diagnostics.png)",
    )
    parser.add_argument(
        "--trace-agent",
        type=int,
        default=None,
        help="also produce the single-agent trajectory figure for this agent id "
        "(must be in config.trace_agent_ids)",
    )
    parser.add_argument(
        "--trace-out",
        default="results/figures/agent_trajectory.png",
        help="output path for the trajectory figure",
    )
    args = parser.parse_args(argv)

    config = Config.from_yaml(args.config)
    model = CityModel(config)
    history = model.run()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig = plot_diagnostics(history, config.n_agents, title=Path(args.config).stem)
    fig.savefig(out_path, dpi=150)
    print(f"wrote {out_path}")

    if args.trace_agent is not None:
        trace = model.trace_dataframe()
        trace_fig = plot_agent_trajectory(trace, args.trace_agent)
        trace_out = Path(args.trace_out)
        trace_out.parent.mkdir(parents=True, exist_ok=True)
        trace_fig.savefig(trace_out, dpi=150)
        print(f"wrote {trace_out}")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
