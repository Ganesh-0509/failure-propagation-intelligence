"""End-to-end FPI demo: generate a synthetic thermal->drivetrain scenario, run the
full Reasoning Engine, and print the technician-ready decision at the moment the
chain becomes clear.

    python scripts/run_demo.py

This is a research/hackathon demonstration on synthetic data. Nothing printed is a
measured field result; the recommendation is a verification step, not an action.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fpi.pipeline import FPIPipeline
from fpi.schemas import PipelineResult
from fpi.synthetic import generate_scenario


def _print_result(step: int, r: PipelineResult) -> None:
    print(f"\n=== Time step {step} ===")
    print("Subsystem health:")
    for sub, health in r.subsystem_health.items():
        det = next((d for d in r.detections if d.subsystem == sub), None)
        p = f"{det.fault_probability:5.2f}" if det else "  -  "
        print(f"  {sub.value:9s} {health.value:8s} (fault prob {p})")

    if r.best_path is None:
        print("No propagation chain above threshold (nominal).")
        return

    chain = " -> ".join([r.best_path.origin.value] + [s.subsystem.value for s in r.best_path.steps])
    print(f"\nMost likely ORIGIN : {r.best_path.origin.value}")
    print(f"Propagation chain  : {chain}")
    if r.best_path.next_node:
        print(f"Next node at risk  : {r.best_path.next_node.value} "
              f"(~{r.best_path.eta_next_cycles} cycles)")
    if r.trust:
        print(f"\nFault path prob    : {r.best_path.path_probability:.2f}  "
              f"(how likely)")
        print(f"Trust score        : {r.trust.value:.0f}/100  (how much to rely on it — "
              f"shown separately, never merged)")
        if r.trust.rationale:
            print(f"  trust note       : {r.trust.rationale}")
    if r.impact:
        print(f"Impact score       : {r.impact.value:.0f}/100  "
              f"(operational priority, safety_relevant={r.impact.safety_relevant})")
    if r.recommendation:
        print(f"\nRecommended verification (NOT an action):")
        print(f"  check first      : {r.recommendation.subsystem.value}")
        print(f"  step             : {r.recommendation.verification_step}")
        if r.recommendation.missing_signals:
            print(f"  missing signals  : {', '.join(r.recommendation.missing_signals)}")


def main() -> None:
    scenario = generate_scenario(kind="thermal_cascade", n_windows=40, seed=7, inject_at=8)
    pipeline = FPIPipeline()
    results = pipeline.run_scenario(scenario)

    # Find the first step where a real propagation chain emerges, and a late step.
    first_chain = next((i for i, r in enumerate(results) if r.best_path is not None), None)
    print("Failure Propagation Intelligence — synthetic thermal->drivetrain demo")
    print("=" * 70)
    if first_chain is not None:
        _print_result(first_chain, results[first_chain])
    _print_result(len(results) - 1, results[-1])
    print("\n" + "=" * 70)
    print("Reminder: synthetic data validates workflow only, never accuracy (whitepaper §12).")


if __name__ == "__main__":
    main()
