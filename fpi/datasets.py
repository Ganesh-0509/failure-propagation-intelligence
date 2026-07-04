"""REAL public-benchmark dataset loaders for per-subsystem detector validation.

This module downloads and parses genuine, publicly available condition-monitoring
benchmarks and turns them into ``(X, y, feature_names)`` numpy tuples that can
validate FPI's PER-SUBSYSTEM DETECTION in isolation:

  * :func:`load_battery_dataset` -- NASA PCoE 18650 Li-ion battery aging data
    (file ``B0005.mat``) -> validates the BATTERY subsystem detector.
  * :func:`load_bearing_dataset` -- CWRU rolling-element bearing vibration data
    (12 kHz drive-end; normal baseline + seeded inner/outer-race faults)
    -> validates the MOTOR subsystem detector.

================================ HONESTY BOUNDARY ============================
These datasets are REAL and let us report a REAL, measured detection accuracy on
a held-out split of REAL downloaded data. They validate DETECTION ONLY -- i.e.
"can we tell a healthy component from a degraded/faulty one from its own
sensors".

There is NO public dataset of real CROSS-SUBSYSTEM PROPAGATION (cooling ->
battery -> motor -> inverter cascades with ground-truth causal timing). No such
labelled corpus exists. Therefore the FPI PROPAGATION cascade remains SYNTHETIC
(see ``fpi/synthetic.py``) and is NEVER validated by this module. Real = per-
subsystem detection; Synthetic = propagation reasoning. Do not conflate them.

Nothing here fabricates data. If every mirror for a file fails, the loader
raises with an explicit online-fetch hint and returns no numbers.
=============================================================================

Feature extraction is intentionally simple and classical (no deep nets), so the
reported accuracy reflects the difficulty of the benchmark, not model tuning.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import numpy as np

# --------------------------------------------------------------------------- #
# Where real data is cached. NEVER committed (see data/real/.gitignore).
# --------------------------------------------------------------------------- #
DEFAULT_CACHE_DIR: Path = Path(__file__).resolve().parents[1] / "data" / "real"


# --------------------------------------------------------------------------- #
# Source registry: URLs + license notes. Each file lists >=1 mirror; the first
# that responds 200 is used. Keep the footprint SMALL (a handful of files).
# --------------------------------------------------------------------------- #
DATASET_SOURCES: dict[str, dict] = {
    "nasa_battery": {
        "description": (
            "NASA Prognostics Center of Excellence (PCoE) 18650 Li-ion battery "
            "aging dataset. Cell B0005 cycled (charge/discharge/impedance) at "
            "room temperature to failure."
        ),
        "license": (
            "U.S. Government work / public domain (NASA PCoE Prognostics Data "
            "Repository). Free to use; cite NASA Ames Prognostics Center of "
            "Excellence. Original: "
            "https://www.nasa.gov/intelligent-systems-division/discovery-and-"
            "systems-health/pcoe/pcoe-data-set-repository/"
        ),
        "files": {
            # ~15.9 MB canonical B0005.mat, mirrored on GitHub (raw).
            "B0005.mat": [
                "https://raw.githubusercontent.com/Hankxu-316/Visual-analysis-system-for-lithium-battery-health-status/HEAD/data/B0005.mat",
                "https://raw.githubusercontent.com/TeslaCui/Battery_SOC_SOH_Simulation_v1_20260414/HEAD/B0005.mat",
            ],
        },
    },
    "cwru_bearing": {
        "description": (
            "Case Western Reserve University (CWRU) Bearing Data Center. "
            "12 kHz drive-end accelerometer signals: healthy baseline plus "
            "seeded inner-race and outer-race faults (0.007in, motor at "
            "1797 RPM / 0 hp load)."
        ),
        "license": (
            "Free for academic/research use, courtesy of the Case Western "
            "Reserve University Bearing Data Center. Cite the CWRU Bearing Data "
            "Center. Original: "
            "https://engineering.case.edu/bearingdatacenter"
        ),
        "files": {
            # numpy-native mirror (srigas/CWRU_Bearing_NumPy); each .npz holds
            # {'DE','FE',(...)} raw vibration channels. ~3-4 MB each.
            "1797_Normal.npz": [
                "https://raw.githubusercontent.com/srigas/CWRU_Bearing_NumPy/main/Data/1797%20RPM/1797_Normal.npz",
            ],
            "1797_IR_7_DE12.npz": [
                "https://raw.githubusercontent.com/srigas/CWRU_Bearing_NumPy/main/Data/1797%20RPM/1797_IR_7_DE12.npz",
            ],
            "1797_OR@12_7_DE12.npz": [
                "https://raw.githubusercontent.com/srigas/CWRU_Bearing_NumPy/main/Data/1797%20RPM/1797_OR%4012_7_DE12.npz",
            ],
        },
    },
}

# Which cached files each loader requires (label semantics documented inline).
_BATTERY_FILE = "B0005.mat"
_BEARING_FILES: dict[str, int] = {
    "1797_Normal.npz": 0,        # healthy baseline
    "1797_IR_7_DE12.npz": 1,     # inner-race fault
    "1797_OR@12_7_DE12.npz": 1,  # outer-race fault
}


# --------------------------------------------------------------------------- #
# Download helper (curl via subprocess, with mirror probing + caching)
# --------------------------------------------------------------------------- #
def _curl_probe(url: str, timeout: int = 20) -> bool:
    """Return True if ``url`` responds with an HTTP 2xx via ``curl -sIL``."""
    try:
        out = subprocess.run(
            ["curl", "-sIL", "--max-time", str(timeout), url],
            capture_output=True,
            text=True,
            timeout=timeout + 10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    # Look at the LAST status line (after any redirects).
    statuses = [
        ln for ln in out.stdout.splitlines() if ln.upper().startswith("HTTP/")
    ]
    if not statuses:
        return False
    last = statuses[-1]
    return " 200" in last or " 2" in last.split("HTTP/")[-1][:5]


def download(
    urls: list[str],
    dest: Path,
    *,
    timeout: int = 300,
    force: bool = False,
    verbose: bool = True,
) -> Path:
    """Download the first working mirror in ``urls`` to ``dest`` (cached).

    Probes each candidate URL with ``curl -sIL`` and downloads the first that
    responds 200. Skips the download entirely if ``dest`` already exists and is
    non-empty (unless ``force``). Returns the local path.

    Raises:
        RuntimeError: if every mirror fails to probe or download.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0 and not force:
        if verbose:
            print(f"  [cached] {dest.name} ({dest.stat().st_size:,} bytes)")
        return dest

    last_err = None
    for url in urls:
        if not _curl_probe(url, timeout=min(timeout, 20)):
            if verbose:
                print(f"  [skip] mirror unreachable: {url}")
            continue
        if verbose:
            print(f"  [fetch] {dest.name} <- {url}")
        try:
            res = subprocess.run(
                ["curl", "-fSL", "--max-time", str(timeout), "-o", str(dest), url],
                capture_output=True,
                text=True,
                timeout=timeout + 30,
            )
        except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
            last_err = str(exc)
            continue
        if res.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
            if verbose:
                print(f"  [ok] {dest.name} ({dest.stat().st_size:,} bytes)")
            return dest
        last_err = res.stderr.strip() or f"curl exit {res.returncode}"

    raise RuntimeError(
        f"Failed to download {dest.name} from any mirror. Last error: {last_err}. "
        f"Mirrors tried: {urls}"
    )


