"""FastAPI service exposing the FPI Reasoning Engine to the technician dashboard.

Endpoints (see PROJECT_PLAN.md and the dashboard API contract):
    GET  /health              -> {"status": "ok"}
    GET  /api/graph           -> dependency graph nodes + edges
    GET  /api/demo/scenario   -> a full thermal_cascade timeline of PipelineResults
    POST /api/evaluate        -> a single PipelineResult (optional scenario spec)

The heavy objects (trained detector, generated demo scenario) are built once and
cached at process start so per-request latency stays edge-realistic.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from fpi.graph import build_dependency_graph
from fpi.pipeline import FPIPipeline
from fpi.schemas import (
    FaultDetection,
    ImpactScore,
    PipelineResult,
    PropagationPath,
    Recommendation,
    Subsystem,
    TrustScore,
)
from fpi.synthetic import generate_scenario

app = FastAPI(
    title="Failure Propagation Intelligence API",
    version="0.1.0",
    description="Edge-AI decision support for EV subsystem failure propagation "
    "(research/hackathon MVP — synthetic data validates workflow only, never accuracy).",
)

# Dashboard is served from a different origin during local dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Cached singletons
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def get_pipeline() -> FPIPipeline:
    return FPIPipeline()


@lru_cache(maxsize=1)
def get_demo_timeline() -> tuple[list[PipelineResult], dict]:
    scenario = generate_scenario(kind="thermal_cascade", n_windows=40, seed=7, inject_at=8)
    results = get_pipeline().run_scenario(scenario)
    meta = {"kind": "thermal_cascade", "n_windows": len(scenario), "inject_at": 8}
    return results, meta


# --------------------------------------------------------------------------- #
# Serialization — explicit, to match the dashboard contract and keep output lean
# --------------------------------------------------------------------------- #
def _detection_json(d: FaultDetection) -> dict:
    return {
        "subsystem": d.subsystem.value,
        "fault_probability": round(d.fault_probability, 4),
        "model_confidence": round(d.model_confidence, 4),
        "temporal_stability": round(d.temporal_stability, 4),
    }


def _path_json(p: PropagationPath | None) -> Optional[dict]:
    if p is None:
        return None
    return {
        "origin": p.origin.value,
        "steps": [
            {
                "subsystem": s.subsystem.value,
                "probability": round(s.probability, 4),
                "eta_cycles": round(s.eta_cycles, 3),
            }
            for s in p.steps
        ],
        "path_probability": round(p.path_probability, 4),
        "next_node": p.next_node.value if p.next_node else None,
        "eta_next_cycles": round(p.eta_next_cycles, 3) if p.eta_next_cycles is not None else None,
    }


def _trust_json(t: TrustScore | None) -> Optional[dict]:
    if t is None:
        return None
    return {
        "value": round(t.value, 2),
        "factors": {k: round(v, 4) for k, v in t.factors.items()},
        "rationale": t.rationale,
    }


def _impact_json(i: ImpactScore | None) -> Optional[dict]:
    if i is None:
        return None
    return {
        "value": round(i.value, 2),
        "factors": {k: round(v, 4) for k, v in i.factors.items()},
        "safety_relevant": i.safety_relevant,
    }


def _rec_json(r: Recommendation | None) -> Optional[dict]:
    if r is None:
        return None
    return {
        "subsystem": r.subsystem.value,
        "reason": r.reason,
        "evidence": list(r.evidence),
        "verification_step": r.verification_step,
        "missing_signals": list(r.missing_signals),
        "trust": _trust_json(r.trust),
        "impact": _impact_json(r.impact),
    }


def result_json(r: PipelineResult) -> dict:
    return {
        "detections": [_detection_json(d) for d in r.detections],
        "best_path": _path_json(r.best_path),
        "all_paths": [_path_json(p) for p in r.all_paths],
        "trust": _trust_json(r.trust),
        "impact": _impact_json(r.impact),
        "recommendation": _rec_json(r.recommendation),
        "subsystem_health": {s.value: h.value for s, h in r.subsystem_health.items()},
    }


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/graph")
def graph() -> dict:
    g = build_dependency_graph()
    nodes = [
        {"id": n.value, "safety_relevant": bool(g.nodes[n].get("safety_relevant", False))}
        for n in g.nodes
    ]
    edges = [
        {
            "source": u.value,
            "target": v.value,
            "weight": g.edges[u, v]["weight"],
            "lag_cycles": g.edges[u, v]["lag_cycles"],
        }
        for u, v in g.edges
    ]
    return {"nodes": nodes, "edges": edges}


@app.get("/api/demo/scenario")
def demo_scenario() -> dict:
    results, meta = get_demo_timeline()
    return {"steps": [result_json(r) for r in results], "meta": meta}


class EvaluateRequest(BaseModel):
    kind: str = "thermal_cascade"
    inject_at: int = 8
    n_windows: int = 40
    step: int = -1  # which timeline index to return; -1 = last


@lru_cache(maxsize=16)
def _run_params(kind: str, inject_at: int, n_windows: int) -> list[PipelineResult]:
    """Generate and evaluate a scenario, memoized by its parameters.

    Without this, every /api/evaluate call regenerated the full N-window scenario
    and re-ran the whole timeline just to return one step. Caching keeps per-request
    latency edge-realistic for repeated calls with the same parameters.
    """
    scenario = generate_scenario(kind=kind, n_windows=n_windows, seed=7, inject_at=inject_at)
    return get_pipeline().run_scenario(scenario)


@app.post("/api/evaluate")
def evaluate(req: EvaluateRequest) -> dict:
    results = _run_params(req.kind, req.inject_at, req.n_windows)
    idx = req.step if -len(results) <= req.step < len(results) else -1
    return result_json(results[idx])
