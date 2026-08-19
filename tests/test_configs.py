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

    assert _diff(baseline, frictionless) == {"transport_cost_rate": (0.000145, 0.0)}


def test_frictionless_and_baseline_share_the_same_separation_rate():
    baseline = _load_raw("baseline.yaml")
    frictionless = _load_raw("frictionless.yaml")

    assert baseline["separation_rate"] == frictionless["separation_rate"]


# Every config that's supposed to share baseline.yaml's economics must carry the same
# separation_rate -- notebook 03's re-estimated central value, not the raw-link upper bound or
# Miyamoto's fallback. mvm.yaml is deliberately excluded: it's its own regression fixture with a
# separately documented rate (see its own header comment), not a spatial-economy config.
_CONFIGS_SHARING_BASELINE_ECONOMICS = (
    "baseline.yaml",
    "frictionless.yaml",
    "trace_demo.yaml",
    "scarce_vacancies.yaml",
    "scarce_vacancies_subsidy.yaml",
)


def test_all_spatial_configs_share_the_same_separation_rate():
    rates = {
        name: _load_raw(name)["separation_rate"] for name in _CONFIGS_SHARING_BASELINE_ECONOMICS
    }
    assert len(set(rates.values())) == 1, rates


def test_all_spatial_configs_use_the_re_estimated_central_separation_rate():
    """Locks the value itself, not just cross-config agreement -- see DECISIONS.md, "The QLFS
    separation-rate linkage needed a demographic consistency check...": 0.0296 is the
    demographically-consistent central estimate (unrounded 0.0295827815), not the raw-link
    upper bound (0.0317) or Miyamoto's fallback (0.0048)."""
    for name in _CONFIGS_SHARING_BASELINE_ECONOMICS:
        assert _load_raw(name)["separation_rate"] == 0.0296, name
