# GeoCrop: data and ML foundation

This repository holds the data foundation, the **Monitor** backend, the **Farm Simulator** (FAO AquaCrop 7.3; see [docs/SIMULATOR.md](docs/SIMULATOR.md)), **Predict** (16/32-day dry-soil early warning; see [docs/PREDICT.md](docs/PREDICT.md)), **Plant Doctor** (leaf-disease screening; see [docs/PLANT_DOCTOR.md](docs/PLANT_DOCTOR.md)) and **Crop Advisor** (crop ranking from simulated past seasons; see [docs/CROP_ADVISOR.md](docs/CROP_ADVISOR.md)) for GeoCrop (Maharashtra). Monitor covers the data pipeline, indices, today's-stress nowcast, a daily update job and an API. See [docs/MONITOR.md](docs/MONITOR.md). The web app is in `frontend/`. All six modules are built. Project history and decisions: [context.md](context.md).

## Layout

```
datasets/            ORIGINAL files you collected (untouched; audited in place)
data/raw/<group>/    downloaded source data, organised by dataset (originals preserved)
data/interim/        derived subsets, e.g. Maharashtra boundaries cut from geoBoundaries
data/reference/      curated lookup tables (district name crosswalk, ...)
data/manifests/      file inventory (scan_project.py)
geocrop/             Python package: common/ (districts, zonal stats, ETo), monitor/ (series, weather, indices, nowcast,
                     ECMWF forecast, daily update), api/ (FastAPI)
tests/               unit + API integration tests (pytest)
models/ ml/          ML model artefacts / pipelines (empty: no trained models yet)
simulator/aquacrop/  official FAO AquaCrop 7.3 source + GUI databases; engine_patched/ = official + 1 documented bug fix (PATCHES.md)
scripts/audit/       catalog.py, scan_project.py, validate_datasets.py, check_models.py, final_audit.py
scripts/download/    download_missing.py (public, credential-free official sources only)
scripts/gee/         export_gee_collections.py (MODIS / SMAP / IMERG / CHIRPS; needs your GEE login)
reports/             audit outputs and GEOCROP_READINESS_REPORT.md
```

## Running the app (database, API, web)

1. **PostgreSQL** (portable 17.12; binaries on D:, data in `db/`, localhost:5433 only, credentials in `.env`):
   ```bash
   scripts\db\start_db.cmd
   ```
   To stop it: `scripts\db\stop_db.cmd`
2. **API** (FastAPI; docs at http://localhost:8000/docs):
   ```bash
   .venv/Scripts/uvicorn geocrop.api.main:app --port 8000
   ```
3. **Web app** (React + Tailwind; open http://localhost:5173):
   ```bash
   cd frontend && npm run dev
   ```

Frontend layout:
- `frontend/src/pages`: Home, Onboarding, Monitor overview, District, My farm, Soil, and the module status pages.
- `frontend/src/lib`: API client, translations (English/Marathi), colour scales, indicators.

Design follows `datasets/DESIGN.md`. Marathi text is a draft awaiting native-speaker review.

## Monitor

```bash
.venv/Scripts/python -m geocrop.monitor.update
```
```bash
.venv/Scripts/uvicorn geocrop.api.main:app --port 8000
```
```bash
.venv/Scripts/python -m pytest tests -p no:cacheprovider
```

## Re-running the data audit

```bash
.venv/Scripts/python scripts/audit/scan_project.py
.venv/Scripts/python scripts/audit/validate_datasets.py
.venv/Scripts/python scripts/audit/check_models.py
.venv/Scripts/python scripts/download/download_missing.py --list
.venv/Scripts/python scripts/download/download_missing.py --only D14 --sg-quantities mean Q0.05 Q0.95 uncertainty
.venv/Scripts/python scripts/audit/final_audit.py
```

The audit runs in `.venv` (Python 3.11) because the global Python install has a broken numpy/scikit-learn combination (importing sklearn raises a RecursionError). `requirements-audit.txt` pins the audit environment. ML libraries (xgboost, lightgbm, shap, torch, timm) are deliberately not installed yet.

All requirements, sources, licences and weights live in `scripts/audit/catalog.py`.
