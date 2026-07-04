"""Edge AI Core — per-subsystem fault detection (whitepaper §7, §12 Category 1).

This stage turns a time-aligned ``SignalWindow`` for a single subsystem into a
``FaultDetection`` carrying three SEPARATE quantities (§9, §14):

  - ``fault_probability`` — "how likely is a fault?" (calibrated where possible)
  - ``model_confidence``  — the classifier's own decisiveness on THIS window
  - ``temporal_stability``— consistency of the verdict across recent windows

Crucially this module answers only "how likely" — it never computes *trust*
("how much should a technician rely on it"). Trust is a separate engine that
consumes data-quality signals (see ``fpi/trust.py``). Keeping probability and
trust orthogonal is a core whitepaper guardrail.

Modelling approach (MVP, §7):
  - One lightweight scikit-learn classifier PER subsystem, because each
    subsystem exposes a different set of sensor channels.
  - Probabilities are calibrated (``CalibratedClassifierCV``) so
    ``fault_probability`` and ``model_confidence`` are meaningful and distinct.
  - An ONNX export path is provided for edge deployment; if the optional
    ``skl2onnx`` / ``onnx`` packages are absent, export is skipped and the
    scikit-learn model remains the demo fallback.

HONESTY NOTE: ``default_detector()`` trains on a small, internally generated,
seeded toy dataset so the module is usable out-of-the-box for the demo. This is
a stand-in ONLY — it validates the workflow, never accuracy. Real per-subsystem
training uses public benchmarks (NASA battery degradation, CWRU bearing;
dataset licenses to be verified before use — §12, §15).
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from fpi.schemas import FaultDetection, SignalWindow, Subsystem

logger = logging.getLogger(__name__)

# How many recent windows contribute to the temporal-stability estimate.
_STABILITY_WINDOW = 5


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _clip01(x: float) -> float:
    """Clamp to the closed unit interval and return a plain float."""
    return float(min(1.0, max(0.0, x)))


@dataclass
class _ConstantModel:
    """Degenerate fallback used when a subsystem's training labels have a single
    class. Emits a fixed, softened probability so the pipeline still runs."""

    fault_probability: float

    def predict_fault_proba(self, X: np.ndarray) -> np.ndarray:
        return np.full(len(X), self.fault_probability, dtype=float)


class _SubsystemModel:
    """A calibrated per-subsystem classifier plus its fixed feature ordering.

    The feature ordering is captured at ``fit`` time so that inference builds the
    input vector in exactly the same column order, and tolerates windows whose
    ``features`` dict is missing or has extra channels.
    """

    def __init__(self, feature_names: list[str]):
        self.feature_names = feature_names
        self._model = None            # CalibratedClassifierCV or _ConstantModel
        self._fault_index = 1         # column of P(fault) in predict_proba

    # -- vectorisation ---------------------------------------------------- #
    def vectorize(self, window: SignalWindow) -> np.ndarray:
        feats = window.features or {}
        return np.array(
            [float(feats.get(name, 0.0)) for name in self.feature_names],
            dtype=float,
        )

    def _matrix(self, windows: list[SignalWindow]) -> np.ndarray:
        if not windows:
            return np.empty((0, len(self.feature_names)), dtype=float)
        return np.vstack([self.vectorize(w) for w in windows])

    # -- training --------------------------------------------------------- #
    def fit(self, windows: list[SignalWindow], labels: list[int]) -> "_SubsystemModel":
        X = self._matrix(windows)
        y = np.asarray(labels, dtype=int)
        classes = np.unique(y)

        if classes.size < 2:
            # Cannot train a discriminative model on one class — fall back to a
            # constant, softened toward the seen class so it never asserts 0/1.
            only = int(classes[0]) if classes.size else 0
            self._model = _ConstantModel(0.9 if only == 1 else 0.1)
            return self

        # Small, cheap, interpretable base learner; standardised inputs.
        base = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=1000),
        )
        # Calibrate so predict_proba is a meaningful probability, not just a
        # monotone score. cv folds are bounded by the rarest class count.
        n_folds = int(min(3, np.min(np.bincount(y))))
        if n_folds >= 2:
            model = CalibratedClassifierCV(base, method="sigmoid", cv=n_folds)
        else:
            # Too few samples to calibrate; use the base learner's own proba.
            model = base
        model.fit(X, y)
        self._model = model
        self._fault_index = int(np.where(model.classes_ == 1)[0][0])
        return self

    # -- inference -------------------------------------------------------- #
    def predict_fault_proba(self, window: SignalWindow) -> float:
        if self._model is None:
            raise RuntimeError("subsystem model used before fit()")
        X = self.vectorize(window).reshape(1, -1)
        if isinstance(self._model, _ConstantModel):
            return _clip01(self._model.predict_fault_proba(X)[0])
        proba = self._model.predict_proba(X)[0]
        return _clip01(proba[self._fault_index])


# --------------------------------------------------------------------------- #
# Public detector
# --------------------------------------------------------------------------- #
class FaultDetector:
    """Per-subsystem Edge AI Core fault detector.

    Usage::

        det = FaultDetector()
        det.fit(windows_by_subsystem, labels)      # dicts keyed by Subsystem
        fd = det.detect(a_window)                   # -> FaultDetection
        fds = det.detect_all(list_of_windows)       # temporal_stability filled in
    """

    def __init__(self) -> None:
        self._models: dict[Subsystem, _SubsystemModel] = {}

    @property
    def fitted_subsystems(self) -> list[Subsystem]:
        return list(self._models.keys())

    def fit(
        self,
        windows_by_subsystem: dict[Subsystem, list[SignalWindow]],
        labels: dict[Subsystem, list[int]],
    ) -> "FaultDetector":
        """Train one calibrated classifier per subsystem.

        Args:
            windows_by_subsystem: maps each ``Subsystem`` to its training windows.
            labels: maps each ``Subsystem`` to aligned 0/1 fault labels
                (1 == fault present).
        """
        for subsystem, windows in windows_by_subsystem.items():
            y = labels.get(subsystem)
            if y is None:
                raise ValueError(f"no labels provided for {subsystem}")
            if len(y) != len(windows):
                raise ValueError(
                    f"{subsystem}: {len(windows)} windows but {len(y)} labels"
                )
            # Fixed, deterministic column order from the union of observed channels.
            feature_names = sorted(
                {k for w in windows for k in (w.features or {}).keys()}
            )
            self._models[subsystem] = _SubsystemModel(feature_names).fit(windows, y)
        return self

    def detect(self, window: SignalWindow) -> FaultDetection:
        """Score a single window. ``temporal_stability`` is left at its neutral
        default (1.0) because a lone window has no history; use ``detect_all``
        for a sequence to get a real stability estimate."""
        model = self._models.get(window.subsystem)
        if model is None:
            raise ValueError(
                f"no trained model for {window.subsystem}; call fit() first"
            )
        p = model.predict_fault_proba(window)
        # model_confidence: decisiveness on THIS window — probability mass on the
        # predicted class, in [0.5, 1]. Distinct from fault_probability, which is
        # specifically P(fault). A window at p=0.5 is maximally undecided.
        confidence = max(p, 1.0 - p)
        return FaultDetection(
            subsystem=window.subsystem,
            fault_probability=p,
            model_confidence=_clip01(confidence),
            temporal_stability=1.0,
            window=window,
        )

    def detect_all(self, windows: list[SignalWindow]) -> list[FaultDetection]:
        """Score a sequence of windows in order, filling ``temporal_stability``
        from a small rolling buffer of recent fault probabilities per subsystem.

        Stability is high when consecutive windows agree (a persistent fault or a
        steady nominal reading) and low when the verdict flickers — a cheap proxy
        for "is this a stable observation or transient noise?"."""
        history: dict[Subsystem, deque[float]] = {}
        detections: list[FaultDetection] = []
        for window in windows:
            fd = self.detect(window)
            buf = history.setdefault(
                window.subsystem, deque(maxlen=_STABILITY_WINDOW)
            )
            buf.append(fd.fault_probability)
            fd.temporal_stability = self._stability(buf)
            detections.append(fd)
        return detections

    @staticmethod
    def _stability(recent: deque[float]) -> float:
        """Map dispersion of recent fault probabilities to a 0..1 stability.

        One sample -> fully stable (nothing to disagree with). Otherwise use the
        spread of probabilities: the std of values in [0,1] is at most 0.5, so
        ``1 - 2*std`` maps a perfectly split history to 0 and a constant one to 1.
        """
        if len(recent) < 2:
            return 1.0
        std = float(np.std(np.asarray(recent, dtype=float)))
        return _clip01(1.0 - 2.0 * std)

    # -- optional edge export -------------------------------------------- #
    def export_onnx(self, path: str) -> bool:
        """Export each per-subsystem model to ONNX for edge deployment.

        Writes one ``<subsystem>.onnx`` file under ``path`` (created if needed).
        Requires the optional ``skl2onnx`` + ``onnx`` packages; if they are not
        installed the export is logged and skipped, and the scikit-learn models
        remain the demo fallback. Returns True only if all models were exported.
        """
        try:
            from pathlib import Path

            import skl2onnx  # noqa: F401
            from skl2onnx import to_onnx
        except ImportError:
            logger.warning(
                "ONNX export skipped: skl2onnx/onnx not installed; "
                "scikit-learn models remain the demo fallback."
            )
            return False

        out_dir = Path(path)
        out_dir.mkdir(parents=True, exist_ok=True)
        exported = 0
        for subsystem, model in self._models.items():
            if isinstance(model._model, _ConstantModel) or model._model is None:
                logger.warning(
                    "skipping ONNX export for %s: no trainable model", subsystem
                )
                continue
            n_features = len(model.feature_names)
            sample = np.zeros((1, n_features), dtype=np.float32)
            onx = to_onnx(model._model, sample)
            (out_dir / f"{subsystem.value}.onnx").write_bytes(
                onx.SerializeToString()
            )
            exported += 1
        return exported == len(self._models) and exported > 0


# --------------------------------------------------------------------------- #
# Demo stand-in training data + factory
# --------------------------------------------------------------------------- #
# Per-subsystem (baseline, fault-delta) for each channel. This intentionally
# mirrors the physics-informed heuristics in fpi/synthetic.py but is kept LOCAL
# so the detector trains without any external data. DEMO ONLY — not real data.
_TOY_BASELINE: dict[Subsystem, dict[str, tuple[float, float]]] = {
    Subsystem.COOLING: {"flow_rate": (12.0, -6.0), "pump_efficiency": (0.95, -0.40)},
    Subsystem.BATTERY: {
        "temp_c": (30.0, +25.0),
        "internal_resistance": (0.020, +0.030),
        "usable_current": (200.0, -60.0),
    },
    Subsystem.MOTOR: {"current_a": (120.0, +80.0), "load_pct": (60.0, +30.0)},
    Subsystem.INVERTER: {
        "junction_temp_c": (65.0, +45.0),
        "stress": (0.30, +0.60),
        "power_derate_pct": (0.0, +40.0),
    },
}


def _toy_training_data(
    seed: int = 0, n_per_class: int = 120
) -> tuple[dict[Subsystem, list[SignalWindow]], dict[Subsystem, list[int]]]:
    """Generate a small, seeded, class-balanced toy dataset per subsystem.

    Nominal samples draw a low fault severity; faulty samples a high one, with
    additive sensor noise so the classes overlap enough for calibration to be
    meaningful. Uses a LOCAL numpy Generator only (no global/`time`-based seed).
    """
    rng = np.random.default_rng(seed)
    windows_by_subsystem: dict[Subsystem, list[SignalWindow]] = {}
    labels: dict[Subsystem, list[int]] = {}

    for subsystem, channels in _TOY_BASELINE.items():
        windows: list[SignalWindow] = []
        ys: list[int] = []
        for label in (0, 1):
            for _ in range(n_per_class):
                if label == 0:
                    severity = float(rng.uniform(0.0, 0.25))
                else:
                    severity = float(rng.uniform(0.5, 1.0))
                features: dict[str, float] = {}
                for name, (base, delta) in channels.items():
                    value = base + delta * severity
                    scale = max(abs(base), 1e-3) * 0.05
                    value += float(rng.normal(0.0, scale))
                    features[name] = value
                windows.append(
                    SignalWindow(
                        subsystem=subsystem,
                        t_start=0.0,
                        t_end=1.0,
                        features=features,
                    )
                )
                ys.append(label)
        windows_by_subsystem[subsystem] = windows
        labels[subsystem] = ys
    return windows_by_subsystem, labels


def default_detector(seed: int = 0) -> FaultDetector:
    """Return a ``FaultDetector`` trained on the seeded toy dataset.

    Convenience factory so the Edge AI Core is usable without external data.
    DEMO STAND-IN ONLY: validates the pipeline/workflow, never accuracy. Swap the
    training set for public benchmarks (NASA battery, CWRU bearing) for anything
    beyond the demo.
    """
    windows_by_subsystem, labels = _toy_training_data(seed=seed)
    return FaultDetector().fit(windows_by_subsystem, labels)


__all__ = ["FaultDetector", "default_detector"]
