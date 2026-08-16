"""Cached, parallel model runs. Every downstream stage (calibration, sweeps, experiments,
robustness) reads through this, so getting the cache key wrong here is the kind of mistake
that costs a week later, not five minutes now -- see I1 in DECISIONS.md.

The cache key is resolved config + seed + a source fingerprint (sha256 over the model code
that actually determines behaviour). Editing agents.py or model.py changes the fingerprint,
so a stale cache entry from before the edit is never served after it. No float quantisation --
canonical JSON with Python's default repr is exact, and quantising creates false cache hits
during Nelder-Mead's late, sub-1e-6 parameter steps (see DECISIONS.md D12's neighbour, I1).
"""

from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path

import pandas as pd
from joblib import Parallel, delayed

from src.config import Config
from src.model import CityModel
from src.moments import compute_moments

# Physical core count, not logical -- measured via psutil.cpu_count(logical=False) on this
# machine (6 physical / 12 logical). Two hyperthreads on one physical core contend for the
# same execution units on CPU-bound simulation work rather than doubling it. See DECISIONS.md D4.
N_JOBS = 6

_SOURCE_FILES = ("src/agents.py", "src/model.py", "src/moments.py")
_CACHE_DIR = Path("results/cache")


def _source_fingerprint() -> str:
    """sha256 over the model code whose behaviour the cache key must track. Recomputed once
    per process, not once per call, since runner.py itself doesn't change within a run."""
    hasher = hashlib.sha256()
    for rel_path in _SOURCE_FILES:
        hasher.update(Path(rel_path).read_bytes())
    return hasher.hexdigest()[:16]


_FINGERPRINT = _source_fingerprint()


def _cache_key(config: Config, seed: int) -> str:
    payload = f"{config.canonical_json()}|seed={seed}|src={_FINGERPRINT}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_cached(config: Config, seed: int, cache_dir: Path = _CACHE_DIR) -> pd.DataFrame:
    """Run once for (config, seed), or return the cached result if the exact same config,
    seed, and model source have already been run."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key(config, seed)
    cache_path = cache_dir / f"{key}.pkl"

    if cache_path.exists():
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    run_config = config if config.seed == seed else _with_seed(config, seed)
    history = CityModel(run_config).run()

    with open(cache_path, "wb") as f:
        pickle.dump(history, f)
    return history


def _with_seed(config: Config, seed: int) -> Config:
    from dataclasses import replace

    return replace(config, seed=seed)


def run_many(config: Config, seeds: list[int], n_jobs: int = N_JOBS) -> list[pd.DataFrame]:
    """Run (config, seed) for every seed in seeds, in parallel, each result independently
    cached. Order of the returned list matches the order of seeds, regardless of which worker
    finished first -- joblib preserves input order."""
    return Parallel(n_jobs=n_jobs, backend="loky")(
        delayed(run_cached)(config, seed) for seed in seeds
    )


def run_moments_cached(config: Config, seed: int, cache_dir: Path = _CACHE_DIR) -> dict[str, float]:
    """Like run_cached, but caches the four computed moments (a handful of floats) rather than
    the full history. This exists because compute_moments needs the live CityModel, not just
    its history -- distance_gradient_slope is cross-sectional, read from the model's final
    agent states, and a pickled history alone can't reconstruct that. A separate JSON cache,
    not a repurposed run_cached entry, so calibrate.py's thousands of (config, seed) moment
    evaluations don't force every caller through the same path as a raw-history request."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key(config, seed) + "-moments"
    cache_path = cache_dir / f"{key}.json"

    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    run_config = config if config.seed == seed else _with_seed(config, seed)
    model = CityModel(run_config)
    history = model.run()
    moments = compute_moments(model, history)

    cache_path.write_text(json.dumps(moments), encoding="utf-8")
    return moments


def run_moments_many(
    config: Config, seeds: list[int], n_jobs: int = N_JOBS
) -> list[dict[str, float]]:
    """Moments analogue of run_many -- one dict of the four moments per seed, same ordering
    guarantee."""
    return Parallel(n_jobs=n_jobs, backend="loky")(
        delayed(run_moments_cached)(config, seed) for seed in seeds
    )