def fetch_dataset(name: str, cache_dir: Optional[Path] = None, *, verbose: bool = True) -> list[Path]:
    """Download all files for one registered dataset into ``cache_dir``.

    ``name`` is a key of :data:`DATASET_SOURCES` (``"nasa_battery"`` or
    ``"cwru_bearing"``). Returns the list of local paths. Files already present
    are left untouched.
    """
    if name not in DATASET_SOURCES:
        raise KeyError(
            f"unknown dataset {name!r}; expected one of {list(DATASET_SOURCES)}"
        )
    cache_dir = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for fname, urls in DATASET_SOURCES[name]["files"].items():
        paths.append(download(urls, cache_dir / fname, verbose=verbose))
    return paths


# --------------------------------------------------------------------------- #
# Shared: missing-file guidance
# --------------------------------------------------------------------------- #
def _require(path: Path, dataset: str) -> Path:
    """Return ``path`` if present/non-empty, else raise with a fetch hint."""
    if path.exists() and path.stat().st_size > 0:
        return path
    raise FileNotFoundError(
        f"Real dataset file not found: {path}\n"
        f"The {dataset!r} benchmark has not been downloaded yet. Fetch it with:\n"
        f"    python scripts/fetch_datasets.py\n"
        f"(loaders never auto-download; see fpi.datasets.DATASET_SOURCES for URLs "
        f"and license terms)."
    )


