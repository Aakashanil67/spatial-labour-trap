"""Tests for runner.py's cache -- these have to be able to catch a genuinely wrong cache key,
not just confirm the happy path. See I1 in DECISIONS.md for why this matters: every downstream
stage (calibration, sweeps, experiments) reads through this cache.
"""

from __future__ import annotations

from dataclasses import replace

import src.runner as runner
from src.config import Config

BASE = Config(
    n_agents=50,
    n_vacancies=5,
    initial_search_capital=1.0,
    search_cost_per_trip=0.02,
    separation_rate=0.02,
    belief_multiplier=1.0,
    household_inflow=0.02,
    reentry_threshold=0.05,
    max_trips_per_step=4,
    n_steps=10,
    seed=1,
)


def test_cache_hit_returns_identical_data(tmp_path):
    cache_dir = tmp_path / "cache"
    a = runner.run_cached(BASE, seed=1, cache_dir=cache_dir)
    b = runner.run_cached(BASE, seed=1, cache_dir=cache_dir)
    assert a.equals(b)
    assert len(list(cache_dir.glob("*.pkl"))) == 1


def test_different_seeds_produce_different_cache_entries(tmp_path):
    cache_dir = tmp_path / "cache"
    runner.run_cached(BASE, seed=1, cache_dir=cache_dir)
    runner.run_cached(BASE, seed=2, cache_dir=cache_dir)
    assert len(list(cache_dir.glob("*.pkl"))) == 2


def test_seed_override_actually_changes_the_run(tmp_path):
    cache_dir = tmp_path / "cache"
    a = runner.run_cached(BASE, seed=1, cache_dir=cache_dir)
    b = runner.run_cached(BASE, seed=99, cache_dir=cache_dir)
    assert not a["u"].equals(b["u"])


def test_source_fingerprint_change_invalidates_the_key():
    """Simulates an edit to agents.py/model.py -- the cache key must change so a stale entry
    from before the edit is never served after it."""
    key_before = runner._cache_key(BASE, seed=1)
    original = runner._FINGERPRINT
    try:
        runner._FINGERPRINT = "deadbeef" * 2
        key_after = runner._cache_key(BASE, seed=1)
    finally:
        runner._FINGERPRINT = original
    assert key_before != key_after


def test_tiny_float_difference_is_not_quantised_away():
    """A 1e-9 difference in a parameter must produce a different key -- quantising floats
    before hashing was tried and rejected (see I1): it causes false cache hits during
    Nelder-Mead's late, sub-1e-6 parameter steps."""
    cfg_a = replace(BASE, search_cost_per_trip=0.02)
    cfg_b = replace(BASE, search_cost_per_trip=0.02 + 1e-9)
    assert runner._cache_key(cfg_a, seed=1) != runner._cache_key(cfg_b, seed=1)


def test_run_many_preserves_seed_order(tmp_path):
    cache_dir = tmp_path / "cache"
    seeds = [5, 1, 9, 3]
    results = [runner.run_cached(BASE, seed=s, cache_dir=cache_dir) for s in seeds]
    parallel_results = _run_many_with_dir(BASE, seeds, cache_dir)
    for sequential, parallel in zip(results, parallel_results, strict=True):
        assert sequential.equals(parallel)


def _run_many_with_dir(config, seeds, cache_dir):
    from joblib import Parallel, delayed

    return Parallel(n_jobs=2, backend="loky")(
        delayed(runner.run_cached)(config, seed, cache_dir) for seed in seeds
    )
