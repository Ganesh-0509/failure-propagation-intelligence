import { useState } from "react";
import type { DependencyGraph as Graph, Health } from "../types";
import { title } from "../format";
import { Panel } from "./Panel";

interface Props {
  graph: Graph;
  health: Record<string, Health>;
  source: "live" | "sample";
}

// Fixed layout positions for the canonical 4-subsystem chain (0..1 space).
const POS: Record<string, { x: number; y: number }> = {
  cooling: { x: 0.12, y: 0.3 },
  battery: { x: 0.42, y: 0.68 },
  motor: { x: 0.68, y: 0.28 },
  inverter: { x: 0.9, y: 0.66 },
};

const W = 520;
const H = 260;

/**
 * Panel 4 — Subsystem Dependency Graph (expandable).
 * Renders nodes + weighted edges from /api/graph. The structure is
 * domain-reasoning-based (§18) and flagged for SME review.
 */
export function DependencyGraph({ graph, health, source }: Props) {
  const [open, setOpen] = useState(true);

  const px = (n: string) => (POS[n]?.x ?? 0.5) * W;
  const py = (n: string) => (POS[n]?.y ?? 0.5) * H;

  return (
    <Panel
      title="Subsystem Dependency Graph"
      subtitle="Directed propagation graph with edge weights"
      className="panel--graph"
      actions={
        <button className="btn" onClick={() => setOpen((o) => !o)}>
          {open ? "Collapse" : "Expand"}
        </button>
      }
    >
      {open && (
        <>
          <div className="graph-scroll">
            <svg
              className="graph-svg"
              viewBox={`0 0 ${W} ${H}`}
              role="img"
              aria-label="Subsystem dependency graph"
            >
              <defs>
                <marker
                  id="arrow"
                  viewBox="0 0 10 10"
                  refX="9"
                  refY="5"
                  markerWidth="7"
                  markerHeight="7"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 0 L 10 5 L 0 10 z" className="graph-arrow" />
                </marker>
              </defs>

              {graph.edges.map((e) => {
                const x1 = px(e.source);
                const y1 = py(e.source);
                const x2 = px(e.target);
                const y2 = py(e.target);
                const mx = (x1 + x2) / 2;
                const my = (y1 + y2) / 2;
                return (
                  <g key={`${e.source}->${e.target}`} className="graph-edge">
                    <line
                      x1={x1}
                      y1={y1}
                      x2={x2}
                      y2={y2}
                      strokeWidth={1 + e.weight * 4}
                      markerEnd="url(#arrow)"
                    />
                    <text x={mx} y={my - 4} className="graph-edge__label">
                      w {e.weight.toFixed(2)} · lag {e.lag_cycles.toFixed(0)}
                    </text>
                  </g>
                );
              })}

              {graph.nodes.map((n) => {
                const h: Health = health[n.id] ?? "ok";
                return (
                  <g key={n.id} transform={`translate(${px(n.id)}, ${py(n.id)})`}>
                    <circle r={26} className={`graph-node graph-node--${h}`} />
                    {n.safety_relevant && (
                      <circle r={31} className="graph-node__safety-ring" />
                    )}
                    <text className="graph-node__label" textAnchor="middle" dy="0.35em">
                      {title(n.id)}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
          <div className="graph-foot">
            <span className="note note--sme">
              Domain-reasoning-based structure — review by SME (§18). Not a learned graph.
            </span>
            {source === "sample" && (
              <span className="badge badge--sample">sample graph</span>
            )}
          </div>
        </>
      )}
    </Panel>
  );
}
