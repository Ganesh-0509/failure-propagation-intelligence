"""Subsystem dependency graph for the Failure Propagation Engine (§8).

Nodes are subsystems; directed edges are physically/empirically justified influence
relationships (e.g. "cooling efficiency influences battery temperature"). Each edge
carries:
  - weight: propagation strength (0..1), how strongly the parent's fault raises the child's risk
  - lag_cycles: typical operating cycles before the effect is observable at the child

IMPORTANT (whitepaper §8, §18): this structure is domain-reasoning-based, NOT a learned
or validated causal model. It is a starting point for engineering review and MUST be
reviewed by a domain SME before any real deployment.
"""
from __future__ import annotations

import networkx as nx

from fpi.schemas import Subsystem

# Directed influence edges: (parent, child, weight, lag_cycles).
# Reflects the thermal -> drivetrain chain and the §8 dependency table.
_EDGES: list[tuple[Subsystem, Subsystem, float, float]] = [
    # Cooling System influences ...
    (Subsystem.COOLING, Subsystem.BATTERY, 0.85, 2.0),   # strong: coolant flow -> battery temp
    (Subsystem.COOLING, Subsystem.MOTOR, 0.25, 4.0),     # weak/indirect
    (Subsystem.COOLING, Subsystem.INVERTER, 0.25, 4.0),  # weak/indirect
    # Battery influences ...
    (Subsystem.BATTERY, Subsystem.MOTOR, 0.55, 2.0),     # moderate: usable current -> motor load
    (Subsystem.BATTERY, Subsystem.INVERTER, 0.30, 3.0),  # weak
    # Motor influences ...
    (Subsystem.MOTOR, Subsystem.INVERTER, 0.80, 1.0),    # strong: motor current -> inverter stress
]

# Subsystems whose degradation terminates at a safety-relevant behavior change (§10).
SAFETY_RELEVANT: set[Subsystem] = {Subsystem.INVERTER, Subsystem.BATTERY}


def build_dependency_graph() -> nx.DiGraph:
    """Return the MVP subsystem dependency graph as a directed NetworkX graph."""
    g = nx.DiGraph()
    for s in Subsystem:
        g.add_node(s, safety_relevant=s in SAFETY_RELEVANT)
    for parent, child, weight, lag in _EDGES:
        g.add_edge(parent, child, weight=weight, lag_cycles=lag)
    return g


def downstream_of(g: nx.DiGraph, origin: Subsystem) -> list[Subsystem]:
    """Subsystems reachable downstream from `origin` (topologically ordered)."""
    reachable = nx.descendants(g, origin)
    order = {s: i for i, s in enumerate(nx.topological_sort(g))}
    return sorted(reachable, key=lambda s: order[s])


__all__ = ["build_dependency_graph", "downstream_of", "SAFETY_RELEVANT"]
