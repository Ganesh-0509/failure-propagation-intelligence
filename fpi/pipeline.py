"""FPI Reasoning Engine — orchestrates the four decision stages (§7).

One coordinated pipeline, described as four stages only because each has distinct
engineering logic:

    Edge AI Core (detection)
        -> 1. Propagation Engine  (ranked propagation paths)
        -> 2. Trust Engine        (decision-confidence, SEPARATE from probability)
        -> 3. Impact Engine        (operational priority)
        -> 4. Evidence Engine      (verification recommendation, never an action)

Probability ("how likely") and trust ("how much to rely on it") are carried
side by side and never blended (§9, §14). Recommendations are verification
steps only (§11).
"""
from __future__ import annotations

from fpi.detection import FaultDetector, default_detector
from fpi.impact import ImpactEngine
from fpi.propagation import PropagationEngine
from fpi.recommendation import RecommendationEngine
from fpi.schemas import (
    FaultDetection,
    HealthState,
    PipelineResult,
    SignalWindow,
    Subsystem,
)
from fpi.trust import TrustEngine

# Health thresholds on per-subsystem fault probability (demo heuristic).
_WATCH = 0.35
_FLAGGED = 0.60


class FPIPipeline:
    """The FPI Reasoning Engine: detection -> propagation -> trust -> impact -> recommendation."""

    def __init__(
        self,
        detector: FaultDetector | None = None,
        propagation: PropagationEngine | None = None,
        trust: TrustEngine | None = None,
        impact: ImpactEngine | None = None,
        recommendation: RecommendationEngine | None = None,
    ) -> None:
        self.detector = detector or default_detector()
        self.propagation = propagation or PropagationEngine()
        self.trust = trust or TrustEngine()
        self.impact = impact or ImpactEngine()
        self.recommendation = recommendation or RecommendationEngine()

    # -- one time step -------------------------------------------------------
    def evaluate(
        self,
        windows: list[SignalWindow],
        detections: list[FaultDetection] | None = None,
    ) -> PipelineResult:
        """Run all four stages on one time-aligned set of subsystem windows."""
        if detections is None:
            detections = self.detector.detect_all(windows)

        result = PipelineResult(detections=detections)
        result.subsystem_health = self._health(detections)

        # Stage 1 — Propagation
        paths = self.propagation.estimate(detections)
        result.all_paths = paths
        if not paths:
            return result  # nominal: nothing elevated, no chain to reason about
        best = paths[0]
        result.best_path = best

        # Stage 2 — Trust (score the prediction driving the chain: its origin)
        origin_det = self._detection_for(detections, best.origin)
        trust = self.trust.score(origin_det) if origin_det else None
        result.trust = trust

        # Stage 3 — Impact (consequence-based priority; trust may modulate, never blend)
        impact = self.impact.score(best, trust)
        result.impact = impact

        # Stage 4 — Evidence-based recommendation (verification step only)
        result.recommendation = self.recommendation.recommend(
            best, trust, impact, detections
        )
        return result

    # -- a whole scenario timeline ------------------------------------------
    def run_scenario(self, scenario: list[list[SignalWindow]]) -> list[PipelineResult]:
        """Evaluate each time step of a scenario, returning a timeline of results."""
        return [self.evaluate(step) for step in scenario]

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _detection_for(
        detections: list[FaultDetection], subsystem: Subsystem
    ) -> FaultDetection | None:
        for d in detections:
            if d.subsystem == subsystem:
                return d
        return None

    @staticmethod
    def _health(detections: list[FaultDetection]) -> dict[Subsystem, HealthState]:
        health: dict[Subsystem, HealthState] = {}
        for d in detections:
            if d.fault_probability >= _FLAGGED:
                health[d.subsystem] = HealthState.FLAGGED
            elif d.fault_probability >= _WATCH:
                health[d.subsystem] = HealthState.WATCH
            else:
                health[d.subsystem] = HealthState.OK
        return health


__all__ = ["FPIPipeline"]
