"""Tests for src/sweeps.py.

The module exists to give the response surface a committed, provenanced generator, so the tests
that matter are: the sweep really does hold everything but one field fixed, and the written
record really does carry the fingerprint the I4 contract wants. simulate_moments is stubbed
throughout -- these check the sweep's own wiring, not the model, which tests/test_moments.py
already covers.
"""

from __future__ import annotations

import json

import pytest

from src.calibrate import MOMENT_KEYS
from src.config import Config
from src.sweeps import DEFAULT_AXES, _gradient_is_identically_zero, main, sweep

CENTRE = {
    "search_cost_per_trip": 0.02,
    "initial_search_capital": 1.0,
    "firm_radius": 2.5,
    "firm_kappa": 0.9,
}


def _stub_simulate(recorder=None):
    def _fake(base, params, seeds):
        if recorder is not None:
            recorder.append(dict(params))
        # firm_radius is the only field this stub responds to, so a sweep along any other axis
        # comes back identically flat -- which is what the flat-axis assertions below rely on.
        return {key: (params["firm_radius"] * 0.1, 0.0) for key in MOMENT_KEYS}

    return _fake


def test_sweep_varies_only_the_named_field(monkeypatch):
    seen: list[dict] = []
    monkeypatch.setattr("src.sweeps.simulate_moments", _stub_simulate(seen))
    base = Config.from_yaml("configs/baseline.yaml")

    sweep(base, CENTRE, axes={"firm_radius": (1.0, 2.0, 3.0)}, seeds=(1,))

    assert [p["firm_radius"] for p in seen] == [1.0, 2.0, 3.0]
    for params in seen:
        for held in ("search_cost_per_trip", "initial_search_capital", "firm_kappa"):
            assert params[held] == CENTRE[held]


def test_sweep_can_walk_a_config_field_that_is_not_a_calibrated_parameter(monkeypatch):
    """separation_rate is a Config field but not one of the four calibrated parameters. The
    module deliberately has no separate code path for it; this pins that."""
    seen: list[dict] = []
    monkeypatch.setattr("src.sweeps.simulate_moments", _stub_simulate(seen))
    base = Config.from_yaml("configs/baseline.yaml")

    sweep(base, CENTRE, axes={"separation_rate": (0.015, 0.06)}, seeds=(1,))

    assert [p["separation_rate"] for p in seen] == [0.015, 0.06]
    assert all(p["firm_radius"] == CENTRE["firm_radius"] for p in seen)


@pytest.mark.parametrize(
    ("values", "expected"),
    [((0.0, 0.0, 0.0), True), ((0.0, 0.0, 0.1), False), ((0.7, 0.7), True)],
)
def test_gradient_is_identically_zero(values, expected):
    points = [{"moments": {"long_term_share": v}} for v in values]
    assert _gradient_is_identically_zero(points, "long_term_share") is expected


def test_main_writes_a_fingerprinted_record(tmp_path, monkeypatch):
    """The whole reason this module exists: the artefact must carry enough provenance to be
    regenerated. A bare dict of numbers is what the audit rejected."""
    monkeypatch.setattr("src.sweeps.simulate_moments", _stub_simulate())
    calibration = tmp_path / "calibration_result.json"
    calibration.write_text(
        json.dumps({"params": CENTRE, "fingerprint": {"code_commit": "deadbeef"}}),
        encoding="utf-8",
    )
    out = tmp_path / "surface.json"

    assert (
        main(
            [
                "--config",
                "configs/baseline.yaml",
                "--calibration",
                str(calibration),
                "--out",
                str(out),
            ]
        )
        == 0
    )

    record = json.loads(out.read_text(encoding="utf-8"))
    fingerprint = record["fingerprint"]
    assert len(fingerprint["code_commit"]) == 40
    assert len(fingerprint["moments_csv_sha256"]) == 64
    assert fingerprint["sweep_seeds"] == [1, 2, 3, 4, 5]
    assert fingerprint["centre_code_commit"] == "deadbeef"
    assert record["centre_params"] == CENTRE
    assert set(record["surfaces"]) == set(DEFAULT_AXES)
    assert set(record["empirical_targets"]) == set(MOMENT_KEYS)
