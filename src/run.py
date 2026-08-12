"""Headless CLI entry point: python -m src.run --config configs/mvm.yaml

Prints a summary to stdout by default. --out is opt-in and writes the full tidy DataFrame to
a CSV -- deliberately not automatic, since results/ isn't gitignored wholesale (only
results/cache/ and results/figures/ are; see I4 in DECISIONS.md for what's meant to stay
committed), and an ad-hoc run shouldn't end up staged by accident.
"""

from __future__ import annotations

import argparse
import sys

from src.config import Config
from src.model import CityModel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the spatial labour trap model headlessly.")
    parser.add_argument("--config", required=True, help="path to a YAML config file")
    parser.add_argument("--out", help="optional path to write the full tidy DataFrame as CSV")
    args = parser.parse_args(argv)

    config = Config.from_yaml(args.config)
    model = CityModel(config)
    history = model.run()

    if args.out:
        history.to_csv(args.out, index=False)
        print(f"wrote {len(history)} rows to {args.out}")

    tail = history.tail(int(config.n_steps * 0.3))
    unemployment_rate = (tail["u"] / config.n_agents).mean()
    discouraged_share = (tail["discouraged"] / config.n_agents).mean()

    print(f"config: {args.config}  (seed={config.seed}, n_agents={config.n_agents})")
    print(f"steps run: {len(history)}")
    print(f"mean unemployment rate, last 30% of run: {unemployment_rate:.4f}")
    print(f"mean discouraged share, last 30% of run: {discouraged_share:.4f}")
    print(f"total hires over run: {history['m'].sum()}")
    print(f"total re-entries over run: {history['n_reentries'].sum()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
