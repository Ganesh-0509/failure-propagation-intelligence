import { Fragment } from "react";
import type { PipelineResult } from "../types";
import { cycles, pct, title } from "../format";
import { Panel } from "./Panel";

interface Props {
  result: PipelineResult;
}

interface ChainNode {
  key: string;
  label: string;
  isOrigin: boolean;
  isNext: boolean;
  isTerminal: boolean;
}

/**
 * Panel 2 — Active Propagation Chain.
 * Renders best_path as a left-to-right chain with probability + ETA labels on
 * the arrows. Origin and next_node are highlighted. A terminal "Power derate"
 * outcome node closes the chain.
 */
export function PropagationChain({ result }: Props) {
  const { best_path } = result;

  const nodes: ChainNode[] = [
    {
      key: best_path.origin,
      label: title(best_path.origin),
      isOrigin: true,
      isNext: best_path.next_node === best_path.origin,
      isTerminal: false,
    },
    ...best_path.steps.map((s) => ({
      key: s.subsystem,
      label: title(s.subsystem),
      isOrigin: false,
      isNext: s.subsystem === best_path.next_node,
      isTerminal: false,
    })),
    {
      key: "power-derate",
      label: "Power Derate",
      isOrigin: false,
      isNext: false,
      isTerminal: true,
    },
  ];

  // Arrow i sits between node i and node i+1. Steps[i] describes the hop INTO
  // node i+1 (the origin has no incoming hop), so arrow before step node j uses
  // best_path.steps[j].
  return (
    <Panel
      title="Active Propagation Chain"
      subtitle={`Origin ${title(best_path.origin)} · next ${title(
        best_path.next_node,
      )} in ${cycles(best_path.eta_next_cycles)} · path probability ${pct(
        best_path.path_probability,
      )}`}
      className="panel--chain"
    >
      <div className="chain" role="list">
        {nodes.map((n, i) => {
          const incoming = i > 0 ? best_path.steps[i - 1] : undefined;
          return (
            <Fragment key={n.key}>
              {i > 0 && (
                <div className="chain__arrow" aria-hidden>
                  {incoming && (
                    <div className="chain__arrow-labels">
                      <span className="chain__arrow-prob">{pct(incoming.probability)}</span>
                      <span className="chain__arrow-eta">
                        ETA {cycles(incoming.eta_cycles)}
                      </span>
                    </div>
                  )}
                  <div className="chain__arrow-line">
                    <span className="chain__arrow-head">▶</span>
                  </div>
                </div>
              )}
              <div
                role="listitem"
                className={[
                  "chain__node",
                  n.isOrigin ? "chain__node--origin" : "",
                  n.isNext ? "chain__node--next" : "",
                  n.isTerminal ? "chain__node--terminal" : "",
                ].join(" ")}
              >
                <span className="chain__node-label">{n.label}</span>
                {n.isOrigin && <span className="chain__badge">origin</span>}
                {n.isNext && !n.isOrigin && (
                  <span className="chain__badge chain__badge--next">next</span>
                )}
                {n.isTerminal && (
                  <span className="chain__badge chain__badge--terminal">outcome</span>
                )}
              </div>
            </Fragment>
          );
        })}
      </div>
    </Panel>
  );
}
