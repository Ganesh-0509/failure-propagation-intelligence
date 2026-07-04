import type { Recommendation } from "../types";
import { title } from "../format";
import { Panel } from "./Panel";

interface Props {
  rec: Recommendation | null;
}

/** The non-autonomy disclaimer — shown on every window, nominal or not. */
const DISCLAIMER = (
  <p className="rec__disclaimer">
    Verification guidance only — never an autonomous action. A technician confirms
    and performs any physical inspection or repair.
  </p>
);

/**
 * Panel 6 — Recommended Verification Steps.
 * Shows the concrete verification step plus reason, evidence and missing
 * signals. Includes the mandatory non-autonomy disclaimer.
 */
export function Recommendations({ rec }: Props) {
  // Nominal window: nothing crossed the alert threshold, so no verification step.
  if (!rec) {
    return (
      <Panel
        title="Recommended Verification"
        subtitle="No target subsystem"
        className="panel--rec"
      >
        <div className="rec">
          <p className="panel__empty">
            No verification step required — all subsystems nominal.
          </p>
          {DISCLAIMER}
        </div>
      </Panel>
    );
  }

  return (
    <Panel
      title="Recommended Verification"
      subtitle={`Target subsystem: ${title(rec.subsystem)}`}
      className="panel--rec"
    >
      <div className="rec">
        <div className="rec__step">
          <span className="rec__step-label">Verification step</span>
          <p className="rec__step-text">{rec.verification_step}</p>
        </div>

        <div className="rec__block">
          <span className="rec__block-label">Why</span>
          <p className="rec__reason">{rec.reason}</p>
        </div>

        <div className="rec__block">
          <span className="rec__block-label">Evidence</span>
          <ul className="rec__list">
            {rec.evidence.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>

        {rec.missing_signals.length > 0 && (
          <div className="rec__block">
            <span className="rec__block-label rec__block-label--warn">Missing signals</span>
            <ul className="rec__list rec__list--muted">
              {rec.missing_signals.map((m, i) => (
                <li key={i}>{m}</li>
              ))}
            </ul>
          </div>
        )}

        {DISCLAIMER}
      </div>
    </Panel>
  );
}
