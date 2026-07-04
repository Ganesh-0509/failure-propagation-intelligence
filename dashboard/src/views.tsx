// ---------------------------------------------------------------------------
// View layer. Each sidebar section is its own view: the reused panel
// component(s) plus an <Explain/> block written to be accurate to the real
// implementation (see docs/DATASETS.md and the whitepaper section notes). The
// shared time-step `current` is passed down so every view reflects the same
// window the top-bar scrubber selects.
// ---------------------------------------------------------------------------

import type { DataSource } from "./api";
import type {
  DependencyGraph as Graph,
  PipelineResult,
  Scenario,
  Subsystem,
} from "./types";
import type { ViewId } from "./nav";

import { VehicleHealth } from "./components/VehicleHealth";
import { PropagationChain } from "./components/PropagationChain";
import { TrustImpact } from "./components/TrustImpact";
import { DependencyGraph } from "./components/DependencyGraph";
import { SignalTrends } from "./components/SignalTrends";
import { Recommendations } from "./components/Recommendations";
import { Timeline } from "./components/Timeline";
import { Explain } from "./components/Explain";

export interface ViewProps {
  view: ViewId;
  result: PipelineResult;
  scenario: Scenario;
  graph: Graph;
  source: DataSource;
  current: number;
  selected: Subsystem;
  onSelect: (s: Subsystem) => void;
  onSeek: (i: number) => void;
}

/** Small header shown at the top of each view. */
function ViewHeader({ title, lede }: { title: string; lede: string }) {
  return (
    <div className="view__header">
      <h1 className="view__title">{title}</h1>
      <p className="view__lede">{lede}</p>
    </div>
  );
}

/* -- Overview (Vehicle Health) --------------------------------------------- */
function OverviewView({ result }: ViewProps) {
  return (
    <section className="view">
      <ViewHeader
        title="Overview"
        lede="Single-glance health of the four subsystems in this time step."
      />
      <div className="view__intro">
        <span className="view__intro-label">What is FPI?</span>
        <p>
          Failure Propagation Intelligence (FPI) models the electric vehicle as a
          graph of connected subsystems — cooling, battery, motor, inverter — and
          reasons about how a fault in one part <em>propagates</em> to the others,
          rather than raising an isolated alert per component. That lets it point
          at the likely root cause and what it will affect next, not just the
          loudest symptom.
        </p>
      </div>
      <VehicleHealth result={result} />
      <Explain
        what={
          <p>
            Health of the four subsystems at the selected time step. Each cell is
            OK, Watch, or Flagged so a technician can see the state of the vehicle
            at a glance before drilling into any one subsystem.
          </p>
        }
        how={
          <p>
            Each subsystem&rsquo;s health comes from its own fault-detection
            probability, banded with fixed thresholds: <strong>OK</strong> below
            0.35, <strong>Watch</strong> from 0.35 to 0.60, and{" "}
            <strong>Flagged</strong> at 0.60 or above. The probability shown on
            each cell is the per-subsystem detector&rsquo;s output for this window.
          </p>
        }
      />
    </section>
  );
}

/* -- Propagation Chain ------------------------------------------------------ */
function PropagationView({ result }: ViewProps) {
  return (
    <section className="view">
      <ViewHeader
        title="Propagation Chain"
        lede="The most likely fault path: origin → downstream subsystems → power derate."
      />
      <PropagationChain result={result} />
      <Explain
        what={
          <p>
            The single most likely fault path for this window — where the trouble
            started (origin), which subsystems it flows into, and the eventual
            power-derate outcome. The next-at-risk node is highlighted with an ETA
            in operating cycles. On a nominal window there is no active chain.
          </p>
        }
        how={
          <>
            <p>
              A directed dependency graph is walked, and each candidate origin is
              scored as a <strong>root cause</strong>: it is penalised for having
              an elevated upstream ancestor and rewarded when its predicted
              downstream victims are also elevated. That way the true origin (for
              example cooling) is identified even when a downstream node (the
              inverter) shows the loudest symptom.
            </p>
            <p>
              ETA comes from per-edge lag in operating cycles. The graph itself is
              hand-specified from automotive domain reasoning — not learned or
              statistically validated (§18).
            </p>
          </>
        }
      />
    </section>
  );
}