# --------------------------------------------------------------------------- #
# NASA battery loader
# --------------------------------------------------------------------------- #
# NOTE ON LABEL LEAKAGE: the binary label is derived from per-cycle discharge
# CAPACITY (degraded == capacity below a fraction of the initial capacity).
# Capacity is therefore DELIBERATELY EXCLUDED from the feature vector so the
# classifier must detect degradation from the discharge voltage/temperature/
# current/duration signals alone -- a genuine, non-trivial detection task rather
# than a tautology.
_BATTERY_FEATURE_NAMES = [
    "voltage_mean",       # mean measured terminal voltage over the discharge
    "voltage_min",        # minimum measured voltage (end-of-discharge sag)
    "voltage_load_mean",  # mean load voltage
    "temp_mean",          # mean cell temperature
    "temp_max",           # peak cell temperature
    "current_mean",       # mean measured current
    "discharge_time_s",   # total discharge duration (shortens as cell ages)
]


def load_battery_dataset(
    cache_dir: Optional[Path] = None,
    *,
    degraded_fraction: float = 0.8,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Load the NASA B0005 battery benchmark as ``(X, y, feature_names)``.

    One sample per DISCHARGE cycle. Features summarise the discharge curve
    (voltage/temperature/current statistics + duration). The binary label is
    ``1`` (degraded) when that cycle's discharge capacity has fallen below
    ``degraded_fraction`` of the cell's INITIAL discharge capacity, else ``0``
    (healthy). Validates the BATTERY subsystem detector on REAL data.

    Args:
        cache_dir: directory holding ``B0005.mat`` (defaults to data/real/).
        degraded_fraction: capacity threshold as a fraction of initial capacity.

    Returns:
        ``X`` (n_cycles, 7) float array, ``y`` (n_cycles,) int array, and the
        list of feature names (capacity is intentionally NOT among them).

    Raises:
        FileNotFoundError: if ``B0005.mat`` has not been downloaded.
    """
    import scipy.io as sio

    cache_dir = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
    mat_path = _require(cache_dir / _BATTERY_FILE, "nasa_battery")
    mat = sio.loadmat(str(mat_path))
    cycles = mat["B0005"][0, 0]["cycle"]

    rows: list[list[float]] = []
    caps: list[float] = []
    for i in range(cycles.shape[1]):
        if str(cycles[0, i]["type"][0]) != "discharge":
            continue
        d = cycles[0, i]["data"][0, 0]
        v = np.asarray(d["Voltage_measured"], dtype=float).ravel()
        vload = np.asarray(d["Voltage_load"], dtype=float).ravel()
        temp = np.asarray(d["Temperature_measured"], dtype=float).ravel()
        cur = np.asarray(d["Current_measured"], dtype=float).ravel()
        t = np.asarray(d["Time"], dtype=float).ravel()
        cap = float(np.asarray(d["Capacity"], dtype=float).ravel()[0])
        if v.size == 0 or t.size == 0:
            continue
        rows.append(
            [
                float(v.mean()),
                float(v.min()),
                float(vload.mean()) if vload.size else 0.0,
                float(temp.mean()),
                float(temp.max()),
                float(cur.mean()),
                float(t.max()),
            ]
        )
        caps.append(cap)

    if not rows:
        raise ValueError(f"no discharge cycles parsed from {mat_path}")

    X = np.asarray(rows, dtype=float)
    caps_arr = np.asarray(caps, dtype=float)
    initial_capacity = float(caps_arr[0])
    threshold = degraded_fraction * initial_capacity
    y = (caps_arr < threshold).astype(int)
    return X, y, list(_BATTERY_FEATURE_NAMES)


# --------------------------------------------------------------------------- #
# CWRU bearing loader
# --------------------------------------------------------------------------- #
_BEARING_FEATURE_NAMES = [
    "rms",            # root-mean-square amplitude
    "kurtosis",       # impulsiveness (rises with bearing defects)
    "peak",           # max absolute amplitude
    "crest_factor",   # peak / rms
    "std",            # standard deviation
    "band_energy_1",  # FFT band energy, low band
    "band_energy_2",  # FFT band energy, mid-low band
    "band_energy_3",  # FFT band energy, mid-high band
    "band_energy_4",  # FFT band energy, high band
]

# Segment length (samples) for windowing the 12 kHz vibration signal.
_BEARING_WINDOW = 2048


def _bearing_features(segment: np.ndarray) -> list[float]:
    """Classical time- and frequency-domain features for one vibration window."""
    seg = np.asarray(segment, dtype=float).ravel()
    rms = float(np.sqrt(np.mean(seg**2)))
    std = float(np.std(seg))
    peak = float(np.max(np.abs(seg)))
    mean = float(np.mean(seg))
    # Fisher kurtosis (0 for a Gaussian); guard against zero variance.
    if std > 1e-12:
        kurt = float(np.mean(((seg - mean) / std) ** 4) - 3.0)
    else:
        kurt = 0.0
    crest = peak / rms if rms > 1e-12 else 0.0

    # FFT magnitude spectrum split into 4 contiguous bands; use fractional energy
    # so amplitude scaling between files does not dominate.
    spec = np.abs(np.fft.rfft(seg))
    power = spec**2
    total = float(power.sum()) + 1e-12
    bands = np.array_split(power, 4)
    band_energy = [float(b.sum() / total) for b in bands]

    return [rms, kurt, peak, crest, std, *band_energy]


def load_bearing_dataset(
    cache_dir: Optional[Path] = None,
    *,
    window: int = _BEARING_WINDOW,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Load the CWRU 12 kHz drive-end bearing benchmark as ``(X, y, names)``.

    Each cached ``.npz`` holds the raw drive-end (``DE``) vibration channel for
    one condition (normal, inner-race fault, outer-race fault). The signal is
    windowed into non-overlapping segments of ``window`` samples; each segment
    becomes one sample with classical statistical + FFT-band features. Label is
    ``0`` for the normal baseline and ``1`` for any seeded fault. Validates the
    MOTOR subsystem detector on REAL data.

    Args:
        cache_dir: directory holding the CWRU ``.npz`` files (defaults to data/real/).
        window: segment length in samples.

    Returns:
        ``X`` (n_windows, 9) float array, ``y`` (n_windows,) int array, and the
        feature-name list.

    Raises:
        FileNotFoundError: if the CWRU files have not been downloaded.
    """
    cache_dir = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR

    feats: list[list[float]] = []
    labels: list[int] = []
    for fname, label in _BEARING_FILES.items():
        path = _require(cache_dir / fname, "cwru_bearing")
        with np.load(str(path)) as npz:
            if "DE" not in npz.files:
                raise ValueError(
                    f"{path} missing expected drive-end 'DE' channel "
                    f"(has {npz.files})"
                )
            sig = np.asarray(npz["DE"], dtype=float).ravel()
        n_seg = sig.size // window
        for s in range(n_seg):
            seg = sig[s * window : (s + 1) * window]
            feats.append(_bearing_features(seg))
            labels.append(label)

    if not feats:
        raise ValueError(
            f"no vibration windows extracted from CWRU files in {cache_dir}"
        )

    X = np.asarray(feats, dtype=float)
    y = np.asarray(labels, dtype=int)
    return X, y, list(_BEARING_FEATURE_NAMES)


__all__ = [
    "DATASET_SOURCES",
    "DEFAULT_CACHE_DIR",
    "download",
    "fetch_dataset",
    "load_battery_dataset",
    "load_bearing_dataset",
]
