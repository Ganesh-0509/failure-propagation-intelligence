"""Tests for the Failure Propagation Engine (§8, §7A).

`FaultDetection` inputs are hand-built here — `fpi.synthetic` is deliberately NOT
imported, so the engine is exercised purely through its shared contract.

Central §7A property under test: a subtle upstream origin (cooling) with a strong,
corroborated downstream chain is recognised as the likely ORIGIN even when a
downstream node (inverter) currently shows the loudest raw symptom.
"""
from __future__ import annotations

import pytest

from fpi.propagation import PropagationEngine, most_likely_origin
from fpi.schemas import FaultDetection, PropagationPath, Subsystem


def _det(subsystem: Subsystem, p: float) -> FaultDetection:
    """Build a bare FaultDetection with a given fault probability."""
    return FaultDetection(subsystem=subsystem, fault_probability=p)


def _cooling_origin_scenario() -> list[FaultDetection]:
    """Subtle cooling origin; a rising chain with the INVERTER loudest at the tail.

    Cooling (the true root) is only mildly elevated, while the inverter — several
    hops downstream — carries the largest raw probability. A root-cause-aware
    engine must still blame cooling.
    """
    return [
        _det(Subsystem.COOLING, 0.55),   # subtle, but the head of the chain
        _det(Subsystem.BATTERY, 0.58),   # rising
        _det(Subsystem.MOTOR, 0.52),     # rising
        _det(Subsystem.INVERTER, 0.82),  # loudest symptom, but at the tail
    ]


def test_most_likely_origin_is_cooling() -> None:
    """(a) Elevated cooling + rising downstream => origin is COOLING, not INVERTER."""
    engine = PropagationEngine()
    paths = engine.estimate(_cooling_origin_scenario())

    assert paths, "expected at least one propagation hypothesis"
    assert most_likely_origin(paths) == Subsystem.COOLING
    # The loud downstream symptom must NOT be mistaken for the origin.
    assert most_likely_origin(paths) != Subsystem.INVERTER


def test_eta_to_inverter_matches_strongest_chain_lags() -> None:
    """(b) ETA(cooling -> inverter) == sum of edge lags along the strongest chain.

    The strongest cooling->inverter route is cooling->battery->motor->inverter with
    lags 2 + 2 + 1 = 5 operating cycles.
    """
    engine = PropagationEngine()
    paths = engine.estimate(_cooling_origin_scenario())

    cooling_path = next(p for p in paths if p.origin == Subsystem.COOLING)
    inverter_step = next(
        s for s in cooling_path.steps if s.subsystem == Subsystem.INVERTER
    )
    assert inverter_step.eta_cycles == pytest.approx(2.0 + 2.0 + 1.0)


def test_paths_sorted_by_probability_desc() -> None:
    """(c) Returned paths are ordered by path_probability descending."""
    engine = PropagationEngine()
    paths = engine.estimate(_cooling_origin_scenario())

    probs = [p.path_probability for p in paths]
    assert probs == sorted(probs, reverse=True)
    assert len(paths) >= 2  # multiple origins are elevated in this scenario


def test_all_nominal_yields_no_high_probability_path() -> None:
    """(d) An all-nominal detection set produces no high-probability hypothesis."""
    engine = PropagationEngine()
    nominal = [
        _det(Subsystem.COOLING, 0.04),
        _det(Subsystem.BATTERY, 0.06),
        _det(Subsystem.MOTOR, 0.03),
        _det(Subsystem.INVERTER, 0.05),
    ]
    paths = engine.estimate(nominal)

    assert not any(p.path_probability > 0.30 for p in paths)
    assert most_likely_origin(paths) is None or not paths


def test_next_node_is_earliest_unmanifested_downstream() -> None:
    """next_node flags the earliest downstream node not yet manifested (by eta)."""
    engine = PropagationEngine()
    paths = engine.estimate(_cooling_origin_scenario())

    cooling_path = next(p for p in paths if p.origin == Subsystem.COOLING)
    # Battery (eta 2) and motor (eta 3) are below the manifested threshold; the
    # inverter (0.82) has manifested. Earliest unmanifested by eta is battery.
    assert cooling_path.next_node == Subsystem.BATTERY
    assert cooling_path.eta_next_cycles == pytest.approx(2.0)
