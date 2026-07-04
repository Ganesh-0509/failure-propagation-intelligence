import type { Health, Scenario } from "../types";
import { SUBSYSTEMS } from "../types";
import { title } from "../format";
import { Panel } from "./Panel";

interface Props {
  scenario: Scenario;
  current: number;
  onSeek: (i: number) => void;
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
 * Timeline VIEW — the full per-window event log. Each row is one evaluated
 * signal window with its worst-subsystem health, trust and impact. Clicking a
 * row selects the active window. The Play/scrub controls now live in the shared
 * top bar; this component is the log list only.
 */
export function Timeline({ scenario, current, onSeek }: Props) {
  const n = scenario.steps.length;

  return (
    <Panel
      title="Maintenance Timeline"
      subtitle={`${scenario.meta.kind} · window ${current + 1} of ${n}`}
      className="panel--timeline"
    >
      <ol className="log log--tall">
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
