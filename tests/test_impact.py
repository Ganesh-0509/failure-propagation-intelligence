"""Tests for the Impact Engine (§10).

The central §10 property under test: prioritization ranks by *operational impact*,
not by raw fault probability. A lower-probability but safety-relevant / high-
consequence path must outrank a higher-probability low-consequence path.

PropagationPath objects are constructed directly here — propagation.py is NOT
imported, so the Impact Engine is exercised through its shared contract only.
"""
from __future__ import annotations

import pytest

from fpi.graph import SAFETY_RELEVANT
from fpi.impact import ImpactEngine
from fpi.schemas import (
    ImpactScore,
    PropagationPath,
    PropagationStep,
    Subsystem,
    TrustScore,
)

FACTOR_KEYS = {
    "operational_risk",
    "vehicle_availability",
    "safety_influence",
    "repair_cost",
    "propagation_severity",
    "service_urgency",
}


def _safety_path() -> PropagationPath:
    """Low-probability chain that terminates at the (safety-relevant) INVERTER."""
    return PropagationPath(
        origin=Subsystem.COOLING,
        steps=[
            PropagationStep(Subsystem.BATTERY, probability=0.60, eta_cycles=2.0),
            PropagationStep(Subsystem.MOTOR, probability=0.55, eta_cycles=3.0),
            PropagationStep(Subsystem.INVERTER, probability=0.50, eta_cycles=4.0),
        ],
        path_probability=0.50,          # low overall likelihood
        next_node=Subsystem.BATTERY,
        eta_next_cycles=2.0,
    )


def _comfort_path() -> PropagationPath:
    """High-probability fault that stays at COOLING (low consequence, not safety)."""
    return PropagationPath(
        origin=Subsystem.COOLING,
        steps=[],
        path_probability=0.90,          # high overall likelihood
        next_node=None,
        eta_next_cycles=1.0,
    )


def test_low_prob_safety_path_outranks_high_prob_comfort_path():
    """§10 ordering property: consequence beats probability."""
    engine = ImpactEngine()
    safety = engine.score(_safety_path())
    comfort = engine.score(_comfort_path())

    assert safety.value > comfort.value, (
        f"safety path ({safety.value:.1f}) must outrank comfort path "
        f"({comfort.value:.1f}) despite lower fault probability"
    )


def test_value_within_bounds():
    engine = ImpactEngine()
    for path in (_safety_path(), _comfort_path()):
        s = engine.score(path)
        assert isinstance(s, ImpactScore)
        assert 0.0 <= s.value <= 100.0


def test_factors_complete_and_normalized():
    engine = ImpactEngine()
    for path in (_safety_path(), _comfort_path()):
        factors = engine.score(path).factors
        assert set(factors.keys()) == FACTOR_KEYS
        for name, value in factors.items():
            assert 0.0 <= value <= 1.0, f"{name}={value} out of [0,1]"


def test_safety_relevant_flag_set_for_inverter_terminus():
    engine = ImpactEngine()
    assert Subsystem.INVERTER in SAFETY_RELEVANT
    assert engine.score(_safety_path()).safety_relevant is True
    assert engine.score(_comfort_path()).safety_relevant is False


def test_rank_orders_by_impact_descending():
    engine = ImpactEngine()
    comfort, safety = _comfort_path(), _safety_path()
    paths = [comfort, safety]  # deliberately worst-first
    ranked = engine.rank(paths)

    assert [p for p, _ in ranked] == [safety, comfort]
    values = [s.value for _, s in ranked]
    assert values == sorted(values, reverse=True)
    # The safety path lands on top.
    top_path, top_score = ranked[0]
    assert top_score.safety_relevant is True


def test_weights_are_inspectable_and_sum_to_one():
    assert pytest.approx(sum(ImpactEngine.weights.values()), abs=1e-9) == 1.0
    assert set(ImpactEngine.weights.keys()) == FACTOR_KEYS


def test_trust_modulation_is_bounded_and_preserves_ordering():
    engine = ImpactEngine()
    low_trust = TrustScore(value=5.0)
    high_trust = TrustScore(value=95.0)

    safety_low = engine.score(_safety_path(), low_trust)
    safety_high = engine.score(_safety_path(), high_trust)
    comfort_high = engine.score(_comfort_path(), high_trust)

    # Trust nudges the value but never flips the consequence-driven ordering.
    assert safety_high.value >= safety_low.value
    assert safety_low.value > comfort_high.value
