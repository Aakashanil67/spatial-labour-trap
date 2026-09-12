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
from dataclasses import asdict, dataclass, replace
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
    baseline_n_dropped: int  # zero-u/v/m periods excluded -- see matching.py's own docstring
    frictionless_b_u: float
    frictionless_b_v: float
    frictionless_returns_to_scale: float
    frictionless_wald_pvalue: float
    frictionless_crs_rejected: bool
    frictionless_a_unconstrained: float
    frictionless_a_constrained: float
    frictionless_n_obs: int
    frictionless_n_dropped: int
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
        baseline_n_dropped=b_fit.n_dropped,
        frictionless_b_u=f_fit.b_u,
        frictionless_b_v=f_fit.b_v,
        frictionless_returns_to_scale=f_fit.returns_to_scale,
        frictionless_wald_pvalue=f_fit.wald_pvalue,
        frictionless_crs_rejected=f_fit.crs_rejected,
        frictionless_a_unconstrained=f_fit.a_unconstrained,
        frictionless_a_constrained=f_fit.a_constrained,
        frictionless_n_obs=f_fit.n_obs,
        frictionless_n_dropped=f_fit.n_dropped,
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
        # matching.py drops periods with zero u, v or m before fitting -- disclosed here rather
        # than only in that module's own docstring, since it conditions the regression on a
        # different population than every period the window covers.
        "baseline_n_dropped_periods_total": int(df["baseline_n_dropped"].sum()),
        "frictionless_n_dropped_periods_total": int(df["frictionless_n_dropped"].sum()),
    }

    # The all-seed, unconstrained result is the primary estimate: it uses every seed run, with
    # no outcome-dependent selection. The constrained, CRS-surviving-seeds result is
    # supplementary -- restricting to seeds that pass a constant-returns test is a post-
    # selection problem an interval computed on the surviving seeds does not correct for, even
    # when it is presented alongside the honest count of how many seeds were excluded.
    unconstrained_vals = df["delta_a_unconstrained"].to_numpy()
    summary["primary_delta_a_unconstrained_all_seeds_mean"] = float(unconstrained_vals.mean())
    if n_seeds > 1:
        lo_u, hi_u = np.percentile(unconstrained_vals, [2.5, 97.5])
        # Not a confidence interval for the mean -- the central 95 per cent of this arm's own
        # raw seed outcomes. A CI for the mean would need to account for how that mean varies
        # across repeated sampling, not just where the individual seed draws happen to fall.
        summary["primary_delta_a_unconstrained_all_seeds_central_95pct_range"] = [
            float(lo_u),
            float(hi_u),
        ]

    if n_valid > 0:
        constrained_vals = valid["delta_a_constrained"].to_numpy()
        summary["supplementary_delta_a_constrained_surviving_seeds_mean"] = float(
            constrained_vals.mean()
        )
        summary["supplementary_delta_a_constrained_n_surviving_of_n_run"] = [n_valid, n_seeds]
        if n_valid > 1:
            lo, hi = np.percentile(constrained_vals, [2.5, 97.5])
            summary["supplementary_delta_a_constrained_central_95pct_range"] = [
                float(lo),
                float(hi),
            ]

    if not reportable:
        summary["finding"] = (
            "The assumed Cobb-Douglas matching technology does not survive constant-returns "
            "testing on enough seeds in at least one arm to trust a constrained delta_a -- "
            "reporting one anyway would misrepresent an unidentified quantity as a clean "
            "result. The unconstrained elasticities and intercepts (per-seed CSV) remain the "
            "honest descriptive record of what the fit actually found."
        )

    return df, summary


def load_calibrated_overrides(calibration_result_path: str) -> dict:
    """Reads the "params" object out of a calibration_result.json-shaped file (the format
    src.calibrate._write_published_outputs writes), for overriding a base config's estimated
    parameters. The advertised SQ1 command has always run on configs/baseline.yaml's own
    values, and that file's own header says they are illustrative, not calibrated -- this is
    the path that lets a run use the actually-fitted economy instead."""
    payload = json.loads(Path(calibration_result_path).read_text(encoding="utf-8"))
    return dict(payload["params"])


def _apply_overrides_to_both(
    baseline_config: Config, frictionless_config: Config, overrides: dict
) -> tuple[Config, Config]:
    """Applies the same override dict to both configs. Since assert_single_field_counterfactual
    has already confirmed the two YAML files differ only in transport_cost_rate, and this
    override never touches that field (it carries only the estimated parameters, which
    calibrate.py's PARAM_NAMES never includes transport_cost_rate among), applying it
    identically to both preserves the single-field counterfactual rather than risking a second,
    silent difference between the arms."""
    if "transport_cost_rate" in overrides:
        raise ValueError(
            "a calibrated-parameter override must not include transport_cost_rate -- that is "
            "the one field this comparison is meant to isolate, and overriding it identically "
            "on both arms would silently erase the counterfactual."
        )
    return replace(baseline_config, **overrides), replace(frictionless_config, **overrides)


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
    parser.add_argument(
        "--calibrated-params",
        default=None,
        help=(
            "path to a calibration_result.json to override the base config's estimated "
            "parameters with, on both arms equally -- run against the fitted economy instead "
            "of --baseline's own (illustrative, unless it happens to be the fitted config) "
            "values. Must not itself set transport_cost_rate."
        ),
    )
    args = parser.parse_args(argv)

    assert_single_field_counterfactual(args.baseline, args.frictionless)

    baseline_config = Config.from_yaml(args.baseline)
    frictionless_config = Config.from_yaml(args.frictionless)
    if args.calibrated_params:
        overrides = load_calibrated_overrides(args.calibrated_params)
        baseline_config, frictionless_config = _apply_overrides_to_both(
            baseline_config, frictionless_config, overrides
        )
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
    print(
        f"periods dropped for zero u/v/m: baseline {summary['baseline_n_dropped_periods_total']}, "
        f"frictionless {summary['frictionless_n_dropped_periods_total']} "
        "(matching.py fits only periods where matching happened -- see its own docstring)"
    )
    print()

    # Primary estimate first: every seed run, no outcome-dependent selection.
    primary_range = summary.get("primary_delta_a_unconstrained_all_seeds_central_95pct_range")
    print(
        f"PRIMARY -- unconstrained delta_a, all {summary['n_paired_seeds']} seeds: "
        f"mean={summary['primary_delta_a_unconstrained_all_seeds_mean']:.4f}  "
        f"central 95% of seed outcomes={primary_range}"
    )

    # Supplementary: restricted to seeds surviving the CRS test in both arms. Reported
    # alongside the primary estimate, not in place of it -- selecting on a test outcome and
    # then reporting an interval on the survivors does not correct for that selection.
    if summary["constrained_headline_reportable"]:
        supp_range = summary.get("supplementary_delta_a_constrained_central_95pct_range")
        n_valid, n_run = summary["supplementary_delta_a_constrained_n_surviving_of_n_run"]
        supp_mean = summary["supplementary_delta_a_constrained_surviving_seeds_mean"]
        print(
            f"SUPPLEMENTARY -- constrained delta_a, {n_valid} of {n_run} seeds surviving CRS "
            f"in both arms: mean={supp_mean:.4f}  "
            f"central 95% of surviving-seed outcomes={supp_range}  "
            "(post-selection: these seeds were chosen because they passed a test, not drawn "
            "at random)"
        )
    else:
        print(f"SUPPLEMENTARY -- constrained delta_a NOT reportable: {summary['finding']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
