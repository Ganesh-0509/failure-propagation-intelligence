import { useCallback, useEffect, useState } from "react";
import type { DataSource } from "./api";
import { fetchGraph, fetchScenario } from "./api";
import type { DependencyGraph as Graph, Scenario, Subsystem } from "./types";
import { SAMPLE_GRAPH, SAMPLE_SCENARIO } from "./sampleScenario";
import type { ViewId } from "./nav";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { ViewRouter } from "./views";

/** First window with an active propagation chain, or 0 if all are nominal. */
function firstActiveWindow(scenario: Scenario): number {
  const idx = scenario.steps.findIndex((s) => s.best_path !== null);
  return idx === -1 ? 0 : idx;
}

export default function App() {
  const [scenario, setScenario] = useState<Scenario>(SAMPLE_SCENARIO);
  const [graph, setGraph] = useState<Graph>(SAMPLE_GRAPH);
  const [source, setSource] = useState<DataSource>("sample");
  const [loading, setLoading] = useState(true);

  // App-global time step — shared across every view so switching views keeps
  // the same window. Owned here; the top-bar scrubber and the Timeline view
  // both drive it through onSeek.
  const [current, setCurrent] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [selected, setSelected] = useState<Subsystem>("cooling");

  // Active view — client-side switching, no router.
  const [view, setView] = useState<ViewId>("overview");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [sc, gr] = await Promise.all([fetchScenario(), fetchGraph()]);
      if (cancelled) return;
      setScenario(sc.data);
      setGraph(gr.data);
      // "live" only if BOTH came from the backend.
      setSource(sc.source === "live" && gr.source === "live" ? "live" : "sample");
      // Open on the first interesting frame; panels still render safely if the
      // user scrubs back to a nominal window.
      setCurrent(firstActiveWindow(sc.data));
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const onSeek = useCallback(
    (i: number) => {
      const clamped = Math.max(0, Math.min(scenario.steps.length - 1, i));
      setCurrent(clamped);
    },
    [scenario.steps.length],
  );

  const result = scenario.steps[current] ?? scenario.steps[0];

  return (
    <div className="shell">
      <Sidebar view={view} onNavigate={setView} />

      <div className="main">
        <TopBar
          scenario={scenario}
          current={current}
          playing={playing}
          source={source}
          onSeek={onSeek}
          onTogglePlay={() => setPlaying((p) => !p)}
        />

        <div className="app__notice">
          Synthetic demonstration data — validates architecture &amp; workflow only,
          never accuracy. The system recommends verification steps, never autonomous
          action.
        </div>

        <main className="content">
          {loading ? (
            <div className="app__loading">Connecting to pipeline…</div>
          ) : (
            <ViewRouter
              view={view}
              result={result}
              scenario={scenario}
              graph={graph}
              source={source}
              current={current}
              selected={selected}
              onSelect={setSelected}
              onSeek={onSeek}
            />
          )}

          <footer className="app__footer">
            FPI MVP · engines are decoupled via one shared data contract · dependency
            graph is domain-reasoning-based (SME review needed) · trust factor weights
            are a design proposal pending calibration.
          </footer>
        </main>
      </div>
    </div>
  );
}
