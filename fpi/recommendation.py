"""Stage 4 — Evidence-Based Decision Engine (whitepaper §11, §11A).

CRITICAL DESIGN RULE (§11, §11A): every recommendation this engine emits is an
*evidence-collection / inspection / verification* step. It is NEVER an autonomous
maintenance action such as "replace", "swap" or "install" a part. The system is
human-in-the-loop by design: it tells a technician *what to look at first and why*,
and the human decides what to do.

The engine is TEMPLATE-DRIVEN (§11A): the likely origin subsystem is looked up in a
fixed table of concrete, physically-actionable verification steps. This keeps the
output inspectable and prevents the model from ever inventing an action verb.

The wording also encodes the §11 "recurring engineering principles":
  - reason before recommend            -> a `reason` string is always produced first
  - estimate trust before deciding     -> low trust forces "verify BEFORE any action"
  - understand propagation before      -> the reason references the propagation path
    maintenance
"""
from __future__ import annotations

import re

from fpi.schemas import (
    FaultDetection,
    ImpactScore,
    PropagationPath,
    Recommendation,
    Subsystem,
    TrustScore,
)

# --------------------------------------------------------------------------- #
# Template table: likely-origin subsystem -> concrete verification step (§11A).
# Every entry is an INSPECTION / VERIFICATION step, not an action. The guard in
# `_assert_no_actions` enforces this at construction time.
# --------------------------------------------------------------------------- #
_VERIFICATION_TEMPLATES: dict[Subsystem, str] = {
    Subsystem.COOLING: (
        "Inspect coolant flow sensor calibration and physically verify coolant "
        "level and pump operation"
    ),
    Subsystem.BATTERY: (
        "Inspect battery module temperature and cell-voltage sensors and verify "
        "pack cooling contact and voltage balance across cells"
    ),
    Subsystem.MOTOR: (
        "Inspect motor winding-temperature and phase-current sensors and verify "
        "bearing vibration and torque response against expected limits"
    ),
    Subsystem.INVERTER: (
        "Inspect inverter IGBT thermal sensors and verify switching waveforms and "
        "DC-link voltage against expected operating limits"
    ),
}

# Expected sensor channels per subsystem — used to name channels that are present
# in the data contract but absent from an analyzed window (§9 missing data).
# These MUST match the feature keys produced by fpi.synthetic (the MVP data source);
# otherwise every channel reads as absent and missing_signals is over-reported.
_EXPECTED_CHANNELS: dict[Subsystem, list[str]] = {
    Subsystem.COOLING: ["flow_rate", "pump_efficiency"],
    Subsystem.BATTERY: ["temp_c", "internal_resistance", "usable_current"],
    Subsystem.MOTOR: ["current_a", "load_pct"],
    Subsystem.INVERTER: ["junction_temp_c", "stress", "power_derate_pct"],
}

# Action verbs that would signal an autonomous maintenance action rather than a
# verification step. The engine must NEVER emit any of these (§11).
_BANNED_ACTION_VERBS: frozenset[str] = frozenset(
    {
        "replace",
        "swap",
        "install",
        "uninstall",
        "remove",
        "refit",
        "fit",
        "mount",
        "dismount",
        "dismantle",
        "disconnect",
        "solder",
        "flash",
        "reprogram",
    }
)

_BANNED_RE = re.compile(
    r"\b(" + "|".join(sorted(_BANNED_ACTION_VERBS)) + r")\b", re.IGNORECASE
)


def _assert_no_actions(text: str) -> None:
    """Guard: raise if `text` contains an autonomous-action verb (§11 safeguard)."""
    match = _BANNED_RE.search(text)
    if match:
        raise AssertionError(
            f"recommendation text contains a banned autonomous-action verb "
            f"{match.group(0)!r}; recommendations must be verification steps only "
            f"(whitepaper §11). Offending text: {text!r}"
        )


