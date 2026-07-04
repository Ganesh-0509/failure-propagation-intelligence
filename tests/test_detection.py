"""Tests for the Edge AI Core — per-subsystem fault detection (§7, §12).

These exercise the detector in isolation against the shared contract. They do
NOT depend on fpi.synthetic: if it is importable we use it for a realistic
faulty-vs-nominal comparison, otherwise a tiny local fixture stands in. This
keeps the module testable even while synthetic.py is being written elsewhere.
"""
from __future__ import annotations

import numpy as np

from fpi.detection import FaultDetector, default_detector
from fpi.schemas import FaultDetection, SignalWindow, Subsystem


# --------------------------------------------------------------------------- #
# Local fixtures (used if fpi.synthetic is unavailable)
# --------------------------------------------------------------------------- #
def _cooling_window(pump_efficiency: float, flow_rate: float) -> SignalWindow:
    return SignalWindow(
        subsystem=Subsystem.COOLING,
        t_start=0.0,
        t_end=1.0,
        features={"pump_efficiency": pump_efficiency, "flow_rate": flow_rate},
    )


def _nominal_cooling_window() -> SignalWindow:
    return _cooling_window(pump_efficiency=0.95, flow_rate=12.0)


def _faulty_cooling_window() -> SignalWindow:
    # Collapsed pump efficiency + flow == clear cooling fault.
    return _cooling_window(pump_efficiency=0.5, flow_rate=6.0)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_default_detector_returns_valid_faultdetection():
    det = default_detector(seed=1)
    fd = det.detect(_nominal_cooling_window())

    assert isinstance(fd, FaultDetection)
    assert fd.subsystem is Subsystem.COOLING
    assert 0.0 <= fd.fault_probability <= 1.0
    assert 0.0 <= fd.model_confidence <= 1.0
    assert 0.0 <= fd.temporal_stability <= 1.0
    assert fd.window is not None


def test_faulty_window_scores_higher_than_nominal():
    det = default_detector(seed=1)

    faulty = det.detect(_faulty_cooling_window())
    nominal = det.detect(_nominal_cooling_window())

    assert faulty.fault_probability > nominal.fault_probability
    # A clear fault should read as genuinely likely, not marginal.
    assert faulty.fault_probability > 0.5
    assert nominal.fault_probability < 0.5


def test_faulty_vs_nominal_with_synthetic_if_available():
    """If the synthetic generator exists, a late-cascade cooling window should
    out-score an early nominal one. Skipped cleanly if synthetic is absent."""
    try:
        from fpi.synthetic import generate_nominal, generate_scenario
    except Exception:
        return  # synthetic.py not ready yet — the local-fixture test covers this

    det = default_detector(seed=1)
    cascade = generate_scenario(kind="thermal_cascade", n_windows=40, seed=3)
    nominal = generate_nominal(n_windows=40, seed=3)

    # COOLING is index 0 within each per-timestep list.
    faulty_cooling = cascade[-1][0]
    nominal_cooling = nominal[-1][0]
    assert faulty_cooling.subsystem is Subsystem.COOLING

    p_faulty = det.detect(faulty_cooling).fault_probability
    p_nominal = det.detect(nominal_cooling).fault_probability
    assert p_faulty > p_nominal


def test_probability_and_confidence_are_distinct():
    """model_confidence must not just echo fault_probability."""
    det = default_detector(seed=1)
    # A nominal window scores P(fault) < 0.5, so decisiveness (mass on the
    # predicted "no-fault" class) is 1 - p and must differ from p itself.
    fd = det.detect(_nominal_cooling_window())
    assert fd.fault_probability < 0.5
    assert fd.model_confidence >= 0.5
    assert abs(fd.model_confidence - fd.fault_probability) > 1e-9


def test_temporal_stability_in_range_and_reacts_to_flicker():
    det = default_detector(seed=1)

    # A steady stream of clearly-faulty cooling windows -> high stability.
    steady = [_faulty_cooling_window() for _ in range(6)]
    steady_fds = det.detect_all(steady)
    for fd in steady_fds:
        assert 0.0 <= fd.temporal_stability <= 1.0
    assert steady_fds[-1].temporal_stability > 0.8

    # An alternating fault/nominal stream -> lower stability by the end.
    flicker: list[SignalWindow] = []
    for i in range(6):
        flicker.append(
            _faulty_cooling_window() if i % 2 == 0 else _nominal_cooling_window()
        )
    flicker_fds = det.detect_all(flicker)
    for fd in flicker_fds:
        assert 0.0 <= fd.temporal_stability <= 1.0
    assert flicker_fds[-1].temporal_stability < steady_fds[-1].temporal_stability


def test_fit_with_custom_data():
    """The public fit() contract works on caller-supplied windows + labels."""
    rng = np.random.default_rng(0)
    windows: list[SignalWindow] = []
    labels: list[int] = []
    for label in (0, 1):
        for _ in range(30):
            base = 0.95 if label == 0 else 0.5
            windows.append(
                _cooling_window(
                    pump_efficiency=base + float(rng.normal(0, 0.02)),
                    flow_rate=(12.0 if label == 0 else 6.0)
                    + float(rng.normal(0, 0.3)),
                )
            )
            labels.append(label)

    det = FaultDetector().fit({Subsystem.COOLING: windows}, {Subsystem.COOLING: labels})
    assert Subsystem.COOLING in det.fitted_subsystems
    p_fault = det.detect(_faulty_cooling_window()).fault_probability
    p_ok = det.detect(_nominal_cooling_window()).fault_probability
    assert p_fault > p_ok
