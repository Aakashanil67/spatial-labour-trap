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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Produce the four-panel diagnostics figure.")
    parser.add_argument("--config", required=True, help="path to a YAML config file")
    parser.add_argument(
        "--out",
        default="results/figures/diagnostics.png",
        help="output path for the figure (default: results/figures/diagnostics.png)",
    )
    args = parser.parse_args(argv)

    config = Config.from_yaml(args.config)
    history = CityModel(config).run()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig = plot_diagnostics(history, config.n_agents, title=Path(args.config).stem)
    fig.savefig(out_path, dpi=150)
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
