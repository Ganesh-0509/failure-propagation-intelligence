"""Network-GATED tests for the real public-dataset loaders (fpi.datasets).

These tests NEVER download anything. If the real files are already cached in
``data/real/`` (e.g. after ``python scripts/fetch_datasets.py``) they assert the
loaders return correctly shaped arrays with both labels present. If the data is
absent, they SKIP cleanly so CI stays green without the large downloads.
"""
from __future__ import annotations

import numpy as np
import pytest

from fpi.datasets import (
    DATASET_SOURCES,
    DEFAULT_CACHE_DIR,
    load_battery_dataset,
    load_bearing_dataset,
)


def _cached(files: list[str]) -> bool:
    return all(
        (DEFAULT_CACHE_DIR / f).exists() and (DEFAULT_CACHE_DIR / f).stat().st_size > 0
        for f in files
    )


_BATTERY_FILES = list(DATASET_SOURCES["nasa_battery"]["files"].keys())
_BEARING_FILES = list(DATASET_SOURCES["cwru_bearing"]["files"].keys())

_have_battery = _cached(_BATTERY_FILES)
_have_bearing = _cached(_BEARING_FILES)


def test_dataset_sources_registry():
    # Pure metadata check -- always runs, no network, no files.
    for name in ("nasa_battery", "cwru_bearing"):
        meta = DATASET_SOURCES[name]
        assert meta["files"], f"{name} has no files"
        assert "license" in meta and meta["license"]
        for urls in meta["files"].values():
            assert urls and all(u.startswith("http") for u in urls)


@pytest.mark.skipif(not _have_battery, reason="real datasets not downloaded")
def test_load_battery_shapes_and_labels():
    X, y, names = load_battery_dataset()
    assert X.ndim == 2 and X.shape[0] == y.shape[0]
    assert X.shape[1] == len(names)
    assert X.shape[0] > 50  # B0005 has ~168 discharge cycles
    # Both classes must be present for a meaningful validation.
    assert set(np.unique(y)) == {0, 1}
    # Capacity (the label source) must NOT leak into the features.
    assert not any("capacit" in n.lower() for n in names)
    assert np.isfinite(X).all()


@pytest.mark.skipif(not _have_bearing, reason="real datasets not downloaded")
def test_load_bearing_shapes_and_labels():
    X, y, names = load_bearing_dataset()
    assert X.ndim == 2 and X.shape[0] == y.shape[0]
    assert X.shape[1] == len(names)
    assert X.shape[0] > 50  # many 2048-sample windows across the files
    assert set(np.unique(y)) == {0, 1}  # normal + fault
    assert np.isfinite(X).all()


@pytest.mark.skipif(
    not (_have_battery and _have_bearing), reason="real datasets not downloaded"
)
def test_loaders_are_deterministic():
    Xb1, yb1, _ = load_battery_dataset()
    Xb2, yb2, _ = load_battery_dataset()
    assert np.array_equal(Xb1, Xb2) and np.array_equal(yb1, yb2)
    Xm1, ym1, _ = load_bearing_dataset()
    Xm2, ym2, _ = load_bearing_dataset()
    assert np.array_equal(Xm1, Xm2) and np.array_equal(ym1, ym2)
