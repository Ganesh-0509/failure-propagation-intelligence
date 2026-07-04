"""Tests for the physics-informed synthetic scenario generator (fpi.synthetic)."""
from __future__ import annotations

import pytest

from fpi.schemas import SignalQuality, SignalWindow, Subsystem
from fpi.synthetic import (
    FAULT_THRESHOLD,
    generate_nominal,
    generate_scenario,
    load_public_dataset,
    save_scenario,
    to_records,
    window_severity,
)

N_WINDOWS = 40
INJECT_AT = 8


def _onset_index(scenario, subsystem, threshold=0.25):
    """First window index where the subsystem's fault indicator exceeds threshold."""
    sub_order = {s: i for i, s in enumerate(Subsystem)}
    idx = sub_order[subsystem]
    for t, step in enumerate(scenario):
        if window_severity(step[idx]) > threshold:
            return t
    return None


def test_scenario_shape():
    scenario = generate_scenario(n_windows=N_WINDOWS, seed=0, inject_at=INJECT_AT)
    assert len(scenario) == N_WINDOWS
    for step in scenario:
        assert len(step) == 4
        assert [w.subsystem for w in step] == list(Subsystem)
        for w in step:
            assert isinstance(w, SignalWindow)
            assert isinstance(w.quality, SignalQuality)
            assert w.features  # non-empty
            assert w.t_end > w.t_start


def test_expected_feature_channels():
    scenario = generate_scenario(n_windows=5, seed=0)
    first = {w.subsystem: w for w in scenario[0]}
    assert "pump_efficiency" in first[Subsystem.COOLING].features
    assert "flow_rate" in first[Subsystem.COOLING].features
    assert "temp_c" in first[Subsystem.BATTERY].features
    assert "internal_resistance" in first[Subsystem.BATTERY].features
    assert "usable_current" in first[Subsystem.BATTERY].features
    assert "current_a" in first[Subsystem.MOTOR].features
    assert "junction_temp_c" in first[Subsystem.INVERTER].features
    assert "stress" in first[Subsystem.INVERTER].features


def test_quality_in_unit_range():
    scenario = generate_scenario(n_windows=N_WINDOWS, seed=3, inject_at=INJECT_AT)
    for step in scenario:
        for w in step:
            q = w.quality
            for val in vars(q).values():
                assert 0.0 <= val <= 1.0


def test_deterministic_under_seed():
    a = generate_scenario(n_windows=N_WINDOWS, seed=42, inject_at=INJECT_AT)
    b = generate_scenario(n_windows=N_WINDOWS, seed=42, inject_at=INJECT_AT)
    assert to_records(a) == to_records(b)


def test_different_seeds_differ():
    a = generate_scenario(n_windows=N_WINDOWS, seed=1)
    b = generate_scenario(n_windows=N_WINDOWS, seed=2)
    assert to_records(a) != to_records(b)


def test_nominal_stays_below_threshold():
    scenario = generate_nominal(n_windows=N_WINDOWS, seed=7)
    for step in scenario:
        for w in step:
            assert window_severity(w) < FAULT_THRESHOLD


def test_cascade_crosses_threshold_downstream():
    scenario = generate_scenario(n_windows=N_WINDOWS, seed=0, inject_at=INJECT_AT)
    # By the final window every subsystem in the primary chain should be faulted.
    last = {w.subsystem: w for w in scenario[-1]}
    for subsystem in Subsystem:
        assert window_severity(last[subsystem]) > FAULT_THRESHOLD


def test_lag_ordering():
    scenario = generate_scenario(n_windows=N_WINDOWS, seed=0, inject_at=INJECT_AT)
    onset = {s: _onset_index(scenario, s) for s in Subsystem}
    for s, idx in onset.items():
        assert idx is not None, f"{s} never crossed threshold"

    # Downstream subsystems must rise strictly AFTER their upstream neighbours.
    assert onset[Subsystem.COOLING] < onset[Subsystem.BATTERY]
    assert onset[Subsystem.BATTERY] < onset[Subsystem.MOTOR]
    assert onset[Subsystem.MOTOR] < onset[Subsystem.INVERTER]

    # Cooling should not visibly fault before the injection point.
    assert onset[Subsystem.COOLING] >= INJECT_AT


def test_before_injection_is_nominal():
    scenario = generate_scenario(n_windows=N_WINDOWS, seed=0, inject_at=INJECT_AT)
    for t in range(INJECT_AT):
        for w in scenario[t]:
            assert window_severity(w) < FAULT_THRESHOLD


def test_save_scenario_roundtrip(tmp_path):
    scenario = generate_scenario(n_windows=10, seed=0)
    out = save_scenario(scenario, tmp_path / "sub" / "s.json", meta={"k": "v"})
    assert out.exists()
    import json

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["n_windows"] == 10
    assert len(payload["records"]) == 10 * 4
    assert payload["meta"]["k"] == "v"


def test_invalid_kind_raises():
    with pytest.raises(ValueError):
        generate_scenario(kind="explosion")


def test_public_dataset_loader_is_stub():
    with pytest.raises(NotImplementedError):
        load_public_dataset("nasa_battery")
