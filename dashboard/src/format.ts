import type { Health } from "./types";

/** Format a 0..1 probability as a percentage string. */
export function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

/** Format an ETA in cycles. */
export function cycles(x: number): string {
  return `${x.toFixed(1)} cyc`;
}

/** Title-case a subsystem id. */
export function title(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const HEALTH_LABEL: Record<Health, string> = {
  ok: "OK",
  watch: "Watch",
  flagged: "Flagged",
};

/** Human-readable factor key, e.g. "sensor_quality" -> "Sensor quality". */
export function humanizeKey(k: string): string {
  const s = k.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}
