import { useEffect } from "react";
import type { DataSource } from "../api";
import type { Scenario } from "../types";

interface Props {
  scenario: Scenario;
  current: number;
  playing: boolean;
  source: DataSource;
  onSeek: (i: number) => void;
  onTogglePlay: () => void;
}

/**
 * Persistent top bar shown above the main content on every view. It owns the
 * app-global time-step scrubber (Play/Pause, Prev, Next, range slider, a
 * "window N/total" label) plus the live/offline status chip. Because it is
 * always mounted, switching views never interrupts playback and keeps the same
 * time step. The auto-advance interval lives here for the same reason.
 */
export function TopBar({
  scenario,
  current,
  playing,
  source,
  onSeek,
  onTogglePlay,
}: Props) {
  const n = scenario.steps.length;

  // Auto-advance while playing; loop back to the start at the end.
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      onSeek(current >= n - 1 ? 0 : current + 1);
    }, 1100);
    return () => clearInterval(id);
  }, [playing, current, n, onSeek]);

  return (
    <div className="topbar">
      <div className="topbar__transport">
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
      </div>

      <input
        className="topbar__scrub"
        type="range"
        min={0}
        max={n - 1}
        value={current}
        onChange={(e) => onSeek(Number(e.target.value))}
        aria-label="Scrub time step"
      />

      <span className="topbar__window" aria-live="polite">
        window <strong>{current + 1}</strong> / {n}
      </span>

      <span className={`conn conn--${source}`}>
        <span className="conn__dot" aria-hidden />
        {source === "live" ? "Live API" : "Offline sample"}
      </span>
    </div>
  );
}
