"""Tests for src/sq1.py. Most of these exercise the pure aggregation and gating logic directly
against synthetic (u, v, m) windows -- matching.py's own correctness (recovering a known
Cobb-Douglas fit) is already covered in tests/test_matching.py, so these tests are about SQ1's
own responsibilities: refusing a bad config pair, building the per-seed record correctly, and
applying the binomial CRS gate -- not re-proving the regression itself.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
import yaml

from src.sq1 import (
    ALPHA,
    assert_single_field_counterfactual,
    main,
    run_sq1,
    seed_result,
)


def _synthetic_history(a: float, b_u: float, b_v: float, n: int, seed: int, noise_sd: float = 0.0):
    """Same construction as test_matching.py's _synthetic_window, with a `step` column added
    so seed_result's burn_in_steps filter has something to filter on."""
    rng = np.random.default_rng(seed)
    log_u = rng.uniform(2.0, 5.0, size=n)
    log_v = rng.uniform(2.0, 5.0, size=n)
    noise = rng.normal(0.0, noise_sd, size=n) if noise_sd else 0.0
    log_m = np.log(a) + b_u * log_u + b_v * log_v + noise
    return pd.DataFrame(
        {
            "step": np.arange(1, n + 1),
            "u": np.exp(log_u),
            "v": np.exp(log_v),
            "m": np.exp(log_m),
        }
    )


def _write_yaml(path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)
    return path


_BASE_FIELDS = {
    "n_agents": 500,
    "n_vacancies": 15,
    "initial_search_capital": 0.6,
    "search_cost_per_trip": 0.02,
    "separation_rate": 0.03,
    "belief_multiplier": 1.0,
    "household_inflow": 0.008,
    "reentry_threshold": 0.035,
    "max_trips_per_step": 3,
    "n_steps": 150,
    "seed": 42,
    "transport_cost_rate": 0.004,
    "burn_in_steps": 50,
}


def test_assert_single_field_counterfactual_passes_on_the_real_configs():
    assert_single_field_counterfactual("configs/baseline.yaml", "configs/frictionless.yaml")


def test_assert_single_field_counterfactual_raises_on_a_second_difference(tmp_path):
    baseline = _write_yaml(tmp_path / "baseline.yaml", _BASE_FIELDS)
    drifted_fields = dict(_BASE_FIELDS, transport_cost_rate=0.0, firm_kappa=0.9)
    frictionless = _write_yaml(tmp_path / "frictionless.yaml", drifted_fields)
    with pytest.raises(ValueError, match="transport_cost_rate"):
        assert_single_field_counterfactual(str(baseline), str(frictionless))


def test_assert_single_field_counterfactual_raises_when_only_a_different_field_changed(tmp_path):
    """A config pair that differs in, say, separation_rate but NOT transport_cost_rate is not
    a frictionless counterfactual at all -- must still be refused, not silently accepted because
    the offending field happens to differ from the one this check is named after."""
    baseline = _write_yaml(tmp_path / "baseline.yaml", _BASE_FIELDS)
    drifted_fields = dict(_BASE_FIELDS, separation_rate=0.05)
    frictionless = _write_yaml(tmp_path / "frictionless.yaml", drifted_fields)
    with pytest.raises(ValueError):
        assert_single_field_counterfactual(str(baseline), str(frictionless))


def test_seed_result_flags_crs_survives_both_only_when_neither_arm_rejects():
    crs_history = _synthetic_history(a=0.4, b_u=0.55, b_v=0.45, n=200, seed=2, noise_sd=0.01)
    non_crs_history = _synthetic_history(a=0.4, b_u=0.8, b_v=0.5, n=200, seed=3, noise_sd=0.01)

    both_crs = seed_result(1, crs_history, crs_history.copy(), burn_in_steps=0)
    assert not both_crs.baseline_crs_rejected
    assert not both_crs.frictionless_crs_rejected
    assert both_crs.crs_survives_both
    assert both_crs.delta_a_constrained == both_crs.delta_a_constrained  # not nan

    one_fails = seed_result(2, non_crs_history, crs_history.copy(), burn_in_steps=0)
    assert one_fails.baseline_crs_rejected
    assert not one_fails.crs_survives_both
    assert one_fails.delta_a_constrained != one_fails.delta_a_constrained  # nan
    # the unconstrained sensitivity figure is still computed even when CRS fails
    assert one_fails.delta_a_unconstrained == one_fails.delta_a_unconstrained  # not nan


def test_seed_result_respects_burn_in_steps():
    """A window with garbage in its first few 'steps' must be excluded, exactly like
    moments.py's own burn-in convention -- confirmed by making the pre-burn-in rows violate the
    Cobb-Douglas relationship entirely and checking the fit still recovers the true parameters
    from the clean post-burn-in rows alone."""
    clean = _synthetic_history(a=0.4, b_u=0.55, b_v=0.45, n=200, seed=5, noise_sd=0.0)
    clean["step"] = clean["step"] + 10  # steps 11..210
    garbage = pd.DataFrame({"step": range(1, 11), "u": [1] * 10, "v": [1] * 10, "m": [999] * 10})
    history = pd.concat([garbage, clean], ignore_index=True)

    result = seed_result(1, history, history.copy(), burn_in_steps=10)
    assert result.baseline_b_u == pytest.approx(0.55, abs=1e-6)
    assert result.baseline_b_v == pytest.approx(0.45, abs=1e-6)


