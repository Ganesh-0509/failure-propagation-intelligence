"""Shared data contracts for the Failure Propagation Intelligence (FPI) pipeline.

This module is the single source of truth for every stage's inputs and outputs.
All engines (detection, propagation, trust, impact, recommendation) exchange the
dataclasses defined here so they stay decoupled and independently testable.

Design notes (from the whitepaper):
- Probability ("how likely") and Trust ("how much to rely on it") are kept as
  SEPARATE quantities and are never blended into one number (§9, §14).
- Recommendations are verification steps, never autonomous actions (§11).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Subsystem(str, Enum):
    """The four MVP subsystems in the thermal -> drivetrain chain (§8, §11A)."""

    COOLING = "cooling"
    BATTERY = "battery"
    MOTOR = "motor"
    INVERTER = "inverter"


class HealthState(str, Enum):
    OK = "ok"
    WATCH = "watch"
    FLAGGED = "flagged"


# --------------------------------------------------------------------------- #
# Stage 0 — Vehicle Data / Edge AI Core
# --------------------------------------------------------------------------- #
@dataclass
class SignalWindow:
    """A time-aligned window of telemetry for one subsystem.

    `features` is a mapping of sensor-channel name -> reduced feature value for
    the window (e.g. mean, slope). `quality` carries per-window data-health
    signals that the Trust Engine consumes.
    """

    subsystem: Subsystem
    t_start: float                       # window start (seconds, relative to run)
    t_end: float
    features: dict[str, float] = field(default_factory=dict)
    quality: "SignalQuality" = None      # populated by the ingestion stage


@dataclass
class SignalQuality:
    """Per-window data-health signals used by the Trust Engine (§9)."""

    noise_level: float = 0.0             # 0..1, higher = noisier
    dropout_rate: float = 0.0            # 0..1, fraction of samples lost
    missing_channels: float = 0.0        # 0..1, fraction of expected channels absent
    calibration_drift: float = 0.0       # 0..1
    channel_consistency: float = 1.0     # 0..1, agreement among co-moving sensors
    historical_similarity: float = 1.0   # 0..1, closeness to training distribution
    environmental_stress: float = 0.0    # 0..1, ambient/load extremeness


@dataclass
class FaultDetection:
    """Output of the Edge AI Core for a single subsystem window."""

    subsystem: Subsystem
    fault_probability: float             # 0..1, calibrated where possible
    model_confidence: float = 0.5        # 0..1, classifier's own calibrated confidence
    temporal_stability: float = 1.0      # 0..1, consistency across recent windows
    window: Optional[SignalWindow] = None


# --------------------------------------------------------------------------- #
# Stage 1 — Failure Propagation Engine (§8)
# --------------------------------------------------------------------------- #
@dataclass
class PropagationStep:
    """One hop along a predicted propagation path."""

    subsystem: Subsystem
    probability: float                   # P(fault reaches this node within horizon)
    eta_cycles: float                    # estimated operating cycles until observable


@dataclass
class PropagationPath:
    """A ranked propagation hypothesis: an origin and its downstream chain."""

    origin: Subsystem
    steps: list[PropagationStep] = field(default_factory=list)
    path_probability: float = 0.0        # overall likelihood of this chain
    next_node: Optional[Subsystem] = None
    eta_next_cycles: Optional[float] = None


# --------------------------------------------------------------------------- #
# Stage 2 — Trust Engine (§9)
# --------------------------------------------------------------------------- #
@dataclass
class TrustScore:
    """Decision-confidence score, kept SEPARATE from fault probability (§9, §14)."""

    value: float                         # 0..100
    factors: dict[str, float] = field(default_factory=dict)   # per-factor 0..1 contributions
    rationale: str = ""                  # human-readable, for the dashboard


# --------------------------------------------------------------------------- #
# Stage 3 — Impact Engine (§10)
# --------------------------------------------------------------------------- #
@dataclass
class ImpactScore:
    """Operational-priority score. Drives dashboard sort order, NOT probability."""

    value: float                         # 0..100
    factors: dict[str, float] = field(default_factory=dict)
    safety_relevant: bool = False


# --------------------------------------------------------------------------- #
# Stage 4 — Evidence-Based Decision Engine (§11)
# --------------------------------------------------------------------------- #
@dataclass
class Recommendation:
    """A verification/inspection step — never an autonomous action (§11)."""

    subsystem: Subsystem                 # where to look first (likely origin)
    reason: str                          # why this was generated
    evidence: list[str] = field(default_factory=list)     # signals/path that triggered it
    verification_step: str = ""          # concrete, human-actionable check
    missing_signals: list[str] = field(default_factory=list)
    trust: Optional[TrustScore] = None
    impact: Optional[ImpactScore] = None


# --------------------------------------------------------------------------- #
# Assembled pipeline output (what the API/dashboard consume)
# --------------------------------------------------------------------------- #
@dataclass
class PipelineResult:
    """Full technician-ready output for one signal-window evaluation."""

    detections: list[FaultDetection] = field(default_factory=list)
    best_path: Optional[PropagationPath] = None
    all_paths: list[PropagationPath] = field(default_factory=list)
    trust: Optional[TrustScore] = None
    impact: Optional[ImpactScore] = None
    recommendation: Optional[Recommendation] = None
    subsystem_health: dict[Subsystem, HealthState] = field(default_factory=dict)
