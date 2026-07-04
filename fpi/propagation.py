"""Stage 1 — Failure Propagation Engine (whitepaper §8, §7A).

Given per-subsystem `FaultDetection`s from the Edge AI Core, this engine reasons
over the directed subsystem dependency graph (`fpi.graph`) to produce ranked
`PropagationPath` hypotheses: for each plausible *origin* it predicts which
downstream subsystems the fault will reach, with what probability, and after how
many operating cycles (`eta_cycles`).

Core value (§7A) — origin vs. symptom
-------------------------------------
The loudest symptom is often NOT the root cause. In the thermal -> drivetrain
chain (cooling -> battery -> motor -> inverter -> power derate) a subtle cooling
fault can drive a loud inverter reading several cycles later. A naive "rank by
raw fault_probability" would blame the inverter. This engine instead scores each
candidate origin as a *root cause*:

  * an origin is a better root when it is elevated AND has no elevated *upstream*
    ancestor (an elevated ancestor means the fault more likely arrived from
    above, making this node a victim, not the source); and
  * an origin is corroborated when the downstream subsystems it is predicted to
    affect are themselves observed to be elevated.

So a quiet-ish cooling node at the head of an elevated chain outranks a loud
inverter node sitting at the chain's tail.

Reasoning basis (§18)
---------------------
The graph this engine walks is DOMAIN-REASONING-BASED, not a learned or validated
causal model (see `fpi.graph`). Probabilities here are engineering plausibility
estimates for triage / verification, never calibrated failure statistics, and the
structure must be reviewed by a domain SME before any real deployment.

Determinism: pure Python + NetworkX, no randomness — identical inputs always yield
identical, stably-sorted outputs.
"""
from __future__ import annotations

import networkx as nx

from fpi.graph import build_dependency_graph, downstream_of
from fpi.schemas import (
    FaultDetection,
    PropagationPath,
    PropagationStep,
    Subsystem,
)

# --------------------------------------------------------------------------- #
# Tunable reasoning constants (domain heuristics, §8/§18 — not learned).
# --------------------------------------------------------------------------- #
# A subsystem is a plausible fault ORIGIN / corroborating symptom only once its
# fault probability rises above this floor. Below it the node is treated as noise.
ELEVATED_THRESHOLD: float = 0.35
# At/above this probability a node is considered to have already MANIFESTED the
# fault; `next_node` points at the earliest downstream node still *below* it.
MANIFESTED_THRESHOLD: float = 0.60
# How strongly an elevated upstream ancestor discounts a node's root-cause score
# (an elevated parent implies the fault arrived from above → this node is a victim).
UPSTREAM_DISCOUNT: float = 0.80
# Gain on downstream corroboration (observed elevation of predicted victims).
CORR_GAIN: float = 0.50
# Per-extra-hop decay applied to propagation strength (fault dilutes with distance).
HOP_DECAY: float = 0.90


def _clamp01(x: float) -> float:
    """Clamp a scalar into the closed unit interval [0, 1]."""
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else float(x)


def most_likely_origin(paths: list[PropagationPath]) -> Subsystem | None:
    """Return the origin of the highest-`path_probability` hypothesis.

    `estimate` returns paths already sorted by `path_probability` descending, so
    this is simply the head of the list. Returns ``None`` when there is no
    plausible propagation hypothesis (e.g. an all-nominal detection set).
    """
    return paths[0].origin if paths else None


