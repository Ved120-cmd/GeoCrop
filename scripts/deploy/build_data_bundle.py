"""Copy the files the API reads at runtime into deploy/runtime (committed to git; the Docker image overlays it on /app).

The full data/ tree is tens of GB (raw satellite archives, caches); the running API needs only ~55 MB of it.
Re-run after a data update (python -m geocrop.monitor.update), then commit and push to redeploy:

    python scripts/deploy/build_data_bundle.py
"""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC, DST = ROOT, ROOT / "deploy/runtime"

LATEST_LOG = "reports/monitor_logs/<latest update_*.json>"

# (source glob relative to the project root, why it is needed)
INCLUDE = [
    ("data/processed/monitor/district_series/**/*.parquet", "Monitor time series"),
    ("data/processed/monitor/indices/*.parquet", "Monitor indices (VHI, SPI, soil moisture, ...)"),
    ("data/processed/monitor/nowcast/*", "district stress nowcast"),
    ("data/processed/monitor/weather/*.parquet", "district weather + ECMWF forecast (nowcast, simulator)"),
    ("data/processed/predict/*", "Predict forecasts and drivers"),
    ("data/processed/soil/*", "district soil tables"),
    ("data/processed/advisor/runs/*.parquet", "Crop Advisor evidence base"),
    ("data/interim/boundaries/*.geojson", "district and state boundaries"),
    ("data/raw/plant_health/ipm_references/ipm/NIPHM_IPM_{Soyabean,Cotton,Maize,Sorghum,Sunflower,Wheat,Potato,Tomato}.pdf", "official IPM packages"),
    (LATEST_LOG, "data freshness shown in the site banner"),
]


def expand(pattern):
    if pattern == LATEST_LOG:
        logs = sorted((SRC / "reports/monitor_logs").glob("update_*.json"))
        return logs[-1:]
    if "{" in pattern:
        head, rest = pattern.split("{", 1)
        opts, tail = rest.split("}", 1)
        return [p for o in opts.split(",") for p in SRC.glob(head + o + tail)]
    return list(SRC.glob(pattern))


def main():
    if DST.exists():
        shutil.rmtree(DST)
    manifest, total = [], 0
    for pattern, why in INCLUDE:
        files = [f for f in expand(pattern) if f.is_file()]
        if not files:
            raise SystemExit(f"nothing matches {pattern} ({why}) - build the data first")
        for f in files:
            rel = f.relative_to(SRC)
            out = DST / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, out)
            size = f.stat().st_size
            total += size
            if size > 95e6:
                raise SystemExit(f"{rel} is {size / 1e6:.0f} MB; GitHub rejects files over 100 MB")
            manifest.append(dict(path=str(rel).replace("\\", "/"), bytes=size, sha256=hashlib.sha256(f.read_bytes()).hexdigest()[:16]))
    (DST / "MANIFEST.json").write_text(json.dumps(dict(built=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                      total_mb=round(total / 1e6, 1), files=manifest), indent=1))
    print(f"deploy/runtime: {len(manifest)} files, {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
