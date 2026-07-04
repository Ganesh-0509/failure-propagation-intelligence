"""Physics-informed synthetic scenario generator (whitepaper §8, §12 Category 2).

This module fabricates time-aligned telemetry for the four MVP subsystems so the
rest of the FPI pipeline (detection -> propagation -> trust -> impact ->
recommendation) can be exercised end-to-end without real vehicle data.

The flagship scenario is the thermal -> drivetrain propagation chain:

    cooling pump efficiency drops
        -> battery temperature rises              (cooling -> battery, lag ~2)
        -> battery internal resistance rises
        -> motor current rises (to hold torque)   (battery -> motor,   lag ~2)
        -> inverter thermal stress rises          (motor  -> inverter, lag ~1)
        -> power derate

Coupling is modelled with deliberately SIMPLE physics-informed heuristics
(saturating ramps with per-node lag), and the per-edge lags are read straight
from ``fpi.graph`` so the two stay consistent.

HONESTY GUARDRAIL (§11A, §12, §15): this is research/hackathon synthetic data.
It validates architecture and workflow ONLY -- propagation logic, trust
behaviour, dashboard wiring -- and is NEVER evidence of real-world accuracy.
Every number below is invented, not measured.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import numpy as np

from fpi.graph import build_dependency_graph
from fpi.schemas import SignalQuality, SignalWindow, Subsystem

# --------------------------------------------------------------------------- #
# Nominal operating points and fault spans (all invented, illustrative only)
# --------------------------------------------------------------------------- #
# Baseline feature values under healthy operation.
_BASELINE: dict[Subsystem, dict[str, float]] = {
    Subsystem.COOLING: {"flow_rate": 12.0, "pump_efficiency": 0.95},
    Subsystem.BATTERY: {"temp_c": 30.0, "internal_resistance": 0.020, "usable_current": 200.0},
    Subsystem.MOTOR: {"current_a": 120.0, "load_pct": 60.0},
    Subsystem.INVERTER: {"junction_temp_c": 65.0, "stress": 0.30, "power_derate_pct": 0.0},
}

# Full-severity (severity == 1.0) deltas applied on top of the baseline. Sign
# encodes the physical direction of the fault (efficiency/current drop, temps
# and resistance rise).
_FAULT_SPAN: dict[Subsystem, dict[str, float]] = {
    Subsystem.COOLING: {"flow_rate": -5.0, "pump_efficiency": -0.40},
    Subsystem.BATTERY: {"temp_c": +25.0, "internal_resistance": +0.030, "usable_current": -60.0},
    Subsystem.MOTOR: {"current_a": +80.0, "load_pct": +30.0},
    Subsystem.INVERTER: {"junction_temp_c": +45.0, "stress": +0.60, "power_derate_pct": +40.0},
}

# The primary propagation chain used to derive per-node onset lags from the graph.
_PRIMARY_CHAIN: list[Subsystem] = [
    Subsystem.COOLING,
    Subsystem.BATTERY,
    Subsystem.MOTOR,
    Subsystem.INVERTER,
]

# One window == one operating "cycle"; this many seconds of wall-clock per window.
_WINDOW_SECONDS: float = 10.0

# Time constant (in cycles) of the saturating fault ramp after onset.
_RAMP_TAU: float = 3.0

# Severity of the "primary" per-subsystem signal above which we consider the
# subsystem to be in a fault condition. Used by tests and downstream stages that
# want a single normalised fault indicator.
FAULT_THRESHOLD: float = 0.5

# The feature whose deviation-from-baseline best summarises each subsystem's
# health, plus the span used to normalise that deviation into a 0..1 severity.
_PRIMARY_SIGNAL: dict[Subsystem, str] = {
    Subsystem.COOLING: "pump_efficiency",
    Subsystem.BATTERY: "temp_c",
    Subsystem.MOTOR: "current_a",
    Subsystem.INVERTER: "stress",
}


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _clip01(x: float) -> float:
    """Clamp a scalar into the closed interval [0, 1]."""
    return float(min(1.0, max(0.0, x)))


def _ramp(t: int, onset: float, tau: float = _RAMP_TAU) -> float:
    """Saturating 0..~1 fault ramp: zero before ``onset``, then 1 - e^-(dt/tau)."""
    if t < onset:
        return 0.0
    return 1.0 - math.exp(-(t - onset) / tau)


def _onset_cycles(inject_at: int) -> dict[Subsystem, float]:
    """Per-subsystem fault onset (in window index), lagged along the graph edges.

    The cooling fault is injected at ``inject_at``; each downstream node's onset
    is the upstream onset plus that edge's ``lag_cycles`` from ``fpi.graph``, so
    onsets stay consistent with the dependency graph the propagation engine uses.
    """
    g = build_dependency_graph()
    onset: dict[Subsystem, float] = {Subsystem.COOLING: float(inject_at)}
    acc = float(inject_at)
    for parent, child in zip(_PRIMARY_CHAIN, _PRIMARY_CHAIN[1:]):
        acc += float(g[parent][child]["lag_cycles"])
        onset[child] = acc
    return onset


def _node_gain(inject_at: int) -> dict[Subsystem, float]:
    """Amplitude scaling per node from cumulative edge weights along the chain.

    Upstream faults propagate with some attenuation, so downstream subsystems get
    a slightly smaller (but still clearly visible) response. A floor keeps every
    node's cascade observable for demo/validation purposes.
    """
    g = build_dependency_graph()
    gain: dict[Subsystem, float] = {Subsystem.COOLING: 1.0}
    cum = 1.0
    for parent, child in zip(_PRIMARY_CHAIN, _PRIMARY_CHAIN[1:]):
        cum *= float(g[parent][child]["weight"])
        # Blend so even weakly-coupled nodes still show a clear rise (0.7..1.0).
        gain[child] = 0.7 + 0.3 * cum
    return gain


# --------------------------------------------------------------------------- #
# Feature / quality construction
# --------------------------------------------------------------------------- #
def _make_features(
    subsystem: Subsystem, severity: float, rng: np.random.Generator, noise: float
) -> dict[str, float]:
    """Build a subsystem's feature dict at a given fault ``severity`` (0..1)."""
    base = _BASELINE[subsystem]
    span = _FAULT_SPAN[subsystem]
    features: dict[str, float] = {}
    for name, base_value in base.items():
        value = base_value + span.get(name, 0.0) * severity
        # Additive sensor noise scaled to the channel's magnitude (5% -> ~noise).
        scale = max(abs(base_value), 1e-3) * noise * 0.05
        value += float(rng.normal(0.0, scale))
        features[name] = float(value)
    return features