class RecommendationEngine:
    """Produce an evidence-based verification `Recommendation` (§11, §11A).

    Combines a ranked `PropagationPath`, a `TrustScore`, an `ImpactScore` and the
    per-subsystem `FaultDetection`s into a single, human-actionable inspection
    step. The output is always a verification step — never an action.
    """

    #: Below this trust value the wording explicitly demands verification BEFORE
    #: any corrective action is taken (§11: estimate trust before deciding).
    LOW_TRUST_THRESHOLD: float = 50.0
    #: At/below this impact value the step may defer to monitoring / next service.
    LOW_IMPACT_THRESHOLD: float = 40.0
    #: Detections at/above this probability are called out as triggering evidence.
    EVIDENCE_PROBABILITY_THRESHOLD: float = 0.5

    # Templates are exposed for inspection/testing, mirroring the sibling engines.
    TEMPLATES: dict[Subsystem, str] = _VERIFICATION_TEMPLATES

    def __init__(self) -> None:
        # Fail fast: the fixed template table must never contain an action verb.
        for subsystem, template in self.TEMPLATES.items():
            _assert_no_actions(template)
            if subsystem not in _EXPECTED_CHANNELS:
                raise AssertionError(f"no expected-channels entry for {subsystem}")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def recommend(
        self,
        path: PropagationPath,
        trust: TrustScore,
        impact: ImpactScore,
        detections: list[FaultDetection],
    ) -> Recommendation:
        """Return a verification `Recommendation` for `path`.

        `subsystem` is the likely origin (where to look first). `trust` and
        `impact` are attached unchanged so the dashboard can show probability and
        trust as separate quantities (§9, §14).
        """
        origin = path.origin
        detections = list(detections or [])

        reason = self._build_reason(path, trust, impact)
        evidence = self._build_evidence(path, detections)
        missing_signals = self._infer_missing_signals(detections)
        verification_step = self._build_verification_step(origin, trust, impact)

        # Final safeguard: whatever we assembled, it must be a verification step.
        _assert_no_actions(verification_step)

        return Recommendation(
            subsystem=origin,
            reason=reason,
            evidence=evidence,
            verification_step=verification_step,
            missing_signals=missing_signals,
            trust=trust,
            impact=impact,
        )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _path_summary(self, path: PropagationPath) -> str:
        """Human-readable 'cooling -> battery -> motor' chain string."""
        chain = [path.origin.value] + [s.subsystem.value for s in path.steps]
        return " -> ".join(chain)

    def _build_reason(
        self, path: PropagationPath, trust: TrustScore, impact: ImpactScore
    ) -> str:
        """Explain WHY this was generated, referencing the propagation path.

        Encodes the §11 recurring engineering principles explicitly so the
        rationale is auditable: reason before recommend, estimate trust before
        deciding, understand propagation before maintenance.
        """
        chain = self._path_summary(path)
        parts = [
            f"Likely fault origin is the {path.origin.value} subsystem. "
            f"Propagation analysis projects the chain {chain} "
            f"with overall path probability {path.path_probability:.0%}."
        ]
        if path.next_node is not None:
            eta = path.eta_next_cycles
            eta_txt = "unknown" if eta is None else f"~{eta:.0f}"
            parts.append(
                f"The next node expected to show effects is {path.next_node.value} "
                f"in {eta_txt} operating cycles."
            )
        trust_val = getattr(trust, "value", None)
        impact_val = getattr(impact, "value", None)
        if trust_val is not None and impact_val is not None:
            parts.append(
                f"Decision trust is {trust_val:.0f}/100 and operational impact is "
                f"{impact_val:.0f}/100 (kept separate from fault probability)."
            )
        # The recurring engineering principles, stated so the output is auditable.
        parts.append(
            "Following the engineering principles (reason before recommend, "
            "estimate trust before deciding, understand propagation before "
            "maintenance), this is issued as a verification step only and not as "
            "an autonomous action."
        )
        return " ".join(parts)

    def _build_evidence(
        self, path: PropagationPath, detections: list[FaultDetection]
    ) -> list[str]:
        """List the signals / path facts that triggered the recommendation."""
        evidence: list[str] = [
            f"Propagation path {self._path_summary(path)} "
            f"(path_probability={path.path_probability:.2f})"
        ]
        if path.next_node is not None and path.eta_next_cycles is not None:
            evidence.append(
                f"Next node {path.next_node.value} in ~{path.eta_next_cycles:.0f} cycles"
            )
        for det in detections:
            if det.fault_probability >= self.EVIDENCE_PROBABILITY_THRESHOLD:
                evidence.append(
                    f"{det.subsystem.value} fault_probability="
                    f"{det.fault_probability:.2f} "
                    f"(model_confidence={det.model_confidence:.2f})"
                )
        return evidence

    def _infer_missing_signals(self, detections: list[FaultDetection]) -> list[str]:
        """Channels expected but absent, inferred from window quality (§9).

        A window whose `quality.missing_channels > 0` reports that some expected
        channels are absent. We name the specific expected channels that are not
        present in the window's features; if none can be named individually we
        still record the coverage gap so the technician knows data is incomplete.
        """
        missing: list[str] = []
        seen: set[str] = set()
        for det in detections:
            window = det.window
            quality = getattr(window, "quality", None) if window is not None else None
            # Ignore trivial gaps: a sub-5% missing fraction with all named channels
            # present is complete-enough data, not a reportable coverage gap.
            if quality is None or getattr(quality, "missing_channels", 0.0) < 0.05:
                continue
            expected = _EXPECTED_CHANNELS.get(det.subsystem, [])
            present = set((window.features or {}).keys())
            absent = [c for c in expected if c not in present]
            if absent:
                for channel in absent:
                    label = f"{det.subsystem.value}.{channel}"
                    if label not in seen:
                        seen.add(label)
                        missing.append(f"{label} (expected but absent in window)")
            else:
                frac = quality.missing_channels
                label = f"{det.subsystem.value}: ~{frac:.0%} of expected channels absent"
                if label not in seen:
                    seen.add(label)
                    missing.append(label)
        return missing

    def _build_verification_step(
        self, origin: Subsystem, trust: TrustScore, impact: ImpactScore
    ) -> str:
        """Assemble the concrete, human-actionable verification step.

        Starts from the fixed template for `origin`, then adapts the wording by
        trust and impact per §11 (estimate trust before deciding; low impact may
        defer to monitoring).
        """
        step = self.TEMPLATES[origin]
        clauses = [step + "."]

        trust_val = getattr(trust, "value", None)
        if trust_val is not None and trust_val < self.LOW_TRUST_THRESHOLD:
            clauses.append(
                "Decision trust is low, so verify these readings BEFORE any "
                "corrective action and confirm sensor integrity first."
            )

        impact_val = getattr(impact, "value", None)
        if impact_val is not None and impact_val <= self.LOW_IMPACT_THRESHOLD:
            clauses.append(
                "Operational impact is low; if no anomaly is confirmed, continue to "
                "monitor and re-check at the next scheduled service."
            )

        return " ".join(clauses)


__all__ = ["RecommendationEngine"]