/* -- Trust & Impact --------------------------------------------------------- */
function TrustView({ result }: ViewProps) {
  return (
    <section className="view">
      <ViewHeader
        title="Trust & Impact"
        lede="Two independent 0–100 scores, shown separately, never merged."
      />
      <TrustImpact trust={result.trust} impact={result.impact} />
      <Explain
        what={
          <p>
            Two separate 0–100 scores shown side by side. <strong>Trust</strong>{" "}
            answers &ldquo;how much should I rely on this prediction?&rdquo; and{" "}
            <strong>Impact</strong> answers &ldquo;how much does it matter
            operationally?&rdquo; They are deliberately never combined into a
            single number.
          </p>
        }
        how={
          <>
            <p>
              <strong>Trust</strong> is a transparent, rule-based weighted blend of
              seven factors: sensor quality, historical similarity, signal
              consistency, missing data, model confidence, environmental
              conditions, and temporal stability.
            </p>
            <p>
              <strong>Impact</strong> is a separate consequence-only score from six
              factors: operational risk, safety influence, propagation severity,
              service urgency, repair cost, and vehicle availability. Impact
              deliberately does <em>not</em> use fault probability, and Trust is
              never folded into Impact — the two axes stay independent by design
              (§9/§14).
            </p>
          </>
        }
      />
    </section>
  );
}

/* -- Dependency Graph ------------------------------------------------------- */
function GraphView({ result, graph, source }: ViewProps) {
  return (
    <section className="view">
      <ViewHeader
        title="Dependency Graph"
        lede="The directed subsystem influence graph with edge weights and lags."
      />
      <DependencyGraph graph={graph} health={result.subsystem_health} source={source} />
      <Explain
        what={
          <p>
            The directed graph of how subsystems influence one another. Each edge
            carries a weight (how strong the influence is) and a lag (how many
            operating cycles it takes to propagate). Node colour reflects the
            current health of that subsystem.
          </p>
        }
        how={
          <p>
            The structure is hand-specified from automotive domain reasoning — for
            example cooling→battery is strong and motor→inverter is strong. It is a
            starting point for engineering review by a domain expert, <em>not</em>{" "}
            a learned or statistically validated causal model (§18).
          </p>
        }
      />
    </section>
  );
}

/* -- Signal Trends ---------------------------------------------------------- */
function TrendsView({ scenario, selected, onSelect, current }: ViewProps) {
  return (
    <section className="view">
      <ViewHeader
        title="Signal Trends"
        lede="A chosen subsystem's fault probability across the scenario timeline."
      />
      <SignalTrends
        scenario={scenario}
        selected={selected}
        onSelect={onSelect}
        currentStep={current}
      />
      <Explain
        what={
          <p>
            The selected subsystem&rsquo;s fault probability plotted across every
            window of the scenario. The dashed &ldquo;now&rdquo; line marks the
            current time step so trends line up with the rest of the dashboard.
          </p>
        }
        how={
          <p>
            Each point is the per-window output of that subsystem&rsquo;s fault
            detector — the same probability that drives the health bands on the
            Overview. Use the buttons to switch which subsystem is charted.
          </p>
        }
      />
    </section>
  );
}

/* -- Recommendations -------------------------------------------------------- */
function RecommendationsView({ result }: ViewProps) {
  return (
    <section className="view">
      <ViewHeader
        title="Recommendations"
        lede="The concrete verification step for the likely origin — never an autonomous action."
      />
      <Recommendations rec={result.recommendation} />
      <Explain
        what={
          <p>
            A concrete verification/inspection step for the likely origin
            subsystem, with the reason behind it, the supporting evidence, and any
            signals that are missing. It always tells a technician what to{" "}
            <em>check</em>, never what to replace autonomously.
          </p>
        }
        how={
          <p>
            The step is template-driven per origin subsystem and is{" "}
            <strong>always a verification action, never an autonomous one</strong>{" "}
            — e.g. &ldquo;inspect coolant flow sensor and verify coolant
            level,&rdquo; never &ldquo;replace pump.&rdquo; The
            verification-guidance-only disclaimer stays visible at all times.
          </p>
        }
      />
    </section>
  );
}

