// ---------------------------------------------------------------------------
// Bundled sample data — lets the dashboard render standalone (no backend).
//
// A realistic ~12-window "thermal_cascade" scenario: the cooling subsystem is
// flagged first, the fault then propagates downstream battery -> motor ->
// inverter, and trust/impact evolve as evidence accumulates.
//
// This is SYNTHETIC demonstration data. Per the whitepaper honesty guardrails
// it validates the dashboard workflow only — never accuracy.
// ---------------------------------------------------------------------------

import type {
  DependencyGraph,
  Health,
  PipelineResult,
  PropagationPath,
  Scenario,
  Subsystem,
} from "./types";

const ORDER: Subsystem[] = ["cooling", "battery", "motor", "inverter"];

// Per-subsystem fault_probability trajectories across 12 windows.
const FAULT: Record<Subsystem, number[]> = {
  cooling: [0.1, 0.18, 0.34, 0.52, 0.63, 0.71, 0.76, 0.79, 0.81, 0.82, 0.83, 0.84],
  battery: [0.05, 0.06, 0.09, 0.14, 0.22, 0.35, 0.48, 0.58, 0.64, 0.68, 0.71, 0.73],
  motor: [0.03, 0.03, 0.04, 0.05, 0.07, 0.1, 0.16, 0.24, 0.33, 0.42, 0.49, 0.55],
  inverter: [0.02, 0.02, 0.03, 0.03, 0.04, 0.05, 0.07, 0.1, 0.15, 0.21, 0.28, 0.35],
};

const N = FAULT.cooling.length;

function r2(x: number): number {
  return Math.round(x * 100) / 100;
}

function healthFor(p: number): Health {
  if (p >= 0.6) return "flagged";
  if (p >= 0.3) return "watch";
  return "ok";
}

/** Build the best propagation path for a given window index. */
function buildBestPath(i: number): PropagationPath {
  const t = i / (N - 1); // 0..1 progress through the cascade
  // Downstream hop probabilities grow as the cascade develops.
  const battP = r2(0.35 + 0.45 * t);
  const motorP = r2(0.2 + 0.4 * t);
  const invP = r2(0.12 + 0.33 * t);

  const steps = [
    { subsystem: "battery", probability: battP, eta_cycles: r2(3.0 - 1.2 * t) },
    { subsystem: "motor", probability: motorP, eta_cycles: r2(6.5 - 2.4 * t) },
    { subsystem: "inverter", probability: invP, eta_cycles: r2(10.0 - 3.5 * t) },
  ];

  // The "next" node is the earliest downstream subsystem not yet flagged.
  let nextIdx = 1;
  for (let k = 1; k < ORDER.length; k++) {
    if (FAULT[ORDER[k]][i] < 0.6) {
      nextIdx = k;
      break;
    }
    nextIdx = Math.min(k + 1, ORDER.length - 1);
  }
  const nextNode = ORDER[nextIdx];
  const nextStep = steps.find((s) => s.subsystem === nextNode) ?? steps[0];

  return {
    origin: "cooling",
    steps,
    path_probability: r2(0.3 + 0.4 * t),
    next_node: nextNode,
    eta_next_cycles: nextStep.eta_cycles,
  };
}

