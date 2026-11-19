"""Central paths and constants for GeoCrop."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
INTERIM = ROOT / "data/interim"
PROCESSED = ROOT / "data/processed"
REFERENCE = ROOT / "data/reference"
SCRATCH = Path(os.environ.get("GEOCROP_SCRATCH", r"D:\geocrop_work\tmp"))  # never C: (nearly full)

GEE_PROJECT = os.environ.get("GEOCROP_GEE_PROJECT", "neuramach")

STATE_FILE = INTERIM / "boundaries/maharashtra_state.geojson"
DISTRICT_FILE = INTERIM / "boundaries/maharashtra_districts.geojson"
CROSSWALK = REFERENCE / "district_name_crosswalk.csv"

# Climatology baseline: frozen so anomalies are stable between runs; rebuilt yearly as a versioned change.
BASELINE_START, BASELINE_END = "2015-01-01", "2024-12-31"
BASELINE_VERSION = "b2015_2024_v1"

# MODIS IGBP (LC_Type1) classes treated as cropland: 12 = croplands, 14 = cropland/natural vegetation mosaic.
CROPLAND_CLASSES = (12, 14)

SERIES_DIR = PROCESSED / "monitor/district_series"
INDEX_DIR = PROCESSED / "monitor/indices"
NOWCAST_DIR = PROCESSED / "monitor/nowcast"
LABEL_CACHE = INTERIM / "label_rasters"

for _d in (PROCESSED, SERIES_DIR, INDEX_DIR, NOWCAST_DIR, LABEL_CACHE, SCRATCH):
    _d.mkdir(parents=True, exist_ok=True)