class PropagationEngine:
    """Reasons over the subsystem dependency graph to rank propagation paths.

    Build once (the graph is static) and call :meth:`estimate` per signal-window
    evaluation. The engine is stateless between calls and fully deterministic.
    """

    def __init__(self, graph: nx.DiGraph | None = None) -> None:
        # Domain-reasoning-based dependency graph (§8, §18); not learned.
        self.graph: nx.DiGraph = graph if graph is not None else build_dependency_graph()

    # ----------------------------------------------------------------- #
    # Internal graph walk
    # ----------------------------------------------------------------- #
    def _strongest_path(
        self, origin: Subsystem, target: Subsystem
    ) -> tuple[float, float, int]:
        """Best downstream route ``origin -> target``.

        Among all simple paths, pick the one maximising the product of edge
        weights (strongest physical influence), breaking ties toward the smaller
        cumulative lag. Returns ``(weight_product, lag_cycles, hop_count)`` where
        ``lag_cycles`` is the sum of ``lag_cycles`` along the chosen path.
        """
        best_product = -1.0
        best_lag = 0.0
        best_hops = 0
        for node_path in nx.all_simple_paths(self.graph, origin, target):
            product = 1.0
            lag = 0.0
            for parent, child in zip(node_path, node_path[1:]):
                edge = self.graph[parent][child]
                product *= edge["weight"]
                lag += edge["lag_cycles"]
            hops = len(node_path) - 1
            if product > best_product or (product == best_product and lag < best_lag):
                best_product, best_lag, best_hops = product, lag, hops
        return best_product, best_lag, best_hops

    # ----------------------------------------------------------------- #
    # Public API
    # ----------------------------------------------------------------- #
    def estimate(
        self,
        detections: list[FaultDetection],
        horizon_cycles: float = 6.0,
    ) -> list[PropagationPath]:
        """Rank propagation hypotheses from per-subsystem detections.

        For every subsystem whose ``fault_probability`` is elevated
        (>= :data:`ELEVATED_THRESHOLD`) we hypothesise it as the fault ORIGIN and
        walk the graph downstream, emitting one :class:`PropagationStep` per
        downstream subsystem that is reachable within ``horizon_cycles``. Each
        path's ``path_probability`` blends the origin's root-cause plausibility
        with observed downstream corroboration, and ``next_node`` /
        ``eta_next_cycles`` flag the earliest downstream node not yet manifested.

        Returns the paths sorted by ``path_probability`` descending (stable). An
        all-nominal detection set (no elevated subsystem) yields an empty list.
        """
        obs: dict[Subsystem, float] = {
            d.subsystem: _clamp01(d.fault_probability) for d in detections
        }

        paths: list[PropagationPath] = []
        for origin in Subsystem:
            p_origin = obs.get(origin, 0.0)
            if p_origin < ELEVATED_THRESHOLD:
                continue  # not a plausible origin

            # Root-cause plausibility: penalise having an elevated upstream cause.
            ancestors = nx.ancestors(self.graph, origin)
            upstream_support = max((obs.get(a, 0.0) for a in ancestors), default=0.0)
            root_score = p_origin * (1.0 - UPSTREAM_DISCOUNT * upstream_support)

            # Walk downstream in topological order and build steps within horizon.
            steps: list[PropagationStep] = []
            corroboration = 0.0
            for node in downstream_of(self.graph, origin):
                weight_product, lag, hops = self._strongest_path(origin, node)
                if weight_product <= 0.0:
                    continue
                if lag > horizon_cycles:
                    continue  # not observable within the reasoning horizon
                struct = weight_product * (HOP_DECAY ** max(hops - 1, 0))
                step_prob = _clamp01(p_origin * struct)
                steps.append(
                    PropagationStep(
                        subsystem=node,
                        probability=step_prob,
                        eta_cycles=lag,
                    )
                )
                # Downstream corroboration: predicted victims that are observed elevated.
                corroboration += step_prob * obs.get(node, 0.0)

            path_probability = _clamp01(root_score * (1.0 + CORR_GAIN * corroboration))

            # Earliest downstream node not yet manifested = where to look next.
            next_node: Subsystem | None = None
            eta_next: float | None = None
            for step in sorted(steps, key=lambda s: s.eta_cycles):
                if obs.get(step.subsystem, 0.0) < MANIFESTED_THRESHOLD:
                    next_node = step.subsystem
                    eta_next = step.eta_cycles
                    break

            paths.append(
                PropagationPath(
                    origin=origin,
                    steps=steps,
                    path_probability=path_probability,
                    next_node=next_node,
                    eta_next_cycles=eta_next,
                )
            )

        # Sort by likelihood descending; stable so equal scores keep enum order.
        paths.sort(key=lambda p: p.path_probability, reverse=True)
        return paths


__all__ = ["PropagationEngine", "most_likely_origin", "ELEVATED_THRESHOLD"]
