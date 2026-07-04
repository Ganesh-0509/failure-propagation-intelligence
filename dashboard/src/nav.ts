// ---------------------------------------------------------------------------
// Shared navigation model for the sidebar-driven views. The dashboard switches
// views client-side via a single `view` string in App state (no router).
// ---------------------------------------------------------------------------

export type ViewId =
  | "overview"
  | "propagation"
  | "trust"
  | "graph"
  | "trends"
  | "recommendations"
  | "timeline"
  | "how";

export interface NavItem {
  id: ViewId;
  label: string;
  /** Short caption shown under the label in the sidebar. */
  hint: string;
}

export const NAV_ITEMS: NavItem[] = [
  { id: "overview", label: "Overview", hint: "Vehicle health at a glance" },
  { id: "propagation", label: "Propagation Chain", hint: "Most likely fault path" },
  { id: "trust", label: "Trust & Impact", hint: "Two separate scores" },
  { id: "graph", label: "Dependency Graph", hint: "Subsystem influence map" },
  { id: "trends", label: "Signal Trends", hint: "Fault probability over time" },
  { id: "recommendations", label: "Recommendations", hint: "Verification step" },
  { id: "timeline", label: "Timeline", hint: "Per-window event log" },
  { id: "how", label: "How It Works", hint: "Pipeline & data honesty" },
];
