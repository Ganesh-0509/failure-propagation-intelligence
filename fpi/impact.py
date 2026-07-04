"""Impact Engine for the Failure Propagation Intelligence (FPI) pipeline (§10).

Central premise (whitepaper §10): fault *detection* and maintenance
*prioritization* are DIFFERENT problems. A maintenance queue must be ranked by
operational impact, NOT by raw fault probability. A 60%-probability fault whose
worst case is a safety-relevant power loss can — and should — outrank a
90%-probability fault whose worst case is a minor comfort malfunction.

Accordingly, `fault_probability` / `path_probability` deliberately do NOT feed the
ImpactScore. Impact is a *consequence* score derived from where a propagation path
terminates and how far it reaches. Trust (decision confidence, §9) is kept SEPARATE
and, when supplied, only lightly modulates the final value — it is never blended
into the consequence factors (§9, §14).

The score combines the six §10 factors, each normalized to 0..1 and stored in
`ImpactScore.factors`:
    operational_risk      severity of the behavior change if left unaddressed
    vehicle_availability  expected downtime to service the terminal subsystem
    safety_influence      does the path terminate at a safety-relevant subsystem
    repair_cost           cost differential of acting now vs after propagation
    propagation_severity  how many downstream subsystems are plausibly affected
    service_urgency       from eta_next_cycles — sooner => more urgent
"""
from __future__ import annotations

import numpy as np

from fpi.graph import SAFETY_RELEVANT
from fpi.schemas import ImpactScore, PropagationPath, Subsystem, TrustScore

# Severity of the behavior change observed if a fault *terminates* at a subsystem
# (§10). The inverter (traction power electronics) sits at the end of the
# thermal -> drivetrain chain: a fault there means torque cut / power derate, so it
# scores highest. Cooling is largely a precursor / comfort concern.
_OPERATIONAL_RISK: dict[Subsystem, float] = {
    Subsystem.INVERTER: 1.00,   # power-electronics fault -> torque cut / power derate
    Subsystem.BATTERY: 0.90,    # HV energy store -> derate, thermal risk
    Subsystem.MOTOR: 0.70,      # traction / drive degradation
    Subsystem.COOLING: 0.35,    # thermal management; mostly precursor / comfort
}

# Expected vehicle downtime to service each subsystem (0..1). Battery service is the
# longest / most disruptive; cooling the least.
_DOWNTIME: dict[Subsystem, float] = {
    Subsystem.BATTERY: 1.00,
    Subsystem.INVERTER: 0.80,
    Subsystem.MOTOR: 0.65,
    Subsystem.COOLING: 0.40,
}

# Cycles-to-observe scale for the urgency decay: urgency = exp(-eta / scale).
_URGENCY_SCALE_CYCLES: float = 5.0
# Default eta (cycles) when a path carries no eta information.
_DEFAULT_ETA_CYCLES: float = 3.0


def _clamp01(x: float) -> float:
    """Clamp a scalar into the closed unit interval."""
    return float(np.clip(x, 0.0, 1.0))


