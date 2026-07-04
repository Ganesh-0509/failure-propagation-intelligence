"""End-to-end integration tests for the full FPI pipeline.

These assert the whitepaper's headline behaviors on synthetic data (§7A, §9, §10, §11):
the origin is identified before the terminal symptom manifests; trust is separate
from probability; impact is safety-aware; and the recommendation is a verification
step, never an autonomous action.
"""
from __future__ import annotations

import re

from fpi.pipeline import FPIPipeline
from fpi.schemas import HealthState, Subsystem
from fpi.synthetic import generate_nominal, generate_scenario

_BANNED = re.compile(r"\b(replace|swap|install|remove|fit|mount)\b", re.IGNORECASE)


def _pipeline():
    return FPIPipeline()


def test_origin_identified_before_terminal_manifests():
    """§7A: cooling is named as origin while inverter is still nominal."""
    scenario = generate_scenario(kind="thermal_cascade", n_windows=40, seed=7, inject_at=8)
    results = _pipeline().run_scenario(scenario)

    # find the first step with a propagation chain
    idx = next(i for i, r in enumerate(results) if r.best_path is not None)
    r = results[idx]
    assert r.best_path.origin == Subsystem.COOLING
    # at that early point the inverter (terminal) has not yet been flagged
    assert r.subsystem_health.get(Subsystem.INVERTER) != HealthState.FLAGGED


def test_trust_and_probability_are_separate_quantities():
    scenario = generate_scenario(kind="thermal_cascade", n_windows=40, seed=7, inject_at=8)
    r = next(r for r in _pipeline().run_scenario(scenario) if r.best_path is not None)
    assert r.trust is not None
    assert 0.0 <= r.trust.value <= 100.0
    # trust is on a 0..100 scale; probability is 0..1 — they are not the same field
    assert 0.0 <= r.best_path.path_probability <= 1.0


def test_impact_flags_safety_relevance_on_thermal_chain():
    scenario = generate_scenario(kind="thermal_cascade", n_windows=40, seed=7, inject_at=8)
    r = next(r for r in _pipeline().run_scenario(scenario) if r.best_path is not None)
    assert r.impact is not None
    assert r.impact.safety_relevant is True  # chain terminates at inverter/battery


def test_recommendation_is_verification_not_action():
    scenario = generate_scenario(kind="thermal_cascade", n_windows=40, seed=7, inject_at=8)
    r = next(r for r in _pipeline().run_scenario(scenario) if r.best_path is not None)
    assert r.recommendation is not None
    assert r.recommendation.subsystem == Subsystem.COOLING
    assert not _BANNED.search(r.recommendation.verification_step)


def test_nominal_scenario_raises_no_high_priority_chain():
    """A no-fault scenario should not surface a flagged propagation chain."""
    scenario = generate_nominal(n_windows=30, seed=3)
    results = _pipeline().run_scenario(scenario)
    # no subsystem should be flagged in a clean run
    flagged = [
        s
        for r in results
        for s, h in r.subsystem_health.items()
        if h == HealthState.FLAGGED
    ]
    assert flagged == []