/* -- Timeline --------------------------------------------------------------- */
function TimelineView({ scenario, current, onSeek }: ViewProps) {
  return (
    <section className="view">
      <ViewHeader
        title="Timeline"
        lede="Step-through log of every evaluated signal window."
      />
      <Timeline scenario={scenario} current={current} onSeek={onSeek} />
      <Explain
        what={
          <p>
            A step-through log of every window in the scenario, each with its
            worst-subsystem health and its trust and impact scores. Click any row
            to jump the whole dashboard to that window.
          </p>
        }
        how={
          <p>
            Each row is one evaluated signal window. The active row is driven by
            the shared top-bar scrubber, so selecting a row here is the same as
            scrubbing the time step everywhere else.
          </p>
        }
      />
    </section>
  );
}

/* -- How It Works (explainer only, no data panel) --------------------------- */
function HowItWorksView() {
  return (
    <section className="view">
      <ViewHeader
        title="How It Works"
        lede="The FPI pipeline, and an honest boundary between what is real and what is synthetic."
      />

      <div className="howto">
        <h2 className="howto__h">The 4-stage pipeline</h2>
        <ol className="howto__pipeline">
          <li>
            <span className="howto__stage">Detect</span>
            <p>
              A per-subsystem detector turns each subsystem&rsquo;s sensor window
              into a fault probability. Thresholds band it into OK / Watch /
              Flagged.
            </p>
          </li>
          <li>
            <span className="howto__stage">Propagation</span>
            <p>
              A directed dependency graph is walked to find the most likely fault
              path and to identify the true root cause, even when a downstream node
              shows the loudest symptom. ETAs come from per-edge lag.
            </p>
          </li>
          <li>
            <span className="howto__stage">Trust</span>
            <p>
              A transparent, rule-based blend of seven factors scores how much to
              rely on the prediction (0–100).
            </p>
          </li>
          <li>
            <span className="howto__stage">Impact</span>
            <p>
              A separate consequence-only score from six factors rates how much the
              prediction matters operationally (0–100). Trust and Impact are kept
              independent.
            </p>
          </li>
          <li>
            <span className="howto__stage">Evidence-based recommendation</span>
            <p>
              A template produces a concrete verification step for the origin
              subsystem — always something to inspect or confirm, never an
              autonomous action.
            </p>
          </li>
        </ol>
      </div>

      <div className="howto howto--boundary">
        <h2 className="howto__h">The data-honesty boundary</h2>
        <p className="howto__lead">
          <strong>Real = detection. Synthetic = propagation.</strong> These are not
          conflated.
        </p>
        <table className="howto__table">
          <thead>
            <tr>
              <th>Capability</th>
              <th>Data</th>
              <th>Validated on real data?</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Per-subsystem <strong>detection</strong></td>
              <td>Real public benchmarks</td>
              <td>
                Yes — NASA battery ~98% and CWRU bearing ~100% on held-out splits
              </td>
            </tr>
            <tr>
              <td>Cross-subsystem <strong>propagation</strong> cascade</td>
              <td>Synthetic (physics-informed)</td>
              <td>No — no public real-propagation dataset exists</td>
            </tr>
          </tbody>
        </table>
        <p className="howto__note">
          The ~98% and ~100% figures are held-out benchmark accuracies for
          detection only. No number in this dashboard is a field/real-world result,
          and the propagation cascade is never presented as validated against real
          propagation. See <code>docs/DATASETS.md</code> for the full boundary.
        </p>
      </div>
    </section>
  );
}

/** Routes the active view id to its component. */
export function ViewRouter(props: ViewProps) {
  switch (props.view) {
    case "overview":
      return <OverviewView {...props} />;
    case "propagation":
      return <PropagationView {...props} />;
    case "trust":
      return <TrustView {...props} />;
    case "graph":
      return <GraphView {...props} />;
    case "trends":
      return <TrendsView {...props} />;
    case "recommendations":
      return <RecommendationsView {...props} />;
    case "timeline":
      return <TimelineView {...props} />;
    case "how":
      return <HowItWorksView />;
    default:
      return <OverviewView {...props} />;
  }
}
