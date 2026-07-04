import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Scenario, Subsystem } from "../types";
import { SUBSYSTEMS } from "../types";
import { title } from "../format";
import { Panel } from "./Panel";

interface Props {
  scenario: Scenario;
  selected: Subsystem;
  onSelect: (s: Subsystem) => void;
  currentStep: number;
}

const COLORS: Record<Subsystem, string> = {
  cooling: "#2563eb",
  battery: "#dc2626",
  motor: "#7c3aed",
  inverter: "#0891b2",
};

/**
 * Panel 5 — Signal Trends.
 * Recharts line chart of a chosen subsystem's fault_probability across the
 * scenario timeline. A reference line marks the current playback window.
 */
export function SignalTrends({ scenario, selected, onSelect, currentStep }: Props) {
  const data = useMemo(
    () =>
      scenario.steps.map((step, i) => {
        const det = step.detections.find((d) => d.subsystem === selected);
        return {
          window: i,
          fault: det ? Math.round(det.fault_probability * 100) : 0,
        };
      }),
    [scenario, selected],
  );

  return (
    <Panel
      title="Signal Trends"
      subtitle={`${title(selected)} fault probability across ${scenario.meta.n_windows} windows`}
      className="panel--trends"
      actions={
        <div className="seg">
          {SUBSYSTEMS.map((s) => (
            <button
              key={s}
              className={`seg__btn ${s === selected ? "seg__btn--active" : ""}`}
              onClick={() => onSelect(s)}
            >
              {title(s)}
            </button>
          ))}
        </div>
      }
    >
      <div className="chart">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: -12 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
            <XAxis
              dataKey="window"
              tick={{ fontSize: 11, fill: "var(--muted)" }}
              label={{
                value: "signal window",
                position: "insideBottom",
                offset: -2,
                fontSize: 11,
                fill: "var(--muted)",
              }}
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fontSize: 11, fill: "var(--muted)" }}
              unit="%"
            />
            <Tooltip
              contentStyle={{
                background: "var(--panel)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                fontSize: 12,
              }}
              formatter={(v: number) => [`${v}%`, "fault prob"]}
              labelFormatter={(l) => `window ${l}`}
            />
            <ReferenceLine
              x={currentStep}
              stroke="var(--accent)"
              strokeDasharray="4 3"
              label={{ value: "now", fontSize: 10, fill: "var(--accent)", position: "top" }}
            />
            <Line
              type="monotone"
              dataKey="fault"
              stroke={COLORS[selected]}
              strokeWidth={2.5}
              dot={{ r: 2 }}
              activeDot={{ r: 5 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}
