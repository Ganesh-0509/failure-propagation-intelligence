# Failure Propagation Intelligence (FPI) — Project-Ready Build Plan

**Source:** `Failure_Propagation_Intelligence_Whitepaper (1).docx`
**Stage:** Research / hackathon MVP (per §11A of the whitepaper)
**Team target:** 3–5 engineers · **This plan:** a buildable software skeleton + working demo

> Honesty guardrails carried from the whitepaper: no performance numbers are claimed as
> measured; synthetic data validates *architecture and workflow only*, never accuracy;
> the system recommends **verification steps**, never autonomous part replacement.

---

## 1. What we are actually building (MVP scope — §11A)

**Included:**
- Per-subsystem fault detection ("Edge AI Core") on public + synthetic data
- Failure Propagation Engine — directed dependency graph over the 4-subsystem
  thermal → battery → motor → inverter chain
- Trust Engine — inspectable, rule-based decision-confidence scoring (0–100)
- Impact Engine — weighted operational-priority scoring
- Evidence-Based Recommendation Engine — template-driven verification steps
- Technician dashboard (panel grid from §14)
- Synthetic scenario generator (physics-informed heuristics) + validation harness

**Explicitly NOT in MVP:** OEM fleet deployment, production digital twin, real CAN/OEM
telemetry, cloud fleet analytics, any autonomous maintenance action.

---

## 2. Architecture (one pipeline, four stages)

```
Vehicle Data (synthetic/public replay)
        │  time-aligned signal windows
        ▼
Edge AI Core ── per-subsystem fault probability
        ▼
1. Propagation Engine  → ranked propagation paths + time-to-next-node
        ▼
2. Trust Engine        → trust score (0–100) per prediction
        ▼
3. Impact Engine       → operational priority score
        ▼
4. Evidence Engine     → concrete verification recommendation
        ▼
Technician Dashboard (React)
```

Everything communicates through **one shared data contract** (`fpi/schemas.py`) so the
engines stay decoupled and independently testable.

---

## 3. Technology stack (illustrative MVP realization — §7, §13)

- **Core / inference:** Python 3.11, scikit-learn (small models), NetworkX (graph)
- **Edge inference format:** ONNX Runtime (export path; sklearn fallback for demo)
- **Service:** FastAPI + Uvicorn
- **Dashboard:** React + Vite + TypeScript, Recharts for signal trends
- **Packaging:** Docker (multi-stage), edge target Jetson Orin Nano / Raspberry Pi 5 (demo only)
- **Testing:** pytest (Python), Vitest/Playwright (dashboard)

_The stack is not the innovation and may be swapped._

---

## 4. Repository layout

```
C:\FPI\
├── fpi/                     # core Python package (the Reasoning Engine)
│   ├── schemas.py           # SHARED CONTRACT — dataclasses for every stage's I/O
│   ├── graph.py             # subsystem dependency graph (NetworkX) + weights/lags
│   ├── synthetic.py         # physics-informed synthetic scenario generator
│   ├── detection.py         # Edge AI Core: per-subsystem fault detection
│   ├── propagation.py       # Stage 1: Failure Propagation Engine
│   ├── trust.py             # Stage 2: Trust Engine
│   ├── impact.py            # Stage 3: Impact Engine
│   ├── recommendation.py    # Stage 4: Evidence-Based Decision Engine
│   └── pipeline.py          # orchestrates stages 1–4 on each signal window
├── api/main.py              # FastAPI service exposing the pipeline
├── dashboard/               # React dashboard (§14 panel grid)
├── tests/                   # pytest module + integration tests
├── data/                    # generated synthetic scenarios (gitignored)
├── scripts/                 # generate_data.py, run_demo.py, evaluate.py
├── Dockerfile               # multi-stage build for edge target
├── docker-compose.yml       # api + dashboard for local demo
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 5. Build phases (maps to whitepaper §13)

| Phase | Deliverable | Owner (agent) | Depends on |
|---|---|---|---|
| P0 Foundation | schemas, graph, repo scaffold, deps | (done inline) | — |
| P1 Signal Collection | synthetic generator + public-dataset loader stub | data agent | schemas, graph |
| P2 Fault Detection | per-subsystem classifiers (Edge AI Core) | ml agent | schemas, synthetic |
| P3 Propagation | graph propagation-path estimator + time-to-next-node | core agent | schemas, graph |
| P4 Trust | 7-factor inspectable trust scoring | core agent | schemas |
| P5 Impact | 6-factor weighted priority scoring | core agent | schemas, propagation |
| P6 Recommendation | template-driven verification recommender | core agent | schemas, impact |
| P7 Pipeline + API | orchestration + FastAPI endpoints | api agent | P2–P6 |
| P8 Dashboard | React panel grid (§14) wired to API | ui agent | API schema |
| P9 Tests + Docker + eval | pytest, multi-stage Docker, eval harness | qa agent | all |

Phases P1, P3, P4 can start in parallel once P0's contracts exist. P5→P6 chain after P3.

---

## 6. Data & validation strategy (§12, §15) — honest labeling

- **Synthetic** (physics-informed heuristics): validates architecture, propagation logic,
  trust behavior, dashboard — **never** cited as accuracy evidence.
- **Public benchmarks** (loader stubs, verify licenses before use): NASA battery
  degradation, CWRU bearing — validate per-subsystem detectors in isolation.
- **Evaluation metrics** (§15) are stated as **targets**, measured via held-out splits and
  synthetic scenario replay against known injected fault chains. No numbers claimed.

---

## 7. Definition of done (MVP demo)

1. `python scripts/generate_data.py` produces a synthetic thermal→drivetrain scenario.
2. `python scripts/run_demo.py` runs the full pipeline and prints a ranked, trust- and
   impact-scored propagation chain with a verification recommendation.
3. `uvicorn api.main:app` serves the pipeline; dashboard renders the §14 panels live.
4. `pytest` passes module + integration tests.
5. `docker compose up` brings up api + dashboard.
6. README documents scope, honesty guardrails, and how to reproduce.

---

## 8. Risks / open questions (carried from §18)

- Dependency-graph structure is domain-reasoning-based, not learned → mark as SME-review-needed.
- Trust factor weights are a design proposal → calibration is future work.
- Edge performance figures are targets until run on real hardware.
- Public dataset URLs/licenses must be re-verified before actual use.
