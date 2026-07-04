# FPI — Technician Dashboard

React + Vite + TypeScript single-page app for the **Failure Propagation Intelligence**
(FPI) MVP. It renders the §14 whitepaper panel grid for an EV thermal → drivetrain
failure-propagation scenario and talks to the FastAPI backend over HTTP.

> **Honesty guardrails (from the whitepaper):** all bundled data is *synthetic* and
> validates the architecture and workflow only — never accuracy. The system recommends
> **verification steps**, never autonomous maintenance actions. Trust and Impact are two
> distinct scores and are **never merged into a single number**.

## Panels (§14)

1. **Vehicle Health Overview** — 4-subsystem status grid (ok / watch / flagged).
2. **Active Propagation Chain** — best path as a left-to-right chain with per-hop
   probability + ETA; origin and next node highlighted; terminal "power derate" outcome.
3. **Trust & Impact** — the two scores side by side (never blended), each with its factor
   breakdown. Impact drives alert sort order.
4. **Subsystem Dependency Graph** — expandable nodes + weighted edges from `/api/graph`
   (domain-reasoning-based; flagged for SME review, §18).
5. **Signal Trends** — Recharts line chart of a chosen subsystem's fault probability across
   the scenario timeline.
6. **Recommended Verification** — verification step, reason, evidence, missing signals,
   plus the non-autonomy disclaimer.
7. **Maintenance Timeline** — scrubbable log with play / prev / next that advances the
   "current" window driving every panel above.

## Run (development)

```bash
npm install
npm run dev
```

Open http://localhost:5173.

### Configuring the backend

The API base URL comes from the `VITE_API_BASE` environment variable and defaults to
`http://localhost:8000`.

```bash
# PowerShell
$env:VITE_API_BASE = "http://localhost:8000"; npm run dev

# bash
VITE_API_BASE=http://localhost:8000 npm run dev
```

Or create a `.env` file:

```
VITE_API_BASE=http://localhost:8000
```

### Offline / standalone demo

If the backend is unreachable, the dashboard **automatically falls back to a bundled
sample thermal-cascade scenario** (`src/sampleScenario.ts`) so it renders fully with no
server running. The header shows `Sample data (offline)` vs `Live API` accordingly.

## Endpoints consumed

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | connection probe |
| GET | `/api/graph` | dependency graph (nodes + weighted edges) |
| GET | `/api/demo/scenario` | full `PipelineResult` timeline |
| POST | `/api/evaluate` | evaluate a single window (client helper provided) |

The response shapes are typed in `src/types.ts` (mirrors `fpi/schemas.py`).

## Build

```bash
npm run build      # tsc -b && vite build  → dist/
npm run preview    # serve the production build locally
```

## Docker

Multi-stage build (Node → nginx) serving on container port **80**:

```bash
docker build -t fpi-dashboard .
docker run -p 8080:80 fpi-dashboard          # http://localhost:8080

# bake a backend URL at build time (optional)
docker build --build-arg VITE_API_BASE=http://api:8000 -t fpi-dashboard .
```

Referenced by the repo-root `docker-compose.yml` as `dashboard/Dockerfile`.

## Project layout

```
dashboard/
├── src/
│   ├── api.ts              # typed API client + graceful sample fallback
│   ├── types.ts            # shared data contract (mirrors fpi/schemas.py)
│   ├── sampleScenario.ts   # bundled 12-window thermal_cascade demo data
│   ├── format.ts           # small display helpers
│   ├── App.tsx / App.css   # layout + §14 panel grid
│   └── components/         # one file per panel
├── Dockerfile              # multi-stage node → nginx (port 80)
├── nginx.conf              # SPA fallback + asset caching
└── vite.config.ts
```
