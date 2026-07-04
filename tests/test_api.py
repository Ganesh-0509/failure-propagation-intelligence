"""API contract tests — verify the FastAPI service matches the dashboard contract."""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_graph_shape():
    r = client.get("/api/graph")
    assert r.status_code == 200
    data = r.json()
    assert len(data["nodes"]) == 4
    assert len(data["edges"]) == 6
    subs = {n["id"] for n in data["nodes"]}
    assert subs == {"cooling", "battery", "motor", "inverter"}
    for e in data["edges"]:
        assert "weight" in e and "lag_cycles" in e


def test_evaluate_contract():
    r = client.post("/api/evaluate", json={"step": 10})
    assert r.status_code == 200
    res = r.json()
    # required top-level keys of a PipelineResult
    for key in ("detections", "best_path", "all_paths", "trust", "impact",
                "recommendation", "subsystem_health"):
        assert key in res
    assert len(res["detections"]) == 4
    # trust (0..100) and probability (0..1) are distinct scales, never merged
    assert 0.0 <= res["trust"]["value"] <= 100.0
    assert 0.0 <= res["best_path"]["path_probability"] <= 1.0
    # recommendation is a verification step
    assert res["recommendation"]["verification_step"]


def test_demo_scenario_timeline():
    r = client.get("/api/demo/scenario")
    assert r.status_code == 200
    data = r.json()
    assert data["meta"]["kind"] == "thermal_cascade"
    assert len(data["steps"]) == data["meta"]["n_windows"]
