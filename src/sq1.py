"""Reproducible, one-command SQ1 comparison: does removing spatial friction change the
matching function's fitted efficiency `a`? Paired seeds across a baseline and a frictionless
config, which must differ in `transport_cost_rate` alone -- refused otherwise, since a second
uncontrolled difference is exactly the bug that invalidated the earlier `delta_a=-0.0025`
figure (see DECISIONS.md, "An independent verification found the frictionless config drifted,
and it invalidates delta_a=-0.0025").

Constant returns is tested per seed per arm before any constrained `a` is trusted (matching.py's
own discipline, applied here at the SQ1 level rather than assumed once and reused). The
headline gate: for each arm, an exact one-sided binomial test asks whether that arm's seed-level
CRS rejection rate is higher than the test's own nominal size (alpha) would produce by chance.
If either arm fails that test, no constrained `delta_a` is reported as the SQ1 headline -- the
honest result at that point is that the assumed Cobb-Douglas matching technology does not
survive contact with this ABM, not a number computed anyway and caveated after the fact.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import binomtest

from src.config import Config
from src.matching import fit_matching_function
from src.runner import run_many

ALPHA = 0.05


def _load_raw_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _diff(a: dict, b: dict) -> dict:
    keys = set(a) | set(b)
    return {k: (a.get(k), b.get(k)) for k in keys if a.get(k) != b.get(k)}


def assert_single_field_counterfactual(
    baseline_path: str, frictionless_path: str, field: str = "transport_cost_rate"
) -> None:
    """Refuses to run SQ1 against two configs that differ in anything but `field`. Loaded as
    plain YAML dictionaries, not `Config` instances, so a field one file omits entirely (and
    the other doesn't) is visible rather than hidden behind a shared dataclass default -- the
    same discipline as tests/test_configs.py."""
    baseline_raw = _load_raw_yaml(baseline_path)
    frictionless_raw = _load_raw_yaml(frictionless_path)
    diff = _diff(baseline_raw, frictionless_raw)
    expected = {field: (baseline_raw.get(field), frictionless_raw.get(field))}
    if diff != expected:
        raise ValueError(
            f"{baseline_path} and {frictionless_path} must differ only in {field!r}; found "
            f"{diff}. SQ1 compares matching efficiency at a fixed population with only the "
            "spatial-friction channel switched off -- refusing to run against two configs that "
            "differ in anything else, since that would silently reintroduce the confound "
            "DECISIONS.md already documents one instance of."
        )


@dataclass(frozen=True)
class SeedResult:
    seed: int
    baseline_b_u: float
    baseline_b_v: float
    baseline_returns_to_scale: float
    baseline_wald_pvalue: float
    baseline_crs_rejected: bool
    baseline_a_unconstrained: float
    baseline_a_constrained: float
    baseline_n_obs: int
    frictionless_b_u: float
    frictionless_b_v: float
    frictionless_returns_to_scale: float
    frictionless_wald_pvalue: float
    frictionless_crs_rejected: bool
    frictionless_a_unconstrained: float
    frictionless_a_constrained: float
    frictionless_n_obs: int
    crs_survives_both: bool
    # nan unless crs_survives_both -- a constrained delta_a computed under a rejected CRS
    # assumption in either arm is not a number worth carrying forward, not even for reference.
    delta_a_constrained: float
    delta_a_unconstrained: float  # always computed -- the sensitivity check


def seed_result(
    seed: int,
    baseline_history: pd.DataFrame,
    frictionless_history: pd.DataFrame,
    burn_in_steps: int,
    alpha: float = ALPHA,
) -> SeedResult:
    b_window = baseline_history[baseline_history["step"] > burn_in_steps]
    f_window = frictionless_history[frictionless_history["step"] > burn_in_steps]
    b_fit = fit_matching_function(b_window, alpha=alpha)
    f_fit = fit_matching_function(f_window, alpha=alpha)
    crs_survives_both = not b_fit.crs_rejected and not f_fit.crs_rejected

    return SeedResult(
        seed=seed,
        baseline_b_u=b_fit.b_u,
        baseline_b_v=b_fit.b_v,
        baseline_returns_to_scale=b_fit.returns_to_scale,
        baseline_wald_pvalue=b_fit.wald_pvalue,
        baseline_crs_rejected=b_fit.crs_rejected,
        baseline_a_unconstrained=b_fit.a_unconstrained,
        baseline_a_constrained=b_fit.a_constrained,
        baseline_n_obs=b_fit.n_obs,
        frictionless_b_u=f_fit.b_u,
        frictionless_b_v=f_fit.b_v,
        frictionless_returns_to_scale=f_fit.returns_to_scale,
        frictionless_wald_pvalue=f_fit.wald_pvalue,
        frictionless_crs_rejected=f_fit.crs_rejected,
        frictionless_a_unconstrained=f_fit.a_unconstrained,
        frictionless_a_constrained=f_fit.a_constrained,
        frictionless_n_obs=f_fit.n_obs,
        crs_survives_both=crs_survives_both,
        delta_a_constrained=(b_fit.a_constrained - f_fit.a_constrained)
        if crs_survives_both
        else float("nan"),
        delta_a_unconstrained=b_fit.a_unconstrained - f_fit.a_unconstrained,
    )


def run_sq1(
    baseline_config: Config,
    frictionless_config: Config,
    seeds: list[int],
    alpha: float = ALPHA,
) -> tuple[pd.DataFrame, dict]:
    """Runs both configs at every seed (each independently cached), fits the matching function
    per seed per arm, and applies the CRS reporting gate. Returns the full per-seed table and
    the summary dict, both written verbatim by main()."""
    baseline_histories = run_many(baseline_config, seeds)
    frictionless_histories = run_many(frictionless_config, seeds)
    burn_in = baseline_config.burn_in_steps

    results = [
        seed_result(seed, b_hist, f_hist, burn_in, alpha)
        for seed, b_hist, f_hist in zip(
            seeds, baseline_histories, frictionless_histories, strict=True
        )
    ]
    df = pd.DataFrame([asdict(r) for r in results])

    n_seeds = len(seeds)
    baseline_rejections = int(df["baseline_crs_rejected"].sum())
    frictionless_rejections = int(df["frictionless_crs_rejected"].sum())
    # Exact one-sided test: is this arm's rejection rate higher than the test's own nominal
    # size (alpha) would produce under repeated sampling if CRS genuinely held everywhere?
    baseline_binom = binomtest(baseline_rejections, n_seeds, alpha, alternative="greater")
    frictionless_binom = binomtest(frictionless_rejections, n_seeds, alpha, alternative="greater")
    either_arm_fails = baseline_binom.pvalue < alpha or frictionless_binom.pvalue < alpha

    valid = df[df["crs_survives_both"]]
    n_valid = len(valid)
    reportable = bool(not either_arm_fails and n_valid > 0)

    summary: dict = {
        "n_paired_seeds": n_seeds,
        "alpha": alpha,
        "baseline_crs_rejections": baseline_rejections,
        "frictionless_crs_rejections": frictionless_rejections,
        "baseline_binomial_pvalue": float(baseline_binom.pvalue),
        "frictionless_binomial_pvalue": float(frictionless_binom.pvalue),
        "n_valid_paired_crs_comparisons": n_valid,
        "constrained_headline_reportable": reportable,
    }

    if n_valid > 0:
        constrained_vals = valid["delta_a_constrained"].to_numpy()
        summary["paired_delta_a_constrained_mean"] = float(constrained_vals.mean())
        if n_valid > 1:
            lo, hi = np.percentile(constrained_vals, [2.5, 97.5])
            summary["paired_delta_a_constrained_ci_95"] = [float(lo), float(hi)]

    unconstrained_vals = df["delta_a_unconstrained"].to_numpy()
    summary["paired_delta_a_unconstrained_mean"] = float(unconstrained_vals.mean())
    if n_seeds > 1:
        lo_u, hi_u = np.percentile(unconstrained_vals, [2.5, 97.5])
        summary["paired_delta_a_unconstrained_ci_95"] = [float(lo_u), float(hi_u)]

    if not reportable:
        summary["finding"] = (
            "The assumed Cobb-Douglas matching technology does not survive constant-returns "
            "testing on enough seeds in at least one arm to trust a constrained delta_a -- "
            "reporting one anyway would misrepresent an unidentified quantity as a clean "
            "result. The unconstrained elasticities and intercepts (per-seed CSV) remain the "
            "honest descriptive record of what the fit actually found."
        )

    return df, summary


def _parse_seed_spec(spec: str) -> list[int]:
    if ":" in spec:
        lo, hi = spec.split(":", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(spec)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reproducible, paired-seed SQ1 (matching-efficiency) comparison."
    )
    parser.add_argument("--baseline", required=True, help="path to the baseline config YAML")
    parser.add_argument(
        "--frictionless", required=True, help="path to the frictionless config YAML"
    )
    parser.add_argument("--seeds", required=True, help='e.g. "1:20" or a single integer')
    parser.add_argument("--out-dir", default="results/published")
    parser.add_argument("--alpha", type=float, default=ALPHA)
    args = parser.parse_args(argv)

    assert_single_field_counterfactual(args.baseline, args.frictionless)

    baseline_config = Config.from_yaml(args.baseline)
    frictionless_config = Config.from_yaml(args.frictionless)
    seeds = _parse_seed_spec(args.seeds)

    df, summary = run_sq1(baseline_config, frictionless_config, seeds, alpha=args.alpha)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "sq1_seed_results.csv", index=False)
    (out_dir / "sq1_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"paired seeds: {summary['n_paired_seeds']}  (alpha={summary['alpha']})")
    for _, row in df.iterrows():
        if row["baseline_crs_rejected"]:
            print(
                f"  seed {int(row['seed'])}: baseline CRS rejected "
                f"(Wald p={row['baseline_wald_pvalue']:.4f})"
            )
        if row["frictionless_crs_rejected"]:
            print(
                f"  seed {int(row['seed'])}: frictionless CRS rejected "
                f"(Wald p={row['frictionless_wald_pvalue']:.4f})"
            )
    print(
        f"baseline CRS rejections: {summary['baseline_crs_rejections']}/"
        f"{summary['n_paired_seeds']} (binomial p={summary['baseline_binomial_pvalue']:.4f})"
    )
    print(
        f"frictionless CRS rejections: {summary['frictionless_crs_rejections']}/"
        f"{summary['n_paired_seeds']} (binomial p={summary['frictionless_binomial_pvalue']:.4f})"
    )
    print()
    if summary["constrained_headline_reportable"]:
        ci = summary.get("paired_delta_a_constrained_ci_95")
        print(
            f"constrained delta_a (n={summary['n_valid_paired_crs_comparisons']}): "
            f"mean={summary['paired_delta_a_constrained_mean']:.4f}  95% CI={ci}"
        )
    else:
        print(f"HEADLINE: constrained delta_a NOT reportable -- {summary['finding']}")
    print(
        f"unconstrained delta_a (sensitivity, all {summary['n_paired_seeds']} seeds): "
        f"mean={summary['paired_delta_a_unconstrained_mean']:.4f}  "
        f"95% CI={summary.get('paired_delta_a_unconstrained_ci_95')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
