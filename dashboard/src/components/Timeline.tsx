import { useEffect } from "react";
import type { Health, Scenario } from "../types";
import { SUBSYSTEMS } from "../types";
import { title } from "../format";
import { Panel } from "./Panel";

interface Props {
  scenario: Scenario;
  current: number;
  playing: boolean;
  onSeek: (i: number) => void;
  onTogglePlay: () => void;
}

/** Highest-severity health across subsystems, for the row indicator dot. */
function worstHealth(health: Record<string, Health>): Health {
  const order: Health[] = ["ok", "watch", "flagged"];
  let worst: Health = "ok";
  for (const s of SUBSYSTEMS) {
    const h = health[s] ?? "ok";
    if (order.indexOf(h) > order.indexOf(worst)) worst = h;
  }
  return worst;
}

/**
 * Panel 7 — Maintenance Timeline / logs.
 * A scrubbable list stepping through the scenario. The play/scrub control
 * advances the "current" PipelineResult that drives every panel above.
 */
export function Timeline({ scenario, current, playing, onSeek, onTogglePlay }: Props) {
  const n = scenario.steps.length;

  // Auto-advance while playing; stop at the end.
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      onSeek(current >= n - 1 ? 0 : current + 1);
    }, 1100);
    return () => clearInterval(id);
  }, [playing, current, n, onSeek]);

  return (
    <Panel
      title="Maintenance Timeline"
      subtitle={`${scenario.meta.kind} · window ${current + 1} of ${n}`}
      className="panel--timeline"
      actions={
        <div className="transport">
          <button className="btn btn--primary" onClick={onTogglePlay}>
            {playing ? "❚❚ Pause" : "▶ Play"}
          </button>
          <button
            className="btn"
            onClick={() => onSeek(Math.max(0, current - 1))}
            disabled={current === 0}
          >
            ‹ Prev
          </button>
          <button
            className="btn"
            onClick={() => onSeek(Math.min(n - 1, current + 1))}
            disabled={current === n - 1}
          >
            Next ›
          </button>
          <input
            className="scrub"
            type="range"
            min={0}
            max={n - 1}
            value={current}
            onChange={(e) => onSeek(Number(e.target.value))}
            aria-label="Scrub timeline"
          />
        </div>
      }
    >
      <ol className="log">
        {scenario.steps.map((step, i) => {
          const w = worstHealth(step.subsystem_health);
          const flagged = SUBSYSTEMS.filter(
            (s) => step.subsystem_health[s] === "flagged",
          ).map(title);
          // best_path/trust/impact are null on nominal windows — guard each.
          const bp = step.best_path;
          const nextLabel = bp?.next_node ? title(bp.next_node) : null;
          const watchLabel = bp ? title(bp.origin) : null;
          const desc = flagged.length
            ? `${flagged.join(", ")} flagged${
                nextLabel ? ` · next ${nextLabel}` : ""
              }`
            : watchLabel
              ? `nominal · watching ${watchLabel}`
              : "nominal";
          return (
            <li
              key={i}
              className={`log__row ${i === current ? "log__row--active" : ""}`}
              onClick={() => onSeek(i)}
            >
              <span className={`health-dot health-dot--${w}`} aria-hidden />
              <span className="log__win">W{i}</span>
              <span className="log__desc">{desc}</span>
              <span className="log__scores">
                T {step.trust ? Math.round(step.trust.value) : "—"} · I{" "}
                {step.impact ? Math.round(step.impact.value) : "—"}
              </span>
            </li>
          );
        })}
      </ol>
    </Panel>
  );
}
