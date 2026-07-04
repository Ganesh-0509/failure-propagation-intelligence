import { useCallback, useEffect, useState } from "react";
import type { DataSource } from "./api";
import { API_BASE, fetchGraph, fetchScenario } from "./api";
import type { DependencyGraph as Graph, Scenario, Subsystem } from "./types";
import { SAMPLE_GRAPH, SAMPLE_SCENARIO } from "./sampleScenario";
import { VehicleHealth } from "./components/VehicleHealth";
import { PropagationChain } from "./components/PropagationChain";
import { TrustImpact } from "./components/TrustImpact";
import { DependencyGraph } from "./components/DependencyGraph";
import { SignalTrends } from "./components/SignalTrends";
import { Recommendations } from "./components/Recommendations";
import { Timeline } from "./components/Timeline";

export default function App() {
  const [scenario, setScenario] = useState<Scenario>(SAMPLE_SCENARIO);
  const [graph, setGraph] = useState<Graph>(SAMPLE_GRAPH);
  const [source, setSource] = useState<DataSource>("sample");
  const [loading, setLoading] = useState(true);

  const [current, setCurrent] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [selected, setSelected] = useState<Subsystem>("cooling");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [sc, gr] = await Promise.all([fetchScenario(), fetchGraph()]);
      if (cancelled) return;
      setScenario(sc.data);
      setGraph(gr.data);
      // "live" only if BOTH came from the backend.
      setSource(sc.source === "live" && gr.source === "live" ? "live" : "sample");
      setCurrent(0);
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
    <div className="app">
      <header className="app__header">
        <div className="app__brand">
          <span className="app__logo">FPI</span>
          <div>
            <h1 className="app__title">Failure Propagation Intelligence</h1>
            <p className="app__tagline">Technician decision-support dashboard · §14 panel grid</p>
          </div>
        </div>
        <div className="app__status">
          <span className={`conn conn--${source}`}>
            <span className="conn__dot" aria-hidden />
            {source === "live" ? "Live API" : "Sample data (offline)"}
          </span>
          <span className="app__api" title="VITE_API_BASE">
            {API_BASE}
          </span>
        </div>
      </header>

      <div className="app__notice">
        Synthetic demonstration data — validates architecture &amp; workflow only, never
        accuracy. The system recommends verification steps, never autonomous action.
      </div>

      {loading ? (
        <div className="app__loading">Connecting to pipeline…</div>
      ) : (
        <main className="grid">
          <div className="grid__health">
            <VehicleHealth result={result} />
          </div>
          <div className="grid__chain">
            <PropagationChain result={result} />
          </div>
          <div className="grid__rec">
            <Recommendations rec={result.recommendation} />
          </div>
          <div className="grid__scores">
            <TrustImpact trust={result.trust} impact={result.impact} />
          </div>
          <div className="grid__graph">
            <DependencyGraph
              graph={graph}
              health={result.subsystem_health}
              source={source}
            />
          </div>
          <div className="grid__trends">
            <SignalTrends
              scenario={scenario}
              selected={selected}
              onSelect={setSelected}
              currentStep={current}
            />
          </div>
          <div className="grid__timeline">
            <Timeline
              scenario={scenario}
              current={current}
              playing={playing}
              onSeek={onSeek}
              onTogglePlay={() => setPlaying((p) => !p)}
            />
          </div>
        </main>
      )}

      <footer className="app__footer">
        FPI MVP · engines are decoupled via one shared data contract · dependency graph is
        domain-reasoning-based (SME review needed) · trust factor weights are a design
        proposal pending calibration.
      </footer>
    </div>
  );
}
