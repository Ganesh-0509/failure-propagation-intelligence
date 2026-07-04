"""Download + cache the REAL public benchmark datasets used by FPI.

Fetches a SMALL subset (a handful of files, not the whole repositories) of two
genuine condition-monitoring benchmarks into ``data/real/`` and prints what was
fetched (sizes + sources + licenses):

  * NASA PCoE Li-ion battery aging (B0005.mat)  -> BATTERY detector validation
  * CWRU 12 kHz drive-end bearing vibration      -> MOTOR   detector validation

Honesty note: these validate PER-SUBSYSTEM DETECTION only. FPI's cross-subsystem
PROPAGATION cascade stays synthetic -- no real propagation-labelled dataset
exists. See docs/DATASETS.md.

Usage:
    python scripts/fetch_datasets.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a bare script (python scripts/fetch_datasets.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fpi.datasets import DATASET_SOURCES, DEFAULT_CACHE_DIR, fetch_dataset


def main() -> int:
    print("=" * 74)
    print("FPI real-dataset fetch  ->  ", DEFAULT_CACHE_DIR)
    print("REAL public benchmarks for PER-SUBSYSTEM DETECTION validation only.")
    print("Propagation reasoning remains synthetic (no real propagation dataset).")
    print("=" * 74)

    failures: list[str] = []
    fetched: list[Path] = []
    for name, meta in DATASET_SOURCES.items():
        print(f"\n[{name}] {meta['description']}")
        print(f"  license: {meta['license']}")
        try:
            paths = fetch_dataset(name, verbose=True)
            fetched.extend(paths)
        except Exception as exc:  # noqa: BLE001 - report honestly, keep going
            print(f"  !! FAILED: {exc}")
            failures.append(name)

    print("\n" + "=" * 74)
    print("Fetched files:")
    total = 0
    for p in fetched:
        size = p.stat().st_size if p.exists() else 0
        total += size
        print(f"  {p.name:28s} {size:>12,} bytes   ({p})")
    print(f"  {'TOTAL':28s} {total:>12,} bytes")

    if failures:
        print("\nDatasets that FAILED to download (no data fabricated):")
        for name in failures:
            print(f"  - {name}: see DATASET_SOURCES for mirrors/licenses")
        print("Retry later or add a working mirror to fpi/datasets.DATASET_SOURCES.")
        return 1

    print("\nAll datasets cached. Run:  python scripts/validate_real.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
