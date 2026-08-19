"""One-at-a-time response surfaces around a published calibration point.

This exists because of a gap the Week 4 audit found in the project's own evidence: the response
surface carrying the headline `long_term_share` finding -- that the moment is unreachable rather
than merely unfitted, which is what decides whether Week 5 policy work proceeds -- was generated
by a throwaway inline script and committed with no provenance. Under the I4 fresh-clone
contract, a committed result that no committed code can regenerate is exactly the artefact class
that contract exists to catch. See DECISIONS.md, "The response surface had no committed
generator".

The default axes are the diagnostic set that surface documents: `firm_radius` across its full
calibration box, plus the two robustness axes the remediation plan names (`separation_rate` and
`household_inflow`). Week 5's full sensitivity sweep (prompt 4.3) is the same machinery over a
longer axis table -- add rows to DEFAULT_AXES rather than writing a second module.

Every axis value is a plain `Config` field override applied on top of the calibrated point, so
the four calibrated parameters and the two fixed robustness axes are handled identically; there
is no separate code path for "a calibrated parameter" versus "a config field".
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.calibrate import (
    MOMENT_KEYS,
    git_commit_hash,
    load_empirical_moments,
    sha256_file,
    simulate_moments,
)
from src.config import Config

# firm_radius and firm_kappa span their full calibration boxes (see calibrate.py's
# DEFAULT_BOUNDS and, for firm_radius, the geometric identification limit that sets its 4.0
# ceiling). The other two bracket their baseline values by roughly a factor of two either way --
# wide enough that a moment with any real gradient along them would visibly move, which is the
# whole point of the diagnostic.
#
# firm_kappa was missing from the original diagnostic set, which is a gap, not a deliberate
# omission: Pissarides (2000)'s free-entry condition (p - w = (r + lambda) * pc / q(theta),
# cited directly in Firm's own docstring in agents.py) ties expected match duration to market
# tightness theta = v/u, and firm_kappa is this model's own tightness dial -- it scales
# decide_vacancies's posting target directly, so it is the parameter most likely, on the
# model's own free-entry logic, to move long_term_share if anything in the current four can.
# Added to test that before concluding the moment is unreachable within the current parameter
# set (see DECISIONS.md, "What actually identifies what, after the corrected campaign").
DEFAULT_AXES: dict[str, tuple[float, ...]] = {
    "firm_radius": (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0),
    "firm_kappa": (0.2, 0.5, 0.8, 1.1, 1.4, 1.7, 2.0),
    "separation_rate": (0.015, 0.0296, 0.045, 0.06),
    "household_inflow": (0.004, 0.008, 0.016, 0.032),
}

# Five is enough to average out simulation noise for a shape diagnostic, and deliberately far
# fewer than a calibration evaluation's 15 -- this sweep answers "does the moment move at all",
# not "what is its precise level".
DEFAULT_SWEEP_SEEDS: tuple[int, ...] = (1, 2, 3, 4, 5)


def sweep(
    base: Config,
    centre: dict[str, float],
    axes: dict[str, tuple[float, ...]] = DEFAULT_AXES,
    seeds: tuple[int, ...] = DEFAULT_SWEEP_SEEDS,
) -> dict[str, list[dict]]:
    """For each axis, hold every other field at `centre` and walk that one field's values,
    recording all four simulated moments at each point."""
    surfaces: dict[str, list[dict]] = {}
    for field, values in axes.items():
        points = []
        for value in values:
            params = dict(centre)
            params[field] = value
            simulated = simulate_moments(base, params, seeds)
            points.append(
                {
                    "value": value,
                    "moments": {key: simulated[key][0] for key in MOMENT_KEYS},
                }
            )
        surfaces[field] = points
    return surfaces


def _gradient_is_identically_zero(points: list[dict], key: str) -> bool:
    values = [p["moments"][key] for p in points]
    return all(v == values[0] for v in values)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Response surfaces around a published calibration point."
    )
    parser.add_argument("--config", required=True, help="base YAML config the campaign used")
    parser.add_argument(
        "--calibration",
        default="results/published/calibration_result.json",
        help="calibration_result.json to read the centre point from",
    )
    parser.add_argument("--moments", default="data/moments.csv")
    parser.add_argument("--out", default="results/published/long_term_share_response_surface.json")
    args = parser.parse_args(argv)

    base = Config.from_yaml(args.config)
    calibration = json.loads(Path(args.calibration).read_text(encoding="utf-8"))
    centre = calibration["params"]
    empirical = load_empirical_moments(args.moments)

    surfaces = sweep(base, centre, seeds=DEFAULT_SWEEP_SEEDS)

    record = {
        "fingerprint": {
            "code_commit": git_commit_hash(),
            "moments_csv_sha256": sha256_file(args.moments),
            "config_path": args.config,
            "config_canonical_json": base.canonical_json(),
            "sweep_seeds": list(DEFAULT_SWEEP_SEEDS),
            "centre_from": args.calibration,
            "centre_code_commit": calibration["fingerprint"]["code_commit"],
        },
        "centre_params": centre,
        "empirical_targets": empirical.values,
        "surfaces": surfaces,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")

    print(f"centre point (from {args.calibration}):")
    for name, value in centre.items():
        print(f"  {name} = {value:.6f}")
    print()
    for field, points in surfaces.items():
        print(f"{field}:")
        for p in points:
            moments = "  ".join(f"{k}={p['moments'][k]:+.4f}" for k in MOMENT_KEYS)
            print(f"  {field}={p['value']:<8g} {moments}")
        flat = [k for k in MOMENT_KEYS if _gradient_is_identically_zero(points, k)]
        if flat:
            print(f"  -> identically flat along this axis: {', '.join(flat)}")
        print()
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