class ImpactEngine:
    """Computes an operational-priority ImpactScore (0..100) for a PropagationPath.

    Impact drives the maintenance dashboard's sort order (§10) — it is a consequence
    ranking, independent of how *likely* the fault is. The six factor weights are
    exposed as the class attribute `weights` for inspection / tuning; they sum to 1.0
    so a factor set that maxes every factor yields a value of 100.
    """

    #: Inspectable factor weights (must sum to 1.0). Safety and operational risk
    #: dominate so a high-consequence path outranks a merely high-probability one.
    weights: dict[str, float] = {
        "operational_risk": 0.25,
        "safety_influence": 0.25,
        "propagation_severity": 0.15,
        "service_urgency": 0.13,
        "repair_cost": 0.12,
        "vehicle_availability": 0.10,
    }

    #: How much decision-confidence (Trust) is allowed to modulate the final value.
    #: Bounded so Trust can never flip the consequence-driven ordering (§9, §14).
    trust_modulation: float = 0.10

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        if weights is not None:
            self.weights = dict(weights)

    # ------------------------------------------------------------------ #
    # Path decomposition helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _nodes(path: PropagationPath) -> list[Subsystem]:
        """All subsystems touched by the path: origin followed by the chain."""
        nodes: list[Subsystem] = [path.origin]
        for step in path.steps:
            nodes.append(step.subsystem)
        return nodes

    @staticmethod
    def _terminal(path: PropagationPath) -> Subsystem:
        """The subsystem at which the propagation path terminates."""
        if path.steps:
            return path.steps[-1].subsystem
        return path.origin

    @staticmethod
    def _downstream_count(path: PropagationPath) -> int:
        """Number of DISTINCT subsystems reached downstream of the origin."""
        seen: set[Subsystem] = set()
        for step in path.steps:
            if step.subsystem != path.origin:
                seen.add(step.subsystem)
        return len(seen)

    def _eta(self, path: PropagationPath) -> float:
        """Best available cycles-to-next-observation for the path."""
        if path.eta_next_cycles is not None:
            return float(path.eta_next_cycles)
        etas = [s.eta_cycles for s in path.steps if s.eta_cycles is not None]
        if etas:
            return float(min(etas))
        return _DEFAULT_ETA_CYCLES

    # ------------------------------------------------------------------ #
    # Factor computation
    # ------------------------------------------------------------------ #
    def _factors(self, path: PropagationPath) -> dict[str, float]:
        nodes = self._nodes(path)
        terminal = self._terminal(path)
        origin = path.origin

        # Max plausible downstream reach = every other subsystem.
        max_reach = max(1, len(Subsystem) - 1)
        propagation_severity = _clamp01(self._downstream_count(path) / max_reach)

        # Consequence at the terminal node.
        operational_risk = _OPERATIONAL_RISK.get(terminal, 0.5)
        vehicle_availability = _DOWNTIME.get(terminal, 0.5)

        # Safety influence: strongest when the path *terminates* at a safety-relevant
        # subsystem; partial credit if it merely passes through one.
        if terminal in SAFETY_RELEVANT:
            safety_influence = 1.0
        elif any(n in SAFETY_RELEVANT for n in nodes):
            safety_influence = 0.5
        else:
            safety_influence = 0.0

        # Repair-cost differential: acting now vs after further propagation. Driven by
        # how much worse the consequence gets from origin -> terminal, plus reach.
        origin_risk = _OPERATIONAL_RISK.get(origin, 0.5)
        escalation = max(0.0, operational_risk - origin_risk)
        repair_cost = _clamp01(0.5 * escalation + 0.5 * propagation_severity)

        # Urgency decays with cycles-to-observe: sooner => more urgent.
        service_urgency = _clamp01(np.exp(-self._eta(path) / _URGENCY_SCALE_CYCLES))

        return {
            "operational_risk": operational_risk,
            "vehicle_availability": vehicle_availability,
            "safety_influence": safety_influence,
            "repair_cost": repair_cost,
            "propagation_severity": propagation_severity,
            "service_urgency": service_urgency,
        }

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def score(self, path: PropagationPath, trust: TrustScore | None = None) -> ImpactScore:
        """Compute the ImpactScore (0..100) for a single propagation path."""
        factors = self._factors(path)

        base = sum(self.weights.get(name, 0.0) * value for name, value in factors.items())
        base = _clamp01(base)

        # Trust lightly modulates confidence in the priority, never the consequence
        # itself, and stays within +/- `trust_modulation` so ordering is preserved.
        if trust is not None:
            trust_norm = _clamp01(trust.value / 100.0)
            modulation = 1.0 - self.trust_modulation + self.trust_modulation * trust_norm
        else:
            modulation = 1.0

        value = float(np.clip(100.0 * base * modulation, 0.0, 100.0))

        return ImpactScore(
            value=value,
            factors=factors,
            safety_relevant=self._terminal(path) in SAFETY_RELEVANT,
        )

    def rank(
        self,
        paths: list[PropagationPath],
        trusts: list[TrustScore | None] | None = None,
    ) -> list[tuple[PropagationPath, ImpactScore]]:
        """Rank paths by operational impact (descending).

        `trusts`, if given, is aligned positionally with `paths`. Ties are broken by
        safety relevance then value so the ordering is deterministic.
        """
        if trusts is not None and len(trusts) != len(paths):
            raise ValueError("trusts must be the same length as paths")

        scored: list[tuple[PropagationPath, ImpactScore]] = []
        for i, path in enumerate(paths):
            trust = trusts[i] if trusts is not None else None
            scored.append((path, self.score(path, trust)))

        scored.sort(
            key=lambda pair: (pair[1].value, pair[1].safety_relevant),
            reverse=True,
        )
        return scored


__all__ = ["ImpactEngine"]
