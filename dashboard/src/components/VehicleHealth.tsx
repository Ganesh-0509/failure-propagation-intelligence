import type { Health } from "../types";
import { SUBSYSTEMS } from "../types";
import { HEALTH_LABEL, pct, title } from "../format";
import type { PipelineResult } from "../types";
import { Panel } from "./Panel";

interface Props {
  result: PipelineResult;
}

/** Panel 1 — Vehicle Health Overview: 4-subsystem status grid, colored by health. */
export function VehicleHealth({ result }: Props) {
  const detByName = new Map(result.detections.map((d) => [d.subsystem, d]));

  return (
    <Panel
      title="Vehicle Health Overview"
      subtitle="Per-subsystem status — thermal → drivetrain chain"
      className="panel--health"
    >
      <div className="health-grid">
        {SUBSYSTEMS.map((s) => {
          const health: Health = result.subsystem_health[s] ?? "ok";
          const det = detByName.get(s);
          return (
            <div key={s} className={`health-cell health-cell--${health}`}>
              <div className="health-cell__top">
                <span className="health-cell__name">{title(s)}</span>
                <span className={`health-dot health-dot--${health}`} aria-hidden />
              </div>
              <span className="health-cell__status">{HEALTH_LABEL[health]}</span>
              {det && (
                <span className="health-cell__prob">
                  fault {pct(det.fault_probability)}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
