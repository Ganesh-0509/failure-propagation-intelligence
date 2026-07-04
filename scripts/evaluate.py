"""Evaluation harness for the FPI prototype (whitepaper §15).

IMPORTANT: every number this script prints is a PROTOTYPE-STAGE measurement on
SYNTHETIC data with a KNOWN injected fault origin. These validate the architecture
and workflow ONLY. They are NOT field results and must never be quoted as evidence
of real-world predictive accuracy (§12, §15, §18).

Metrics implemented here (the synthetic-measurable subset of §15):
  - origin identification accuracy : fraction of runs where the predicted origin
    matches the injected origin (cooling).
  - propagation lead time          : how many operating cycles earlier FPI names the
    chain vs. waiting for the terminal node (inverter) to cross its own threshold.
  - false alarm rate               : fraction of nominal (no-fault) runs that raise a
    flagged propagation chain.

Metrics NOT computed here (require held-out public data or reliability diagrams):
  fault-detection accuracy, trust-calibration error, decision-quality rubric,
  edge latency / memory footprint. See §15 for how those would be measured.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fpi.pipeline import FPIPipeline
from fpi.schemas import HealthState, Subsystem
from fpi.synthetic import generate_nominal, generate_scenario

INJECTED_ORIGIN = Subsystem.COOLING
TERMINAL = Subsystem.INVERTER
N_SEEDS = 20


def _first_chain_step(results) -> int | None:
    for i, r in enumerate(results):
        if r.best_path is not None:
            return i
    return None


def _first_terminal_flagged(results) -> int | None:
    for i, r in enumerate(results):
        if r.subsystem_health.get(TERMINAL) == HealthState.FLAGGED:
            return i
    return None


def main() -> None:
    pipeline = FPIPipeline()

    # --- origin accuracy + propagation lead time over many seeded fault runs ---
    correct_origin = 0
    lead_times: list[int] = []
    for seed in range(N_SEEDS):
        results = pipeline.run_scenario(
            generate_scenario(kind="thermal_cascade", n_windows=40, seed=seed, inject_at=8)
        )
        chain_step = _first_chain_step(results)
        if chain_step is not None and results[chain_step].best_path.origin == INJECTED_ORIGIN:
            correct_origin += 1
        term_step = _first_terminal_flagged(results)
        if chain_step is not None and term_step is not None:
            lead_times.append(term_step - chain_step)

    # --- false alarm rate over nominal runs ---
    false_alarms = 0
    for seed in range(N_SEEDS):
        results = pipeline.run_scenario(generate_nominal(n_windows=40, seed=1000 + seed))
        if any(
            h == HealthState.FLAGGED
            for r in results
            for h in r.subsystem_health.values()
        ):
            false_alarms += 1

    avg_lead = sum(lead_times) / len(lead_times) if lead_times else float("nan")

    print("=" * 68)
    print("FPI PROTOTYPE EVALUATION — SYNTHETIC DATA ONLY (NOT field results)")
    print("=" * 68)
    print(f"Runs per metric                 : {N_SEEDS}")
    print(f"Origin identification accuracy  : {correct_origin}/{N_SEEDS} "
          f"({100*correct_origin/N_SEEDS:.0f}%)  [target metric §15]")
    print(f"Propagation lead time (avg)     : {avg_lead:.1f} cycles earlier than "
          f"waiting for the {TERMINAL.value} threshold")
    print(f"False alarm rate (nominal runs) : {false_alarms}/{N_SEEDS} "
          f"({100*false_alarms/N_SEEDS:.0f}%)")
    print("-" * 68)
    print("Reminder: synthetic validation of architecture/workflow only (§12, §15, §18).")
    print("Not a measured field result. Origin is known-injected; do not cite as accuracy.")


if __name__ == "__main__":
    main()
