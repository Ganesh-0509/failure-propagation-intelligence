# Real Public Datasets for FPI

This document describes the **real, publicly available** benchmark datasets used
to validate FPI's **per-subsystem fault detection**, how to fetch and run them,
the feature extraction per subsystem, and — most importantly — the honesty
boundary between what is validated with real data and what remains synthetic.

## The honesty boundary (read this first)

| Capability | Data | Validated against real data? |
|---|---|---|
| **Per-subsystem DETECTION** (is a component healthy or degraded/faulty?) | **REAL** public benchmarks (NASA battery, CWRU bearing) | **Yes** — measured on a held-out split of real downloaded data |
| **Cross-subsystem PROPAGATION** (cooling → battery → motor → inverter cascade, ETA, causal ordering) | **SYNTHETIC** (`fpi/synthetic.py`) | **No — and it cannot be here** |

There is **no public dataset of real cross-subsystem propagation** — i.e. no
corpus of real vehicles with ground-truth causal fault *cascades* across
subsystems and their timing. Such data does not exist publicly. Therefore FPI's
propagation reasoning is exercised only on physics-informed **synthetic**
scenarios and is **never** presented as validated against real-world propagation.

**Real = detection. Synthetic = propagation.** Do not conflate them.

Nothing in this pipeline fabricates data or metrics. If a download fails, the
loaders raise an explicit error with a fetch hint and produce no numbers.

---

## Datasets

### 1. NASA PCoE Li-ion battery aging → BATTERY detector

- **File used:** `B0005.mat` (~15.9 MB) — a single 18650 Li-ion cell cycled
  (charge / discharge / impedance) at room temperature until end-of-life.
- **Source (canonical):** NASA Ames Prognostics Center of Excellence (PCoE)
  Prognostics Data Repository —
  <https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/>
- **Mirror actually fetched (GitHub raw):**
  `https://raw.githubusercontent.com/Hankxu-316/Visual-analysis-system-for-lithium-battery-health-status/HEAD/data/B0005.mat`
  (fallback: `.../TeslaCui/Battery_SOC_SOH_Simulation_v1_20260414/HEAD/B0005.mat`)
- **License:** U.S. Government work / **public domain** (NASA PCoE). Free to use;
  please cite the NASA Ames Prognostics Center of Excellence.

**Feature extraction (`load_battery_dataset`)** — one sample per *discharge*
cycle (~168 cycles in B0005):

| Feature | Meaning |
|---|---|
| `voltage_mean`, `voltage_min` | mean / minimum measured terminal voltage over the discharge |
| `voltage_load_mean` | mean load voltage |
| `temp_mean`, `temp_max` | mean / peak cell temperature |
| `current_mean` | mean measured current |
| `discharge_time_s` | total discharge duration (shortens as the cell ages) |

**Label:** `1` (degraded) if that cycle's discharge **capacity** is below
`degraded_fraction` (default **0.8**) of the cell's **initial** discharge
capacity, else `0` (healthy).

> **Label-leakage guard:** capacity *defines* the label, so it is **deliberately
> excluded** from the feature vector. The detector must recognise degradation
> from the discharge voltage/temperature/current/duration curve alone — a
> genuine, non-trivial detection task rather than a tautology.

### 2. CWRU bearing vibration (12 kHz drive-end) → MOTOR detector

- **Files used** (~3–4 MB each): `1797_Normal.npz` (healthy baseline),
  `1797_IR_7_DE12.npz` (inner-race fault), `1797_OR@12_7_DE12.npz` (outer-race
  fault) — 0.007in seeded faults, motor at 1797 RPM / 0 hp load, 12 kHz
  drive-end accelerometer.
- **Source (canonical):** Case Western Reserve University Bearing Data Center —
  <https://engineering.case.edu/bearingdatacenter>
- **Mirror actually fetched (numpy-native, GitHub raw):**
  `srigas/CWRU_Bearing_NumPy` —
  `https://raw.githubusercontent.com/srigas/CWRU_Bearing_NumPy/main/Data/1797%20RPM/...`
  (chosen over `.mat` to avoid fragile MATLAB-struct handling; each `.npz`
  contains the raw `DE`/`FE` vibration channels).
- **License:** Free for **academic / research use**, courtesy of the CWRU Bearing
  Data Center. Please cite the Case Western Reserve University Bearing Data Center.

**Feature extraction (`load_bearing_dataset`)** — the drive-end (`DE`) signal is
windowed into non-overlapping **2048-sample** segments; each segment is one
sample with:

| Feature | Meaning |
|---|---|
| `rms`, `std`, `peak` | amplitude statistics |
| `kurtosis` | impulsiveness (rises with bearing defects) |
| `crest_factor` | `peak / rms` |
| `band_energy_1..4` | fractional FFT energy in 4 contiguous spectral bands |

**Label:** `0` for the normal baseline, `1` for any seeded fault (inner or outer
race).

---

## How to run

```bash
# 1) Download + cache the real data into data/real/ (skips files already present)
python scripts/fetch_datasets.py

# 2) Train per-subsystem detectors on a TRAIN split, evaluate on a held-out TEST
#    split, and print REAL measured metrics
python scripts/validate_real.py
```

Programmatic access:

```python
from fpi.datasets import load_battery_dataset, load_bearing_dataset
X, y, feature_names = load_battery_dataset()   # NASA B0005
X, y, feature_names = load_bearing_dataset()   # CWRU 12kHz DE
```

The stub in `fpi.synthetic.load_public_dataset("nasa_battery" | "cwru_bearing")`
now delegates to these loaders.

Loaders **never auto-download**. If the data is not cached they raise
`FileNotFoundError` with the exact fetch command. Tests
(`tests/test_datasets.py`) **skip** cleanly when the data is absent and never
download.

---

## Measured results (example run)

Measured on held-out (30%) test splits of the real downloaded data, seed 42.
These are **real** measurements of **per-subsystem detection** only; re-run
`scripts/validate_real.py` to reproduce.

| Detector | Dataset | Held-out test accuracy | Notes |
|---|---|---|---|
| BATTERY | NASA B0005 (168 discharge cycles) | ~0.98 | LogisticRegression; capacity excluded from features |
| MOTOR | CWRU 12 kHz DE (237 vibration windows) | ~1.00 | RandomForest; normal vs seeded fault is a well-separated benchmark |

> The CWRU normal-vs-fault separation is famously clean with classical features,
> so ~1.0 on this held-out split is expected for the benchmark and is **not** a
> claim about FPI's real-world propagation performance.

---

## Data handling / git

Real benchmark files are large and are **never committed**. `data/real/` is
gitignored (`data/real/.gitignore` = `*` except itself); only the `.gitignore`
placeholder is tracked. Verify with `git check-ignore data/real/B0005.mat`.
