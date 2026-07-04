"""REAL public-benchmark validation of FPI's PER-SUBSYSTEM DETECTION.

Trains a small scikit-learn classifier per subsystem on a TRAIN split of a REAL
downloaded benchmark, evaluates on a held-out TEST split, and prints REAL,
measured metrics:

  * BATTERY detector  <- NASA PCoE B0005 Li-ion battery aging (healthy vs degraded)
  * MOTOR   detector  <- CWRU 12 kHz drive-end bearing (normal vs seeded fault)

=============================================================================
REAL public-benchmark validation of per-subsystem DETECTION. Propagation
reasoning remains SYNTHETIC (no real propagation-labelled dataset exists).
Every metric below is measured on a held-out split of REAL downloaded data.
=============================================================================

Usage:
    python scripts/fetch_datasets.py     # once, to download the data
    python scripts/validate_real.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from fpi.datasets import load_battery_dataset, load_bearing_dataset

_SEED = 42


def _evaluate(name: str, X: np.ndarray, y: np.ndarray, feature_names, clf, target_names):
    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=0.30, random_state=_SEED, stratify=y
    )
    clf.fit(Xtr, ytr)
    pred = clf.predict(Xte)
    acc = accuracy_score(yte, pred)

    print(f"\n### {name}")
    print(f"  samples: {len(y)}  (train {len(ytr)} / test {len(yte)})")
    print(f"  class balance (full): {dict(zip(*np.unique(y, return_counts=True)))}")
    print(f"  features ({len(feature_names)}): {', '.join(feature_names)}")
    print(f"  HELD-OUT TEST ACCURACY: {acc:.4f}")
    print("  classification report (held-out test split):")
    report = classification_report(
        yte, pred, target_names=target_names, digits=3, zero_division=0
    )
    for line in report.strip().splitlines():
        print("    " + line)
    return acc


def main() -> int:
    header = (
        "=" * 74
        + "\nREAL public-benchmark validation of per-subsystem DETECTION.\n"
        + "Propagation reasoning remains SYNTHETIC (no real propagation dataset).\n"
        + "Metrics below are measured on held-out splits of REAL downloaded data.\n"
        + "=" * 74
    )
    print(header)

    try:
        Xb, yb, fb = load_battery_dataset()
        Xm, ym, fm = load_bearing_dataset()
    except FileNotFoundError as exc:
        print("\nERROR: real data not available.\n")
        print(exc)
        return 1

    # BATTERY: capacity is deliberately EXCLUDED from features (it defines the
    # label), so this is a genuine detection task on discharge-curve signals.
    battery_acc = _evaluate(
        "BATTERY subsystem detector  (NASA B0005 Li-ion aging)",
        Xb,
        yb,
        fb,
        make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
        target_names=["healthy", "degraded"],
    )

    # MOTOR (bearing): fault vs normal from vibration windows.
    motor_acc = _evaluate(
        "MOTOR subsystem detector    (CWRU 12kHz drive-end bearing)",
        Xm,
        ym,
        fm,
        make_pipeline(
            StandardScaler(),
            RandomForestClassifier(n_estimators=200, random_state=_SEED),
        ),
        target_names=["normal", "faulty"],
    )

    footer = (
        "\n" + "=" * 74 + "\n"
        "SUMMARY (REAL, measured on held-out real data):\n"
        f"  BATTERY detector held-out accuracy: {battery_acc:.4f}\n"
        f"  MOTOR   detector held-out accuracy: {motor_acc:.4f}\n"
        "\nScope: this validates PER-SUBSYSTEM DETECTION only. FPI's cross-\n"
        "subsystem PROPAGATION cascade remains SYNTHETIC -- no public dataset of\n"
        "real cross-subsystem propagation exists, so it is not (and cannot here\n"
        "be) validated against real data.\n" + "=" * 74
    )
    print(footer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
