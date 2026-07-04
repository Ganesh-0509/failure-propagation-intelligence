"""Stage 2 — Trust Engine (whitepaper §9).

The Trust Engine answers a question that is deliberately kept SEPARATE from the
fault probability produced upstream: *how much should a technician rely on this
prediction?* Probability ("how likely is the fault") and trust ("how much to
rely on the estimate") are shown side by side on the dashboard and are NEVER
merged into a single number (§9, §14). A prediction can be high-probability and
low-trust (act, but verify first) or low-probability and high-trust (a quiet,
dependable "all clear").

The engine is intentionally NOT a second black-box model (§11A, §11 explainability
rule): it is a transparent, rule-based weighted combination of the seven §9
factors. Every factor is normalized to 0..1, every weight is an inspectable class
attribute, and the resulting rationale names the factors that most reduced trust
so the reasoning can be audited on the panel grid.

Design honesty (§18): the factor weights below are a DESIGN PROPOSAL informed by
domain reasoning, not values calibrated against real maintenance outcomes.
Calibrating them against labelled field data is explicit future work.
"""
from __future__ import annotations

from typing import Optional

from fpi.schemas import FaultDetection, SignalQuality, TrustScore


def _clamp01(x: float) -> float:
    """Clamp a value into the [0, 1] interval."""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


class TrustEngine:
    """Inspectable, rule-based decision-confidence scorer (§9).

    Usage::

        engine = TrustEngine()
        trust = engine.score(detection)   # -> TrustScore (value 0..100)

    The seven §9 factors are each normalized to 0..1 (1.0 = fully trustworthy),
    combined with the weights in :attr:`WEIGHTS`, and scaled to a 0..100 score.
    Probability is never an input here — trust is computed purely from data-health
    and model-stability signals, keeping the two quantities orthogonal.
    """

    #: Per-factor weights (§9). These are a DESIGN PROPOSAL (§18); calibration
    #: against real outcomes is future work. Exposed as a class attribute so they
    #: are inspectable and tunable without touching the scoring logic. Sum == 1.0.
    WEIGHTS: dict[str, float] = {
        "sensor_quality": 0.13,
        "historical_similarity": 0.18,
        "signal_consistency": 0.12,
        "missing_data": 0.18,
        "model_confidence": 0.11,
        "environmental_conditions": 0.16,
        "temporal_stability": 0.12,
    }

    #: Human-readable phrases used to explain the 1-2 factors that most reduced
    #: trust. `missing_data` is templated with the actual missing fraction.
    _PHRASES: dict[str, str] = {
        "sensor_quality": "noisy or drifting sensor signals",
        "historical_similarity": "conditions rarely seen in training",
        "signal_consistency": "disagreement between related channels",
        "missing_data": "{pct}% of channels missing",
        "model_confidence": "low model confidence",
        "environmental_conditions": "extreme environmental/load conditions",
        "temporal_stability": "unstable readings across recent windows",
    }

    # Shortfall below this weighted amount is not worth naming in the rationale.
    _RATIONALE_EPS = 0.02

    def factor_scores(self, detection: FaultDetection) -> dict[str, float]:
        """Compute the seven §9 trust factors, each normalized to 0..1.

        1.0 means "this axis gives no reason to distrust the prediction"; 0.0
        means "this axis is as bad as it gets". Returned as a plain dict so it
        can be stored verbatim in :attr:`TrustScore.factors` for inspection.
        """
        q: SignalQuality = self._quality(detection)

        # 1. Sensor quality: degraded by noise, dropouts and calibration drift.
        sensor_quality = 1.0 - (
            q.noise_level + q.dropout_rate + q.calibration_drift
        ) / 3.0

        # 2. Historical similarity: closeness to the training distribution.
        historical_similarity = q.historical_similarity

        # 3. Signal consistency: agreement among co-moving channels.
        signal_consistency = q.channel_consistency

        # 4. Missing data: more missing channels => lower trust. Penalized
        #    super-linearly ((1 - x)^2) because missing channels remove the
        #    cross-checks that make the *remaining* data trustworthy — losing
        #    half your channels is far worse than half as trustworthy.
        missing_data = (1.0 - q.missing_channels) ** 2

        # 5. Model confidence: the classifier's own calibrated confidence.
        model_confidence = detection.model_confidence

        # 6. Environmental conditions: more ambient/load stress => lower trust.
        environmental_conditions = 1.0 - q.environmental_stress

        # 7. Temporal stability: consistency of the call across recent windows.
        temporal_stability = detection.temporal_stability

        return {
            "sensor_quality": _clamp01(sensor_quality),
            "historical_similarity": _clamp01(historical_similarity),
            "signal_consistency": _clamp01(signal_consistency),
            "missing_data": _clamp01(missing_data),
            "model_confidence": _clamp01(model_confidence),
            "environmental_conditions": _clamp01(environmental_conditions),
            "temporal_stability": _clamp01(temporal_stability),
        }

    def score(self, detection: FaultDetection) -> TrustScore:
        """Score a single :class:`FaultDetection` -> :class:`TrustScore` (0..100).

        The value is the weighted sum of the seven normalized factors scaled to
        0..100. The per-factor 0..1 values are stored in ``factors`` and a short
        rationale naming the 1-2 biggest trust reducers is attached.
        """
        factors = self.factor_scores(detection)

        weighted = sum(self.WEIGHTS[name] * factors[name] for name in self.WEIGHTS)
        value = 100.0 * _clamp01(weighted)

        rationale = self._build_rationale(value, factors, self._quality(detection))
        return TrustScore(value=round(value, 1), factors=factors, rationale=rationale)

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    @staticmethod
    def _quality(detection: FaultDetection) -> SignalQuality:
        """Return the window's SignalQuality, or a neutral default if absent."""
        window = detection.window
        if window is not None and window.quality is not None:
            return window.quality
        return SignalQuality()

    #: At/above this 0..100 score the prediction is treated as dependable and the
    #: rationale is framed positively rather than as a list of minor reducers.
    _HIGH_TRUST = 70.0

    def _build_rationale(
        self, value: float, factors: dict[str, float], quality: SignalQuality
    ) -> str:
        """Name the 1-2 factors whose weighted shortfall most reduced trust.

        Shortfall for a factor is ``weight * (1 - value)`` — i.e. how much trust
        that factor gave up relative to a perfect 1.0. Reporting the largest
        shortfalls makes the score self-explaining on the dashboard. When the
        overall score is already high, no reducer is worth flagging, so a
        positive one-liner is returned instead.
        """
        shortfalls = [
            (name, self.WEIGHTS[name] * (1.0 - factors[name]))
            for name in self.WEIGHTS
        ]
        shortfalls.sort(key=lambda pair: pair[1], reverse=True)

        top = [(name, gap) for name, gap in shortfalls if gap > self._RATIONALE_EPS][:2]
        if value >= self._HIGH_TRUST or not top:
            return (
                "High trust: sensor data is clean, consistent, and well "
                "represented in the training distribution."
            )

        phrases = [self._phrase(name, quality) for name, _ in top]
        return "Trust reduced mainly by " + " and ".join(phrases) + "."

    def _phrase(self, name: str, quality: SignalQuality) -> str:
        """Render the human-readable phrase for a factor, templating as needed."""
        template = self._PHRASES[name]
        if name == "missing_data":
            return template.format(pct=round(quality.missing_channels * 100))
        return template


__all__ = ["TrustEngine"]