function buildStep(i: number): PipelineResult {
  const t = i / (N - 1);

  const detections = ORDER.map((s) => {
    const p = FAULT[s][i];
    return {
      subsystem: s,
      fault_probability: r2(p),
      // confidence climbs as more corroborating windows arrive
      model_confidence: r2(Math.min(0.95, 0.55 + 0.35 * t + (s === "cooling" ? 0.05 : 0))),
      // stability dips mid-cascade (transient) then firms up
      temporal_stability: r2(0.9 - 0.25 * Math.sin(Math.PI * t) * (p > 0.3 ? 1 : 0.3)),
    };
  });

  const subsystem_health: Record<string, Health> = {};
  for (const s of ORDER) subsystem_health[s] = healthFor(FAULT[s][i]);

  const best_path = buildBestPath(i);

  // Trust: inspectable 7-factor score, climbs from ~55 -> ~82.
  const trustFactors = {
    sensor_quality: r2(0.78 + 0.12 * t),
    temporal_stability: r2(0.62 + 0.28 * t),
    model_confidence: r2(0.58 + 0.32 * t),
    path_coherence: r2(0.6 + 0.3 * t),
    corroborating_signals: r2(0.45 + 0.45 * t),
    data_completeness: r2(0.7 + 0.2 * t),
    historical_consistency: r2(0.55 + 0.25 * t),
  };
  const trust = {
    value: r2(55 + 27 * t),
    factors: trustFactors,
    rationale:
      i < 3
        ? "Early signal: single-window thermal anomaly, limited corroboration."
        : i < 7
          ? "Rising coolant-flow anomaly corroborated across multiple windows; temporal stability improving."
          : "Sustained, multi-window thermal signature with high sensor quality and coherent downstream path.",
  };

  // Impact: 6-factor operational priority, climbs from ~30 -> ~88 as the
  // cascade threatens the safety-relevant battery.
  const impactFactors = {
    operational_risk: r2(0.4 + 0.5 * t),
    safety_relevance: r2(0.3 + 0.6 * t),
    propagation_reach: r2(0.25 + 0.6 * t),
    time_criticality: r2(0.35 + 0.55 * t),
    downtime_cost: r2(0.45 + 0.4 * t),
    cascade_severity: r2(0.3 + 0.6 * t),
  };
  const impact = {
    value: r2(30 + 58 * t),
    factors: impactFactors,
    safety_relevant: FAULT.battery[i] >= 0.3,
  };

  const evidence: string[] = [
    `Coolant-loop fault probability ${(FAULT.cooling[i] * 100).toFixed(0)}% across recent windows`,
  ];
  if (FAULT.battery[i] >= 0.3)
    evidence.push(
      `Battery thermal margin narrowing (downstream fault probability ${(FAULT.battery[i] * 100).toFixed(0)}%)`,
    );
  if (FAULT.motor[i] >= 0.3)
    evidence.push("Motor winding temperature trending upward in lockstep with coolant anomaly");

  const missing_signals: string[] = [];
  if (i < 5) missing_signals.push("coolant flow-rate sensor (currently inferred)");
  if (FAULT.battery[i] < 0.6) missing_signals.push("battery pack per-module temperature spread");

  const recommendation = {
    subsystem: "cooling",
    reason:
      "Cooling loop is the propagation origin; verifying it first can arrest the downstream thermal cascade toward the battery.",
    evidence,
    verification_step:
      "Inspect coolant flow sensor calibration and confirm pump duty-cycle response against commanded setpoint.",
    missing_signals,
    trust,
    impact,
  };

  return {
    detections,
    best_path,
    all_paths: [best_path],
    trust,
    impact,
    recommendation,
    subsystem_health,
  };
}

export const SAMPLE_SCENARIO: Scenario = {
  steps: Array.from({ length: N }, (_, i) => buildStep(i)),
  meta: { kind: "thermal_cascade", n_windows: N },
};

export const SAMPLE_GRAPH: DependencyGraph = {
  nodes: [
    { id: "cooling", safety_relevant: false },
    { id: "battery", safety_relevant: true },
    { id: "motor", safety_relevant: false },
    { id: "inverter", safety_relevant: true },
  ],
  edges: [
    { source: "cooling", target: "battery", weight: 0.85, lag_cycles: 2.0 },
    { source: "cooling", target: "motor", weight: 0.45, lag_cycles: 4.0 },
    { source: "battery", target: "motor", weight: 0.6, lag_cycles: 3.0 },
    { source: "battery", target: "inverter", weight: 0.55, lag_cycles: 3.5 },
    { source: "motor", target: "inverter", weight: 0.7, lag_cycles: 2.5 },
  ],
};
