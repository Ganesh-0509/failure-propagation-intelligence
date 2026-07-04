"""Tests for Stage 4 — the Evidence-Based Decision Engine (whitepaper §11, §11A).

These tests construct PropagationPath / TrustScore / ImpactScore / FaultDetection
objects directly from the shared contract; they do NOT import any other engine, so
the Recommendation Engine is exercised through its shared contract only.

Headline properties under test (§11):
  - recommendations are VERIFICATION steps, never autonomous actions;
  - a cooling-origin path yields a coolant-inspection step;
  - low decision trust forces "verify BEFORE any action" wording;
  - the passed trust and impact objects are carried through unchanged;
  - missing channels in a window populate `missing_signals`.
"""
from __future__ import annotations

import pytest

from fpi.recommendation import RecommendationEngine
from fpi.schemas import (
    FaultDetection,
    ImpactScore,
    PropagationPath,
    PropagationStep,
    Recommendation,
    SignalQuality,
    SignalWindow,
    Subsystem,
    TrustScore,
)

# Verbs that would signal an autonomous maintenance action (must never appear).
BANNED_VERBS = ["replace", "swap", "install", "remove", "refit", "fit", "mount"]


def _cooling_path() -> PropagationPath:
    """Thermal->drivetrain chain with a COOLING origin (the §8/§11A example)."""
    return PropagationPath(
        origin=Subsystem.COOLING,
        steps=[
            PropagationStep(Subsystem.BATTERY, probability=0.70, eta_cycles=2.0),
            PropagationStep(Subsystem.MOTOR, probability=0.55, eta_cycles=4.0),
            PropagationStep(Subsystem.INVERTER, probability=0.45, eta_cycles=5.0),
        ],
        path_probability=0.62,
        next_node=Subsystem.BATTERY,
        eta_next_cycles=2.0,
    )


def _detection(
    subsystem: Subsystem,
    fault_probability: float,
    quality: SignalQuality | None = None,
    features: dict[str, float] | None = None,
) -> FaultDetection:
    window = SignalWindow(
        subsystem=subsystem,
        t_start=0.0,
        t_end=1.0,
        features=features or {},
        quality=quality,
    )
    return FaultDetection(
        subsystem=subsystem,
        fault_probability=fault_probability,
        model_confidence=0.6,
        temporal_stability=0.9,
        window=window,
    )


def _detections() -> list[FaultDetection]:
    return [
        _detection(Subsystem.COOLING, 0.82),
        _detection(Subsystem.BATTERY, 0.40),
    ]


def test_cooling_origin_yields_coolant_inspection_step():
    engine = RecommendationEngine()
    rec = engine.recommend(
        _cooling_path(),
        TrustScore(value=80.0),
        ImpactScore(value=70.0),
        _detections(),
    )
    assert isinstance(rec, Recommendation)
    assert rec.subsystem is Subsystem.COOLING
    step = rec.verification_step.lower()
    assert "coolant" in step
    assert "inspect" in step or "verify" in step


def test_verification_step_has_no_banned_action_verbs():
    """The §11 core invariant: never an autonomous action, across all origins."""
    engine = RecommendationEngine()
    for origin in Subsystem:
        path = PropagationPath(origin=origin, steps=[], path_probability=0.5)
        rec = engine.recommend(
            path,
            TrustScore(value=20.0),   # exercise the low-trust wording branch too
            ImpactScore(value=20.0),  # ...and the low-impact wording branch
            [],
        )
        step = rec.verification_step.lower()
        for verb in BANNED_VERBS:
            assert verb not in step.split(), f"banned verb {verb!r} in step: {step!r}"


def test_low_trust_forces_verify_before_action_phrase():
    engine = RecommendationEngine()
    low = engine.recommend(
        _cooling_path(), TrustScore(value=15.0), ImpactScore(value=70.0), _detections()
    )
    high = engine.recommend(
        _cooling_path(), TrustScore(value=90.0), ImpactScore(value=70.0), _detections()
    )
    assert "before any" in low.verification_step.lower()
    assert "before any" not in high.verification_step.lower()


def test_low_impact_defers_to_monitoring():
    engine = RecommendationEngine()
    rec = engine.recommend(
        _cooling_path(), TrustScore(value=80.0), ImpactScore(value=20.0), _detections()
    )
    text = rec.verification_step.lower()
    assert "monitor" in text or "next scheduled service" in text


def test_recommendation_carries_passed_trust_and_impact():
    engine = RecommendationEngine()
    trust = TrustScore(value=42.0, rationale="unit-test trust")
    impact = ImpactScore(value=57.0, safety_relevant=True)
    rec = engine.recommend(_cooling_path(), trust, impact, _detections())
    # The exact objects are attached, unchanged (probability/trust stay separate).
    assert rec.trust is trust
    assert rec.impact is impact


def test_missing_signals_populated_when_window_reports_missing_channels():
    engine = RecommendationEngine()
    quality = SignalQuality(missing_channels=0.5)  # half the channels absent
    det = _detection(
        Subsystem.COOLING,
        fault_probability=0.80,
        quality=quality,
        features={"coolant_temp": 88.0},  # coolant_flow / pump_rpm absent
    )
    rec = engine.recommend(
        _cooling_path(), TrustScore(value=70.0), ImpactScore(value=60.0), [det]
    )
    assert rec.missing_signals, "expected missing_signals to be populated"
    joined = " ".join(rec.missing_signals).lower()
    assert "coolant_flow" in joined or "absent" in joined


def test_no_missing_signals_when_channels_complete():
    engine = RecommendationEngine()
    quality = SignalQuality(missing_channels=0.0)
    det = _detection(Subsystem.COOLING, 0.8, quality=quality, features={"coolant_flow": 1.0})
    rec = engine.recommend(
        _cooling_path(), TrustScore(value=70.0), ImpactScore(value=60.0), [det]
    )
    assert rec.missing_signals == []


def test_reason_references_propagation_path_and_principles():
    engine = RecommendationEngine()
    rec = engine.recommend(
        _cooling_path(), TrustScore(value=70.0), ImpactScore(value=60.0), _detections()
    )
    reason = rec.reason.lower()
    assert "propagation" in reason
    assert "cooling" in reason
    # The recurring engineering principles are stated for auditability (§11).
    assert "verification step" in reason


def test_evidence_lists_path_and_triggering_detections():
    engine = RecommendationEngine()
    rec = engine.recommend(
        _cooling_path(), TrustScore(value=70.0), ImpactScore(value=60.0), _detections()
    )
    assert rec.evidence, "evidence must not be empty"
    joined = " ".join(rec.evidence).lower()
    assert "path" in joined
    # High-probability cooling detection is called out; the 0.40 battery one is not.
    assert "cooling" in joined


def test_all_four_subsystem_templates_exist_and_are_clean():
    engine = RecommendationEngine()
    assert set(engine.TEMPLATES.keys()) == set(Subsystem)
    for template in engine.TEMPLATES.values():
        words = template.lower().split()
        for verb in BANNED_VERBS:
            assert verb not in words, f"banned verb {verb!r} in template: {template!r}"
