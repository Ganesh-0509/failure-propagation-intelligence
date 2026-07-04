// ---------------------------------------------------------------------------
// FPI shared data contract (mirrors fpi/schemas.py — keep in sync with backend)
// The four subsystems are ALWAYS exactly these, in this canonical order.
// ---------------------------------------------------------------------------

export const SUBSYSTEMS = ["cooling", "battery", "motor", "inverter"] as const;
export type Subsystem = (typeof SUBSYSTEMS)[number];

export type Health = "ok" | "watch" | "flagged";

/** Per-subsystem fault detection output (Edge AI Core). */
export interface Detection {
  subsystem: string;
  fault_probability: number;
  model_confidence: number;
  temporal_stability: number;
}

/** One hop along a propagation path. */
export interface PathStep {
  subsystem: string;
  probability: number;
  eta_cycles: number;
}

/** A ranked propagation path (Stage 1). */
export interface PropagationPath {
  origin: string;
  steps: PathStep[];
  path_probability: number;
  // Null when the path is a single origin node with no forecast next hop.
  next_node: string | null;
  eta_next_cycles: number | null;
}

/** Trust score (Stage 2) — inspectable, never merged with impact. */
export interface TrustScore {
  value: number; // 0–100
  factors: Record<string, number>; // 7 keys
  rationale: string;
}

/** Impact score (Stage 3) — operational priority; drives alert sort order. */
export interface ImpactScore {
  value: number; // 0–100
  factors: Record<string, number>; // 6 keys
  safety_relevant: boolean;
}

/** Evidence-based verification recommendation (Stage 4). */
export interface Recommendation {
  subsystem: string;
  reason: string;
  evidence: string[];
  verification_step: string;
  missing_signals: string[];
  trust: TrustScore;
  impact: ImpactScore;
}

/** The full pipeline output for a single signal window.
 *
 * On NOMINAL windows (no subsystem's fault_probability crosses the alert
 * threshold) the backend emits null for best_path/trust/impact/recommendation.
 * subsystem_health and detections are always present. */
export interface PipelineResult {
  detections: Detection[];
  best_path: PropagationPath | null;
  all_paths: PropagationPath[];
  trust: TrustScore | null;
  impact: ImpactScore | null;
  recommendation: Recommendation | null;
  subsystem_health: Record<string, Health>;
}

// --- Graph -----------------------------------------------------------------

export interface GraphNode {
  id: string;
  safety_relevant: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
  lag_cycles: number;
}

export interface DependencyGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// --- Scenario (timeline) ---------------------------------------------------

export interface ScenarioMeta {
  kind: string;
  n_windows: number;
}

export interface Scenario {
  steps: PipelineResult[];
  meta: ScenarioMeta;
}

export interface HealthResponse {
  status: string;
}
