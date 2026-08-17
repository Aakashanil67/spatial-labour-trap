"""Contract tests over data/moments.csv and src.calibrate.load_empirical_moments().

See DECISIONS.md, "An independent verification found distance_gradient_slope's sign and
dating both wrong" -- the committed target had dropped Baez and Kshirsagar's minus sign (a
travel-time-rank increase *lowers* employment share) and was dated to the paper's 2026
publication year rather than the 2011 census geography the underlying regression actually
uses. These tests exist so that class of silent, sign-dropping transcription error gets
caught by the suite rather than by a second independent audit.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.calibrate import MOMENT_KEYS, load_empirical_moments

MOMENTS_PATH = Path(__file__).resolve().parent.parent / "data" / "moments.csv"


def _raw_moments() -> pd.DataFrame:
    return pd.read_csv(MOMENTS_PATH)


def _required_rows(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["key"].isin(MOMENT_KEYS)]


def test_every_required_moment_key_occurs_exactly_once():
    counts = _raw_moments()["key"].value_counts()
    for key in MOMENT_KEYS:
        assert counts.get(key, 0) == 1, f"{key} occurs {counts.get(key, 0)} times, expected 1"


def test_values_and_standard_errors_are_finite():
    df = _required_rows(_raw_moments())
    assert df["value"].apply(math.isfinite).all()
    assert df["standard_error"].apply(math.isfinite).all()


def test_standard_errors_are_strictly_positive():
    df = _required_rows(_raw_moments())
    assert (df["standard_error"] > 0).all()


def test_distance_gradient_slope_is_negative():
    row = _raw_moments().set_index("key").loc["distance_gradient_slope"]
    assert row["value"] < 0


def test_distance_gradient_slope_measurement_period_is_2011_not_the_paper_publication_year():
    row = _raw_moments().set_index("key").loc["distance_gradient_slope"]
    assert str(row["period"]) == "2011"


def test_distance_gradient_slope_source_cites_table_5b_and_explains_the_uncertainty_field():
    row = _raw_moments().set_index("key").loc["distance_gradient_slope"]
    source = row["source"]
    assert "Table 5b" in source
    assert "standard_error" in source or "sample SD" in source or "sampling SE" in source


def test_load_empirical_moments_rejects_a_duplicate_moment_key(tmp_path):
    df = _raw_moments()
    dup = pd.concat([df, df[df["key"] == "discouraged_share"]], ignore_index=True)
    path = tmp_path / "dup_moments.csv"
    dup.to_csv(path, index=False)

    with pytest.raises(ValueError, match="duplicate"):
        load_empirical_moments(str(path))


@pytest.mark.parametrize("bad_se", [0.0, -0.01])
def test_load_empirical_moments_rejects_a_non_positive_standard_error(tmp_path, bad_se):
    df = _raw_moments().copy()
    df.loc[df["key"] == "discouraged_share", "standard_error"] = bad_se
    path = tmp_path / "bad_se_moments.csv"
    df.to_csv(path, index=False)

    with pytest.raises(ValueError, match="standard_error"):
        load_empirical_moments(str(path))


def test_load_empirical_moments_rejects_a_non_finite_value(tmp_path):
    df = _raw_moments().copy()
    df.loc[df["key"] == "discouraged_share", "value"] = np.inf
    path = tmp_path / "nonfinite_moments.csv"
    df.to_csv(path, index=False)

    with pytest.raises(ValueError):
        load_empirical_moments(str(path))


def test_load_empirical_moments_still_loads_the_real_file():
    moments = load_empirical_moments(str(MOMENTS_PATH))
    assert moments.values["distance_gradient_slope"] < 0
