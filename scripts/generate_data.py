"""CLI to generate a synthetic FPI scenario and write it to ``data/`` as JSON.

Usage:
    python scripts/generate_data.py --out data/scenario.json
    python scripts/generate_data.py --kind nominal --out data/nominal.json

This produces physics-informed synthetic telemetry ONLY (whitepaper §8, §12
Category 2) -- it validates workflow, never accuracy.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a plain script (``python scripts/generate_data.py``) by making
# the repository root importable.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fpi.synthetic import generate_scenario, save_scenario  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a synthetic FPI scenario (thermal cascade or nominal)."
    )
    parser.add_argument(
        "--out",
        default="data/scenario.json",
        help="Output JSON path (default: data/scenario.json).",
    )
    parser.add_argument(
        "--kind",
        default="thermal_cascade",
        choices=["thermal_cascade", "nominal"],
        help="Scenario type (default: thermal_cascade).",
    )
    parser.add_argument("--n-windows", type=int, default=40, help="Number of windows.")
    parser.add_argument("--seed", type=int, default=0, help="RNG seed (deterministic).")
    parser.add_argument(
        "--inject-at", type=int, default=8, help="Window index where the fault begins."
    )
    parser.add_argument("--noise", type=float, default=0.05, help="Sensor noise level (0..1).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scenario = generate_scenario(
        kind=args.kind,
        n_windows=args.n_windows,
        seed=args.seed,
        inject_at=args.inject_at,
        noise=args.noise,
    )
    meta = {
        "kind": args.kind,
        "n_windows": args.n_windows,
        "seed": args.seed,
        "inject_at": args.inject_at,
        "noise": args.noise,
        "note": "Synthetic (physics-informed). Validates workflow only, never accuracy.",
    }
    out_path = save_scenario(scenario, args.out, meta=meta)
    print(
        f"Wrote {args.kind} scenario: {args.n_windows} windows x 4 subsystems "
        f"-> {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