def _make_quality(
    severity: float, rng: np.random.Generator, noise: float
) -> SignalQuality:
    """Populate a SignalQuality that degrades gracefully as the fault grows."""
    jitter = lambda s: float(rng.normal(0.0, noise * s))  # noqa: E731
    return SignalQuality(
        noise_level=_clip01(noise + jitter(0.2)),
        dropout_rate=_clip01(0.01 + 0.04 * severity + jitter(0.1)),
        missing_channels=_clip01(0.0 + jitter(0.02)),
        calibration_drift=_clip01(0.02 + 0.10 * severity + jitter(0.1)),
        channel_consistency=_clip01(1.0 - 0.15 * severity + jitter(0.1)),
        historical_similarity=_clip01(1.0 - 0.50 * severity + jitter(0.1)),
        environmental_stress=_clip01(0.05 + 0.60 * severity + jitter(0.1)),
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def generate_scenario(
    kind: str = "thermal_cascade",
    n_windows: int = 40,
    seed: int = 0,
    inject_at: int = 8,
    noise: float = 0.05,
) -> list[list[SignalWindow]]:
    """Generate a synthetic scenario as a list of per-time-step subsystem windows.

    Args:
        kind: scenario type. ``"thermal_cascade"`` injects a cooling-pump fault
            that propagates downstream; ``"nominal"`` produces a fault-free run.
        n_windows: number of time steps (windows) to produce.
        seed: seed for a local ``numpy`` ``Generator`` (deterministic; no global
            RNG or time-based seeding is used).
        inject_at: window index at which the cooling fault begins. Ignored for
            the nominal scenario. Values ``>= n_windows`` yield a nominal run.
        noise: 0..1 relative sensor-noise level applied to features and quality.

    Returns:
        A list of length ``n_windows``; each element is a list of exactly four
        ``SignalWindow`` objects, one per ``Subsystem`` (COOLING, BATTERY, MOTOR,
        INVERTER), in that fixed order.
    """
    if kind not in ("thermal_cascade", "nominal"):
        raise ValueError(
            f"unknown scenario kind {kind!r}; expected 'thermal_cascade' or 'nominal'"
        )

    rng = np.random.default_rng(seed)
    faulted = kind == "thermal_cascade"
    onsets = _onset_cycles(inject_at)
    gains = _node_gain(inject_at)

    scenario: list[list[SignalWindow]] = []
    for t in range(n_windows):
        step: list[SignalWindow] = []
        for subsystem in Subsystem:  # enum order == COOLING, BATTERY, MOTOR, INVERTER
            if faulted:
                severity = _clip01(gains[subsystem] * _ramp(t, onsets[subsystem]))
            else:
                severity = 0.0
            window = SignalWindow(
                subsystem=subsystem,
                t_start=t * _WINDOW_SECONDS,
                t_end=(t + 1) * _WINDOW_SECONDS,
                features=_make_features(subsystem, severity, rng, noise),
                quality=_make_quality(severity, rng, noise),
            )
            step.append(window)
        scenario.append(step)
    return scenario


def generate_nominal(
    n_windows: int = 40, seed: int = 0, noise: float = 0.05
) -> list[list[SignalWindow]]:
    """Generate a fault-free ("nominal") scenario. Convenience wrapper."""
    return generate_scenario(
        kind="nominal", n_windows=n_windows, seed=seed, noise=noise
    )


def window_severity(window: SignalWindow) -> float:
    """Normalised 0..1 fault indicator for a single window's primary signal.

    Compares the subsystem's primary feature to its baseline and normalises by the
    fault span. A healthy window sits near 0; a fully-developed fault approaches 1.
    Used by tests and any stage that wants a single fault scalar per window.
    """
    subsystem = window.subsystem
    name = _PRIMARY_SIGNAL[subsystem]
    base = _BASELINE[subsystem][name]
    span = _FAULT_SPAN[subsystem][name]
    if span == 0.0:
        return 0.0
    return _clip01((window.features[name] - base) / span)


# --------------------------------------------------------------------------- #
# Serialization helpers
# --------------------------------------------------------------------------- #
def to_records(scenario: list[list[SignalWindow]]) -> list[dict]:
    """Flatten a scenario into DataFrame-ready records (one row per window).

    Each record has ``t_index``, ``subsystem``, ``t_start``, ``t_end``, every
    feature (prefixed ``feat_``) and every quality signal (prefixed ``qual_``).
    Ready to hand to ``pandas.DataFrame(...)`` without importing pandas here.
    """
    records: list[dict] = []
    for t_index, step in enumerate(scenario):
        for window in step:
            row: dict = {
                "t_index": t_index,
                "subsystem": window.subsystem.value,
                "t_start": window.t_start,
                "t_end": window.t_end,
            }
            for k, v in window.features.items():
                row[f"feat_{k}"] = v
            if window.quality is not None:
                for k, v in asdict(window.quality).items():
                    row[f"qual_{k}"] = v
            records.append(row)
    return records


def scenario_to_dict(scenario: list[list[SignalWindow]], meta: Optional[dict] = None) -> dict:
    """Serialise a scenario (plus optional metadata) to a JSON-safe dict."""
    return {
        "meta": meta or {},
        "n_windows": len(scenario),
        "subsystems": [s.value for s in Subsystem],
        "records": to_records(scenario),
    }


def save_scenario(
    scenario: list[list[SignalWindow]],
    path: str | Path,
    meta: Optional[dict] = None,
) -> Path:
    """Write a scenario to ``path`` as JSON, creating parent dirs. Returns the path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = scenario_to_dict(scenario, meta=meta)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def load_scenario_records(path: str | Path) -> dict:
    """Load a scenario JSON written by :func:`save_scenario` (raw dict form)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Public-dataset loader STUB (§12 Category 1) -- intentionally not implemented
# --------------------------------------------------------------------------- #
def load_public_dataset(name: str):
    """Load a REAL public benchmark dataset for per-subsystem detector validation.

    Delegates to :mod:`fpi.datasets`, which parses genuine downloaded benchmarks
    into ``(X, y, feature_names)`` numpy tuples. Supported names (§12 Category 1),
    used to validate detectors IN ISOLATION:

      * ``"nasa_battery"`` -- NASA PCoE 18650 Li-ion battery aging dataset
        (:func:`fpi.datasets.load_battery_dataset`) -> BATTERY detector.
      * ``"cwru_bearing"`` -- CWRU rolling-element bearing vibration dataset
        (:func:`fpi.datasets.load_bearing_dataset`)  -> MOTOR detector.

    HONESTY BOUNDARY (§11A, §12, §15): these real datasets validate PER-SUBSYSTEM
    DETECTION ONLY. There is NO public dataset of real CROSS-SUBSYSTEM
    PROPAGATION, so the FPI propagation cascade (the rest of this module) stays
    SYNTHETIC and is never validated by real data. Real = detection; synthetic =
    propagation.

    The data is NOT auto-downloaded here; fetch it first with
    ``python scripts/fetch_datasets.py``. Dataset licenses (NASA PCoE = U.S.
    Government public domain; CWRU = free for academic/research use) are recorded
    in ``fpi.datasets.DATASET_SOURCES``.

    Returns:
        ``(X, y, feature_names)`` from the delegated loader.

    Raises:
        ValueError: if ``name`` is not a supported dataset.
        FileNotFoundError: if the dataset has not been downloaded yet (the error
            includes the exact fetch command).
    """
    # Imported lazily so fpi.synthetic has no hard dependency on scipy/loaders.
    from fpi import datasets

    key = name.strip().lower()
    loaders = {
        "nasa_battery": datasets.load_battery_dataset,
        "nasa": datasets.load_battery_dataset,
        "battery": datasets.load_battery_dataset,
        "cwru_bearing": datasets.load_bearing_dataset,
        "cwru": datasets.load_bearing_dataset,
        "bearing": datasets.load_bearing_dataset,
    }
    if key not in loaders:
        raise ValueError(
            f"unknown public dataset {name!r}; supported: 'nasa_battery' "
            f"(NASA Li-ion battery degradation) and 'cwru_bearing' "
            f"(CWRU bearing vibration). Fetch with "
            f"'python scripts/fetch_datasets.py'."
        )
    return loaders[key]()


__all__ = [
    "generate_scenario",
    "generate_nominal",
    "window_severity",
    "to_records",
    "scenario_to_dict",
    "save_scenario",
    "load_scenario_records",
    "load_public_dataset",
    "FAULT_THRESHOLD",
]
