"""Contract tests over the raw YAML config files -- not the `Config` dataclass.

Deliberately load the YAML as plain dictionaries rather than instantiating `Config`: a future
field left out of one file entirely would be silently filled by a dataclass default and this
comparison would miss it. See DECISIONS.md, "The frictionless config drifted from a one-field
counterfactual into a second, uncontrolled experiment" -- `frictionless.yaml` claimed
`transport_cost_rate` was its only difference from `baseline.yaml` while also carrying the
stale Miyamoto `separation_rate`, so SQ1's headline number compared two economies that differed
in two channels at once.
"""

from __future__ import annotations

from pathlib import Path

import yaml

CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs"


def _load_raw(name: str) -> dict:
    with open(CONFIGS_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _diff(a: dict, b: dict) -> dict:
    keys = set(a) | set(b)
    return {k: (a.get(k), b.get(k)) for k in keys if a.get(k) != b.get(k)}


def test_frictionless_differs_from_baseline_only_in_transport_cost_rate():
    baseline = _load_raw("baseline.yaml")
    frictionless = _load_raw("frictionless.yaml")

    assert _diff(baseline, frictionless) == {"transport_cost_rate": (0.004, 0.0)}


def test_frictionless_and_baseline_share_the_same_separation_rate():
    baseline = _load_raw("baseline.yaml")
    frictionless = _load_raw("frictionless.yaml")

    assert baseline["separation_rate"] == frictionless["separation_rate"]
