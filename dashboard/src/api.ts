// ---------------------------------------------------------------------------
// Typed FPI API client.
//
// Talks to the FastAPI backend over HTTP. Base URL comes from
// import.meta.env.VITE_API_BASE (default "http://localhost:8000").
//
// Every call degrades gracefully: if the backend is unreachable (fetch throws
// or returns a non-2xx), we fall back to the bundled sample scenario so the
// dashboard renders standalone for a demo with no server running.
// ---------------------------------------------------------------------------

import type {
  DependencyGraph,
  HealthResponse,
  PipelineResult,
  Scenario,
} from "./types";
import { SAMPLE_SCENARIO, SAMPLE_GRAPH } from "./sampleScenario";

export const API_BASE: string =
  import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

/** How a piece of data was sourced — surfaced in the UI as a status badge. */
export type DataSource = "live" | "sample";

export interface Fetched<T> {
  data: T;
  source: DataSource;
  /** Present when we fell back to sample data. */
  error?: string;
}

const TIMEOUT_MS = 4000;

async function getJSON<T>(path: string): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      signal: controller.signal,
      headers: { Accept: "application/json" },
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} for ${path}`);
    }
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

async function postJSON<TReq, TRes>(path: string, body: TReq): Promise<TRes> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} for ${path}`);
    }
    return (await res.json()) as TRes;
  } finally {
    clearTimeout(timer);
  }
}

/** GET /health — lightweight probe used to show connection status. */
export async function checkHealth(): Promise<boolean> {
  try {
    const r = await getJSON<HealthResponse>("/health");
    return r.status === "ok";
  } catch {
    return false;
  }
}

/** GET /api/graph — subsystem dependency graph, sample fallback. */
export async function fetchGraph(): Promise<Fetched<DependencyGraph>> {
  try {
    const data = await getJSON<DependencyGraph>("/api/graph");
    return { data, source: "live" };
  } catch (e) {
    return {
      data: SAMPLE_GRAPH,
      source: "sample",
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

/** GET /api/demo/scenario — full timeline, sample fallback. */
export async function fetchScenario(): Promise<Fetched<Scenario>> {
  try {
    const data = await getJSON<Scenario>("/api/demo/scenario");
    if (!data?.steps?.length) throw new Error("empty scenario");
    return { data, source: "live" };
  } catch (e) {
    return {
      data: SAMPLE_SCENARIO,
      source: "sample",
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

/**
 * POST /api/evaluate — evaluate a single window.
 * Falls back to the last sample step so callers always get a result.
 */
export async function evaluate(
  window: unknown,
): Promise<Fetched<PipelineResult>> {
  try {
    const data = await postJSON<unknown, PipelineResult>(
      "/api/evaluate",
      window,
    );
    return { data, source: "live" };
  } catch (e) {
    const steps = SAMPLE_SCENARIO.steps;
    return {
      data: steps[steps.length - 1],
      source: "sample",
      error: e instanceof Error ? e.message : String(e),
    };
  }
}