def _fake_run_many_factory(histories_by_config_and_seed):
    def _fake_run_many(config, seeds, n_jobs=None):
        return [histories_by_config_and_seed[(config.seed, seed)] for seed in seeds]

    return _fake_run_many


def test_run_sq1_gates_the_constrained_headline_when_an_arm_fails_too_often(monkeypatch):
    """If an arm's CRS rejection rate is high enough that the binomial test rejects "this is
    just the test's own 5% false-positive rate," the constrained delta_a must not be reported
    as the headline -- even though it's still numerically computable for the seeds that did
    pass."""
    from src.config import Config

    seeds = list(range(1, 11))
    crs = {
        s: _synthetic_history(a=0.4, b_u=0.55, b_v=0.45, n=200, seed=100 + s, noise_sd=0.01)
        for s in seeds
    }
    non_crs = {
        s: _synthetic_history(a=0.4, b_u=0.8, b_v=0.5, n=200, seed=200 + s, noise_sd=0.01)
        for s in seeds
    }
    # baseline arm fails CRS on every seed; frictionless always passes.
    histories = {}
    for s in seeds:
        histories[(1, s)] = non_crs[s]
        histories[(2, s)] = crs[s]

    monkeypatch.setattr("src.sq1.run_many", _fake_run_many_factory(histories))

    baseline_cfg = Config(
        n_agents=10,
        n_vacancies=1,
        initial_search_capital=0.6,
        search_cost_per_trip=0.02,
        separation_rate=0.03,
        belief_multiplier=1.0,
        household_inflow=0.008,
        reentry_threshold=0.035,
        max_trips_per_step=3,
        n_steps=10,
        seed=1,
        burn_in_steps=0,
    )
    frictionless_cfg = baseline_cfg.__class__(**{**baseline_cfg.__dict__, "seed": 2})

    df, summary = run_sq1(baseline_cfg, frictionless_cfg, seeds)
    assert summary["baseline_crs_rejections"] == 10
    assert summary["baseline_binomial_pvalue"] < ALPHA
    assert summary["constrained_headline_reportable"] is False
    assert "finding" in summary
    assert len(df) == 10


def test_run_sq1_reports_a_constrained_headline_when_crs_holds_everywhere(monkeypatch):
    from src.config import Config

    seeds = list(range(1, 6))
    histories = {}
    for s in seeds:
        h = _synthetic_history(a=0.4, b_u=0.55, b_v=0.45, n=200, seed=100 + s, noise_sd=0.01)
        histories[(1, s)] = h
        histories[(2, s)] = h.copy()

    monkeypatch.setattr("src.sq1.run_many", _fake_run_many_factory(histories))

    baseline_cfg = Config(
        n_agents=10,
        n_vacancies=1,
        initial_search_capital=0.6,
        search_cost_per_trip=0.02,
        separation_rate=0.03,
        belief_multiplier=1.0,
        household_inflow=0.008,
        reentry_threshold=0.035,
        max_trips_per_step=3,
        n_steps=10,
        seed=1,
        burn_in_steps=0,
    )
    frictionless_cfg = baseline_cfg.__class__(**{**baseline_cfg.__dict__, "seed": 2})

    df, summary = run_sq1(baseline_cfg, frictionless_cfg, seeds)
    assert summary["baseline_crs_rejections"] == 0
    assert summary["constrained_headline_reportable"] is True
    assert summary["n_valid_paired_crs_comparisons"] == 5
    assert summary["paired_delta_a_constrained_mean"] == pytest.approx(0.0, abs=1e-9)


def test_main_writes_csv_and_json_and_refuses_a_bad_config_pair(tmp_path, monkeypatch):
    baseline_path = _write_yaml(tmp_path / "baseline.yaml", _BASE_FIELDS)
    drifted = dict(_BASE_FIELDS, separation_rate=0.06)  # a second, uncontrolled difference
    frictionless_path = _write_yaml(tmp_path / "frictionless.yaml", drifted)

    with pytest.raises(ValueError):
        main(
            [
                "--baseline",
                str(baseline_path),
                "--frictionless",
                str(frictionless_path),
                "--seeds",
                "1:3",
                "--out-dir",
                str(tmp_path / "out"),
            ]
        )

    good_frictionless_path = _write_yaml(
        tmp_path / "frictionless_ok.yaml", dict(_BASE_FIELDS, transport_cost_rate=0.0)
    )

    def _fake_run_many(config, seeds, n_jobs=None):
        return [
            _synthetic_history(a=0.4, b_u=0.55, b_v=0.45, n=200, seed=1000 + seed, noise_sd=0.01)
            for seed in seeds
        ]

    monkeypatch.setattr("src.sq1.run_many", _fake_run_many)
    out_dir = tmp_path / "out"
    exit_code = main(
        [
            "--baseline",
            str(baseline_path),
            "--frictionless",
            str(good_frictionless_path),
            "--seeds",
            "1:3",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert exit_code == 0
    csv_path = out_dir / "sq1_seed_results.csv"
    json_path = out_dir / "sq1_summary.json"
    assert csv_path.exists()
    assert json_path.exists()
    written = pd.read_csv(csv_path)
    assert len(written) == 3
    summary = json.loads(json_path.read_text(encoding="utf-8"))
    assert summary["n_paired_seeds"] == 3
