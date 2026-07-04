"""Tests for Stage 2 — the Trust Engine (whitepaper §9).

These tests construct FaultDetection / SignalWindow / SignalQuality objects
directly from the shared contract; they do NOT import any other engine, so the
Trust Engine is exercised in isolation. The two headline cases mirror the §9
worked examples:

  A) high fault probability from a window with ~40-50% missing channels and
     conditions rarely seen in training  -> LOW trust
  B) moderate probability from clean, consistent, well-represented data across
     stable windows                        -> HIGH trust

Note that fault_probability is set on both detections purely to demonstrate that
it does NOT influence the trust score — trust and probability stay orthogonal.
"""
from __future__ import annotations

import pytest

from fpi.schemas import FaultDetection, SignalQuality, SignalWindow, Subsystem
from fpi.trust import TrustEngine


def _detection(
    subsystem: Subsystem,
    fault_probability: float,
    model_confidence: float,
    temporal_stability: float,
    quality: SignalQuality,
) -> FaultDetection:
    """Build a FaultDetection wrapping a SignalWindow that carries `quality`."""
    window = SignalWindow(
        subsystem=subsystem,
        t_start=0.0,
        t_end=1.0,
        features={},
        quality=quality,
    )
    return FaultDetection(
        subsystem=subsystem,
        fault_probability=fault_probability,
        model_confidence=model_confidence,
        temporal_stability=temporal_stability,
        window=window,
    )


def _example_a() -> FaultDetection:
    """§9 example A: high probability but a badly degraded, unfamiliar window."""
    quality = SignalQuality(
        noise_level=0.6,
        dropout_rate=0.5,
        missing_channels=0.5,        # ~half the channels absent
        calibration_drift=0.4,
        channel_consistency=0.35,
        historical_similarity=0.08,  # conditions rarely seen in training
        environmental_stress=0.7,
    )
    return _detection(
        Subsystem.BATTERY,
        fault_probability=0.88,
        model_confidence=0.40,
        temporal_stability=0.35,
        quality=quality,
    )


def _example_b() -> FaultDetection:
    """§9 example B: moderate probability from clean, well-represented data."""
    quality = SignalQuality(
        noise_level=0.05,
        dropout_rate=0.03,
        missing_channels=0.0,
        calibration_drift=0.02,
        channel_consistency=0.95,
        historical_similarity=0.95,
        environmental_stress=0.10,
    )
    return _detection(
        Subsystem.MOTOR,
        fault_probability=0.55,
        model_confidence=0.70,
        temporal_stability=0.92,
        quality=quality,
    )


def test_example_a_low_trust() -> None:
    engine = TrustEngine()
    trust = engine.score(_example_a())
    assert trust.value < 40.0, f"expected low trust, got {trust.value}"


def test_example_b_high_trust() -> None:
    engine = TrustEngine()
    trust = engine.score(_example_b())
    assert trust.value > 70.0, f"expected high trust, got {trust.value}"


def test_high_probability_can_be_low_trust() -> None:
    """Probability and trust are orthogonal: 88% probability, low trust."""
    engine = TrustEngine()
    det_a = _example_a()
    det_b = _example_b()
    assert det_a.fault_probability > det_b.fault_probability
    assert engine.score(det_a).value < engine.score(det_b).value


def test_trust_always_in_range() -> None:
    engine = TrustEngine()
    for det in (_example_a(), _example_b()):
        assert 0.0 <= engine.score(det).value <= 100.0


def test_extreme_inputs_stay_in_range() -> None:
    """Out-of-nominal quality values must not push the score out of [0, 100]."""
    engine = TrustEngine()

    worst = _detection(
        Subsystem.COOLING,
        fault_probability=0.5,
        model_confidence=0.0,
        temporal_stability=0.0,
        quality=SignalQuality(
            noise_level=1.0,
            dropout_rate=1.0,
            missing_channels=1.0,
            calibration_drift=1.0,
            channel_consistency=0.0,
            historical_similarity=0.0,
            environmental_stress=1.0,
        ),
    )
    best = _detection(
        Subsystem.INVERTER,
        fault_probability=0.5,
        model_confidence=1.0,
        temporal_stability=1.0,
        quality=SignalQuality(
            noise_level=0.0,
            dropout_rate=0.0,
            missing_channels=0.0,
            calibration_drift=0.0,
            channel_consistency=1.0,
            historical_similarity=1.0,
            environmental_stress=0.0,
        ),
    )
    assert 0.0 <= engine.score(worst).value <= 100.0
    assert 0.0 <= engine.score(best).value <= 100.0
    assert engine.score(worst).value < engine.score(best).value


def test_factors_dict_has_seven_normalized_keys() -> None:
    engine = TrustEngine()
    expected = {
        "sensor_quality",
        "historical_similarity",
        "signal_consistency",
        "missing_data",
        "model_confidence",
        "environmental_conditions",
        "temporal_stability",
    }
    for det in (_example_a(), _example_b()):
        factors = engine.score(det).factors
        assert set(factors.keys()) == expected
        assert len(factors) == 7
        for name, val in factors.items():
            assert 0.0 <= val <= 1.0, f"{name} out of range: {val}"


def test_factor_keys_match_weight_keys() -> None:
    """Every scored factor must have a corresponding inspectable weight."""
    engine = TrustEngine()
    factors = engine.score(_example_a()).factors
    assert set(factors.keys()) == set(TrustEngine.WEIGHTS.keys())


def test_weights_are_inspectable_and_normalized() -> None:
    assert isinstance(TrustEngine.WEIGHTS, dict)
    assert len(TrustEngine.WEIGHTS) == 7
    assert pytest.approx(sum(TrustEngine.WEIGHTS.values()), abs=1e-9) == 1.0


def test_low_trust_has_nonempty_rationale() -> None:
    engine = TrustEngine()
    trust = engine.score(_example_a())
    assert isinstance(trust.rationale, str)
    assert trust.rationale.strip() != ""


def test_low_trust_rationale_names_dominant_reducers() -> None:
    """Example A's rationale should call out the missing channels and the
    unfamiliar (rarely-seen-in-training) conditions."""
    engine = TrustEngine()
    rationale = engine.score(_example_a()).rationale.lower()
    assert "missing" in rationale
    assert "training" in rationale


def test_missing_channels_lower_trust() -> None:
    """Monotonicity check: more missing channels never increases trust."""
    engine = TrustEngine()

    def trust_for(missing: float) -> float:
        det = _detection(
            Subsystem.BATTERY,
            fault_probability=0.5,
            model_confidence=0.7,
            temporal_stability=0.9,
            quality=SignalQuality(
                historical_similarity=0.9,
                channel_consistency=0.9,
                missing_channels=missing,
            ),
        )
        return engine.score(det).value

    assert trust_for(0.0) > trust_for(0.3) > trust_for(0.6)


def test_score_ignores_missing_quality() -> None:
    """A detection with no window/quality must still score without error."""
    engine = TrustEngine()
    det = FaultDetection(
        subsystem=Subsystem.MOTOR,
        fault_probability=0.5,
        model_confidence=0.5,
        temporal_stability=1.0,
        window=None,
    )
    trust = engine.score(det)
    assert 0.0 <= trust.value <= 100.0
    assert set(trust.factors.keys()) == set(TrustEngine.WEIGHTS.keys())
