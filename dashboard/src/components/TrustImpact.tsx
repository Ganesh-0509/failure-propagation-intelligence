import type { ImpactScore, TrustScore } from "../types";
import { humanizeKey } from "../format";
import { Panel } from "./Panel";

interface Props {
  trust: TrustScore | null;
  impact: ImpactScore | null;
}

function FactorBars({ factors, tone }: { factors: Record<string, number>; tone: string }) {
  const entries = Object.entries(factors);
  return (
    <ul className="factors">
      {entries.map(([k, v]) => (
        <li key={k} className="factors__row">
          <span className="factors__label">{humanizeKey(k)}</span>
          <span className="factors__track">
            <span
              className={`factors__fill factors__fill--${tone}`}
              style={{ width: `${Math.max(0, Math.min(1, v)) * 100}%` }}
            />
          </span>
          <span className="factors__val">{Math.round(v * 100)}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Panel 3 — Trust Score + Impact Score.
 * Shown SIDE BY SIDE and never blended into one number (whitepaper hard rule).
 * Impact drives the alert sort order elsewhere in the app.
 */
export function TrustImpact({ trust, impact }: Props) {
  // Nominal window: no active prediction, so there is nothing to score.
  if (!trust || !impact) {
    return (
      <Panel
        title="Trust & Impact"
        subtitle="Two independent scores — shown separately, never merged"
        className="panel--scores"
      >
        <p className="panel__empty">No active prediction — subsystems nominal.</p>
      </Panel>
    );
  }

  return (
    <Panel
      title="Trust & Impact"
      subtitle="Two independent scores — shown separately, never merged"
      className="panel--scores"
    >
      <div className="scores">
        <div className="score score--trust">
          <div className="score__head">
            <span className="score__name">Trust</span>
            <span className="score__value">{Math.round(trust.value)}</span>
            <span className="score__scale">/ 100</span>
          </div>
          <p className="score__caption">Decision confidence — is the evidence reliable?</p>
          <FactorBars factors={trust.factors} tone="trust" />
          <p className="score__rationale">{trust.rationale}</p>
        </div>

        <div className="score__divider" aria-hidden />

        <div className="score score--impact">
          <div className="score__head">
            <span className="score__name">Impact</span>
            <span className="score__value">{Math.round(impact.value)}</span>
            <span className="score__scale">/ 100</span>
          </div>
          <p className="score__caption">
            Operational priority — how much does it matter?
            {impact.safety_relevant && (
              <span className="score__safety">safety-relevant</span>
            )}
          </p>
          <FactorBars factors={impact.factors} tone="impact" />
          <p className="score__rationale">
            Impact drives alert sort order. Higher impact is triaged first.
          </p>
        </div>
      </div>
      <p className="scores__foot">
        Trust and impact are kept distinct by design: a high-confidence reading of a
        low-priority fault is not the same as an urgent but uncertain one.
      </p>
    </Panel>
  );
}
