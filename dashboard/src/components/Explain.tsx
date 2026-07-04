import type { ReactNode } from "react";

interface ExplainProps {
  /** Plain-English "what this shows" for a non-expert reviewer/technician. */
  what: ReactNode;
  /** "How it's computed / where it comes from" — accurate to the implementation. */
  how: ReactNode;
}

/**
 * Reusable explanation block shown under every view. Two labelled parts —
 * "What this shows" and "How it's computed / where it comes from" — styled as a
 * subtle card that is visually distinct from the data panels above it.
 */
export function Explain({ what, how }: ExplainProps) {
  return (
    <aside className="explain" aria-label="Explanation">
      <div className="explain__col">
        <span className="explain__label">What this shows</span>
        <div className="explain__body">{what}</div>
      </div>
      <div className="explain__divider" aria-hidden />
      <div className="explain__col">
        <span className="explain__label">How it&rsquo;s computed / where it comes from</span>
        <div className="explain__body">{how}</div>
      </div>
    </aside>
  );
}
