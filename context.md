# GeoCrop: project context

> A running record of what GeoCrop is, what has been built, the decisions taken and why, known issues, and what comes next.
> Read this first when resuming work. Last updated: **2026-11-19**.
> Detailed method documents: [docs/MONITOR.md](docs/MONITOR.md), [docs/SIMULATOR.md](docs/SIMULATOR.md), [reports/GEOCROP_READINESS_REPORT.md](reports/GEOCROP_READINESS_REPORT.md).

---

## 1. What GeoCrop is

GeoCrop is an AI-assisted agricultural intelligence platform for **Maharashtra, India**. It covers all 36 districts, 2015 to today, and individual farms.

| Module | Purpose | Status |
|---|---|---|
| **Monitor** | Satellite and weather monitoring, drought and crop-stress indices, today's water-stress estimate | **Built** (backend + UI) |
| **Soil Intelligence** | District soil profile, water-holding capacity | **Basic version built** (SoilGrids estimates, UI page) |
| **Farm Simulator** | "What if" yield and water simulations with FAO AquaCrop 7.3 | **Built** (backend + UI) |
| **Predict** | 16- and 32-day dry-soil early warning (LightGBM, SHAP) | Built 2026-11-19 (docs/PREDICT.md) |
| **Crop Advisor** | Crop ranking per district, season and water from simulated past seasons | Built 2026-11-21 (docs/CROP_ADVISOR.md) |
| **Plant Doctor** | Leaf-disease screening from a photo (EfficientNet-B0) | Built 2026-11-20 (docs/PLANT_DOCTOR.md) |

**Guiding principles agreed with the user:**
- Never invent agronomic values, labels, metrics or data.
- Every number is labelled as observed, estimate, provisional or forecast, with its date.
- Prefer official sources.
- Be explicit about limitations.

---

## 2. Machine and environment

* **Windows 11, 16 GB RAM.** C: is about 99% full, so the pagefile can't grow and commit memory runs out when VS Code and Chrome are open.
  * Stop the preview servers before heavy jobs.
  * Freeing C: or moving the pagefile to D: would help; that is the user's decision.
* **Drive rules (user instruction):**
  * Project and data live on **E:\projects\soil**.
  * Scratch, temporary files and caches go on **D:\geocrop_work** (`tmp`, `pip-cache`, `npm-cache`, `aquacrop_runs`).
  * **Never use C:** for working files.
* **Python:** project virtual environment `E:\projects\soil\.venv` (Python 3.11). The global Python's numpy/sklearn are broken, so don't use it. Run Python with `TEMP=D:/geocrop_work/tmp`.
* **Node 24 / npm 10:** frontend in `frontend/`, npm cache on D:.
* **PostgreSQL 17.12**, portable EnterpriseDB build (signature verified):
  * binaries in `D:\geocrop_work\pgsql`, data in `E:\projects\soil\db\pgdata`;
  * listens on **localhost:5433** only;
  * credentials in `E:\projects\soil\.env` (never commit or print the password);
  * start/stop with `scripts\db\start_db.cmd` / `stop_db.cmd`. It does not auto-start after a reboot.
* **Google Earth Engine:** authenticated for the Python client via `earthengine authenticate --auth_mode=notebook`. The working Cloud project is **`neuramach`**; the user's other project `451632937241` has the EE API disabled.
* **Preview configs** in `.claude/launch.json`: `geocrop-api` (uvicorn :8000) and `geocrop-web` (Vite :5173, proxies `/api` to :8000).
* **Unrelated user files** in the project root, not part of GeoCrop: `lonar_audiobook/`, `resume/`, `practice*.py`.

---

## 3. Repository layout

```
datasets/              user's ORIGINAL files (audited in place; never modified)
data/raw/              downloaded source data by dataset (originals preserved)
data/interim/          derived subsets (Maharashtra boundaries, IMD temp NetCDF, label caches)
data/processed/        monitor/{district_series,indices,weather,nowcast}, soil/*.parquet
data/reference/        district_name_crosswalk.csv, regions.csv, fao56_crop_params.csv (+ SOURCES.md)
data/manifests/        file inventory from the audit
db/                    PostgreSQL data directory + log
geocrop/               Python package
  config.py            paths and constants (scratch on D:, baseline 2015-2024, GEE project)
  db.py                SQLAlchemy models: farmers, farms, crop_plantings, irrigation_events
  common/              districts (registry + label rasters), zonal (fast district stats), gridweights, eto (FAO-56)
  monitor/             products (QA decoding), build_series, weather, indices, soilwater, nowcast,
                       forecast_ecmwf, update (daily job)
  soil/                district_props (SoilGrids district summary, USDA texture)
  simulator/           aquacrop (file writers + engine runner), scenario (Maharashtra inputs, multi-season runs)
  api/                 main.py (Monitor API), app_routes.py (geo, overview, soil, profiles), simulator_routes.py
frontend/              React 19 + TypeScript + Tailwind v4 + react-router + React Query + Leaflet + Recharts
  src/pages/           Home, Onboarding, MonitorOverview, DistrictPage, MyFarm, SoilPage, SimulatorPage, ModulePage
  src/lib/             api.ts, i18n.tsx (EN/MR), scales.ts (validated colours), indicators.ts, profile.tsx
simulator/aquacrop/    official_src (FAO AquaCrop 7.3, untouched), gui_ac73 (FAO crop/soil DB),
                       engine_patched (official + 1 documented fix, PATCHES.md)
scripts/               audit/, download/, gee/ (Earth Engine downloader), db/, preprocessing/, validation/
tests/                 pytest: core science, API integration, app routes, simulator (28 tests)
docs/                  MONITOR.md, SIMULATOR.md
reports/               readiness report, dataset/model audits, download logs, monitor update logs, validation
```

---

## 4. Timeline: what was done

### Phase 1: Data audit (2026-11-12)
* Inventoried the user's `datasets/` folder: 79 files, 20 MB.
  * **Usable:** partial DES crop statistics (HTML tables saved as `.xls`; 4 of 5 don't name their crop); the genuine FAO AquaCrop 7.3 source (checksum matches the official release); a GIEWS PDF; Earth Engine script snippets.
  * **Invalid:** 60 `out*.tif` files that were empty Gulf-of-Guinea exports (Earth Engine run with no region). The **user deleted them on 2026-11-13 and wants them left deleted**. Also a 0-byte IMD NetCDF and a *Madhya Pradesh* aquifer map.
* Built the audit tooling (`scripts/audit/`) and the readiness report.
* Downloaded the public, credential-free official data:
  * **Boundaries:** geoBoundaries, 36 districts.
  * **Weather:** NASA POWER (127 cells); IMD rainfall 0.25° (1991–2025); IMD Tmax/Tmin 1°; CHIRPS.
  * **Soil and terrain:** SoilGrids 2.0 (60 layers); SoilGrids 2017 water layers; Copernicus DEM GLO-90.
  * **Plant health:** PlantVillage; PlantDoc; 38 NIPHM IPM packages; 6 CIB&RC pesticide lists.
  * **Simulation:** AquaCrop GUI databases.

### Phase 2: Earth Engine data (2026-11-13)
* `scripts/gee/download_gee_direct.py` downloads straight to E: (no Google Drive), on each product's native grid, clipped to the Maharashtra polygon, with explicit NODATA (never 0), QA bands kept and resumable.
  * Fixed EE's fill-value quirks (0 / −inf outside the footprint).
  * Fixed a mask-aware merge that was erasing QC = 0 ("good" quality) values.
* Downloaded 2015–2025: MOD13Q1 (253), MOD11A2 (506), MOD16A2GF (506), MCD12Q1 (11), SMAP L4 daily (3,929), GPM IMERG daily (4,018).
* Data readiness went from 5.7% to **54.3%** (weighted).

### Phase 3: Monitor backend (2026-11-13)
* **District time series:** mean, median, p10, p90 and valid fraction, for all land and cropland, built with fast single-sort zonal stats (verified equal to pandas).
* **Weather:**
  * district IMD/CHIRPS rain, IMD temperature, NASA POWER;
  * FAO-56 Penman–Monteith reference ET, checked against FAO worked examples.
* **Indices**, all against a frozen baseline:
  * VCI, TCI and VHI;
  * SMAP percentile;
  * ET/PET anomaly;
  * SPI-1 and SPI-3 (IMD 1991–2020);
  * IMD monsoon departure.

  Rain after IMD's last release uses IMERG scaled to IMD, flagged provisional. The indices reproduce the 2015 and 2018 Marathwada droughts and the Kolhapur 2019 floods.
* **Today's-stress nowcast:** FAO-56 water balance started from SMAP, run forward with observed weather plus the ECMWF open-data 10-day forecast.
  * District mode uses the MODIS ET/PET landscape coefficient. Backtest against SMAP: skill +0.10 at 7 days and +0.25 at 14 days. The Kc = 1 version failed and was replaced.
  * Field mode uses FAO-56 crop parameters, the sowing date and logged irrigation.
* **Soil water:** SoilGrids 2017 AWCh layers are *available* capacity, not water content. They were misread at first, then corrected. Even read correctly they gave implausible values (22–77 mm/m), so **Saxton–Rawls** on SoilGrids 2.0 is the default (127–143 mm/m).
* **Daily update job** (`python -m geocrop.monitor.update`):
  * incremental Earth Engine downloads, including MOD16A2 near-real-time ET (provisional);
  * provisional-to-Final IMERG replacement;
  * POWER refresh;
  * ECMWF forecast;
  * series, indices and the district stress precompute;
  * writes a JSON log to `reports/monitor_logs/`.
* **First live run:** the data show a drought-like 2026 post-monsoon. Monsoon rain was about −29% (provisional) and SMAP was near the 2018 drought level.

### Phase 4: Frontend (2026-11-13)
* React + Tailwind following `datasets/DESIGN.md` ("Arva" pastoral editorial style):
  * cream canvas, forest-green header and footer, a lime freshness strip;
  * pill buttons and pastel quilt cards;
  * Source Serif 4 instead of Reckless, plus Inter and Devanagari fonts.
* **User decisions:**
  * profiles in **PostgreSQL**;
  * farm location by **map pin + details**;
  * **English + Marathi** toggle (the Marathi text is a draft needing native review);
  * unbuilt modules shown as **honest status pages**.
* **Pages:**
  * Home;
  * Onboarding (4 steps; the pin is checked against the chosen district);
  * Monitor overview (choropleth, 6 indicators, regions including Khandesh, ranked list);
  * District page (status cards, 10-day stress outlook, NDVI / SMAP / monsoon charts);
  * My farm (field stress plus irrigation log);
  * Soil;
  * Simulator;
  * module status pages.
* **Colour scales** were validated with the dataviz checker: a terracotta dry/stress ramp, a blue wet ramp, sage for no stress. The status palette was rejected because mild and moderate were indistinguishable.

### Phase 5: Farm Simulator (2026-11-19)
* `geocrop/simulator/` writes AquaCrop input files (climate, soil, initial water, irrigation, project) into isolated run folders on D:. It runs the engine in a subprocess and batches several seasons per process (about 0.6 s of engine time per season).
* **Found a bug in FAO's official 7.3 Python engine:** `RequiredTimeNew` is called without `VirtualTimeCC`, so the engine crashes under canopy stress.
  * Fixed in `simulator/aquacrop/engine_patched/` with a byte-exact one-line patch; the diff and explanation are in PATCHES.md.
  * Should be reported upstream at https://github.com/un-fao/fao-AquaCrop/issues.
* **Inputs:**
  * district POWER temperature and ET plus IMD/IMERG-scaled rain;
  * 4 Saxton–Rawls soil horizons with Ksat;
  * SMAP initial water on the sowing date;
  * FAO GDD crop files: soybean (Patancheru), cotton, maize, sorghum, wheat, sunflower, tomato, potato.
* **Output:** water-limited **attainable** yield (perfect fertility, no pests).
  * AquaCrop's fertility-stress setting has **no effect** with these crop files (their response is uncalibrated), so it isn't offered.
  * The emphasis is on comparing scenarios (up to 3) across about 12 real past seasons.
* **Check:** Latur soybean. Rainfed collapses in 2015, 2018 and 2026; "irrigate when needed" gives +13% median yield for +152 mm.
* **Also fixed:** NASA POWER had **no data for Jan–Oct 2026**. The update fetched only 40 days, so the job now fetches from the archive end. The backfill made Monitor's 2026 reference ET real instead of climatology, and the stress picture grew more severe.
* Moved the rain extension to a persisted file (`rain_imd_extended.parquet`) to cut memory use.

### Phase 6: Predict (2026-11-19)
* `geocrop/predict/`: leakage-safe features (publication delays SMAP 3, rain 1, POWER 3, NDVI 32, LST 16, ET 24 days), training, daily inference, model card. Details: [docs/PREDICT.md](docs/PREDICT.md).
* **Target:** SMAP root-zone percentile at +16 and +32 days. This is a **proxy**, not measured crop stress. No weather forecasts are used (no reforecasts).
* **Split and selection:** train 2015–21, validation 2022–23, test 2024–26. The model formulation was chosen **on validation only**: an early version eyeballed test results, and this was corrected.
* **Honest results:**
  * The dry-risk probability is useful: Brier skill +0.48 (16 d) and +0.37 (32 d), precision 0.88, recall 0.39.
  * Point forecasts are only 4–7% better than "no change". At 32 d, damped persistence beats the model.
  * In the 2026 drought the model did worse than "no change".
* **Deployment:**
  * The daily update gained a `predict_forecast` step.
  * New API `/predict/*`.
  * New page `/predict`: risk map, district detail with range chart and SHAP drivers, reliability card.
  * `check_models.py` now verifies M1a and M1b as trained.
* Tests: 34 passing (`tests/test_predict.py` added).

### Phase 7: Plant Doctor (2026-11-20)
* `geocrop/plantdoctor/`: EfficientNet-B0 transfer learning, covering 38 classes and 14 crops. Data: PlantVillage (lab) plus PlantDoc (field). Details: [docs/PLANT_DOCTOR.md](docs/PLANT_DOCTOR.md).
* **Splits:** grouped by leaf (leaf map, photo sequence, near-exact hash); PlantDoc de-duplicated against training. A loose hash threshold chained groups and was rejected.
* **Test results:**
  * Lab 99.6%.
  * **Field 70.1% top-1, 81.4% with the crop given,** 91.8% top-3, 96.5% healthy vs diseased.
  * Temperature refit on field validation (disclosed): ECE went from 0.16 to 0.077.
* **Machine fixes:**
  * The page file was moved to D: by the user, because the commit limit was exhausted (GPU allocations count against it under WDDM). Commit limit is now 29 GB.
  * `channels_last` is 9× slower with this cuDNN, so it isn't used.
  * `python-multipart` and `huggingface_hub` installed. torch 2.5.1+cu124 and timm 1.0.12 added.
* **Deployment:** API `/doctor/info` and `/doctor/diagnose`; page `/plant-doctor` with photo upload or camera, top-3 results, reliability card and next steps. Photos are not stored.
* **Not covered:** cotton, soybean diseases, onion, sugarcane, pulses and pomegranate are the biggest gaps for Maharashtra.
* Tests: 37 (`tests/test_doctor.py` added).

### Phase 8: Crop Advisor + simulator fixes (2026-11-20 to 21)
* **Approach:** `geocrop/advisor/` ranks crops by how they would have done in each district's real past seasons, simulated with AquaCrop. No invented agronomic rules. Details: [docs/CROP_ADVISOR.md](docs/CROP_ADVISOR.md).
  * **Grid:** about 27k seasons. Kharif: 5 crops × 3 sowing dates. Rabi: 6 crops × 4 dates. Each rainfed and irrigated, 2015–2025, all 36 districts.
  * **Ranking:** FAO (1976) suitability classes from relative yield against the best districts under the same water regime.
  * **Card details:** bad-year risk, irrigation need, sowing-date sensitivity, official NIPHM IPM PDF, and this season's SMAP and Predict context.
* **Honesty checks:**
  * Rain-only rabi potato and tomato are not ranked (irrigated crops in practice).
  * Crop-file notes: the potato file matures in about 60 days here; the sorghum (Texas) and maize (California) files give high attainable yields.
  * FAO-56 season-length check; edge-of-window flags; a rainfed crop's share of its irrigated potential.
  * Rainfed non-establishment counts as a failed season; irrigated non-completion is an engine anomaly and excluded.
* **Farm Simulator input bugs fixed** (they affected all earlier simulator results; see docs/SIMULATOR.md):
  1. The climate header said day 1 for every record, so weather was shifted by (sowing day − 1) days.
  2. Leap-year sowings after February never started the crop; fixed by relabelling with the next year.
  3. An engine crash lost the rest of its batch; lost seasons are now re-run one by one.
  4. Daily chart dates were wrong.
* **Performance:** 3 precompute processes thrashed memory (155 min per district). One process with 10 engine processes takes 3 min per district.
* **Laptop:** the laptop sleeping overnight paused the run; keep it awake during long jobs.

---

## 5. Key decisions and conventions

* **District IDs** are alphabetical by current official name, 1–36 (1 Ahilyanagar … 24 Palghar, 26 Pune … 36 Yavatmal). Use `/districts`. Names follow `data/reference/district_name_crosswalk.csv`: geoBoundaries uses 2021 names (Ahmadnagar, Aurangabad, Osmanabad…).
* **Regions** follow `data/reference/regions.csv`: Konkan, Western Maharashtra, North Maharashtra (includes **Khandesh** = Dhule, Jalgaon, Nandurbar), Marathwada, Vidarbha.
* **Cropland** means MODIS MCD12Q1 IGBP classes 12 and 14. This is broad land cover, *not* crop type.
* **Baselines:** satellite 2015–2024 (frozen, `b2015_2024_v1`); SPI uses IMD 1991–2020.
* **Status flags:** IMERG within 120 days and MOD16A2 are *provisional*. A district-date with valid fraction below 0.3 is *low_confidence* and excluded from alerts.
* **Storage:** files (Parquet / GeoTIFF) for science data; PostgreSQL for user profiles only. PostGIS is not used yet.
* **Crop parameters** come only from documented sources: FAO-56 tables, with Kc ini from crop-group rows. Chickpea, rice and tur have no FAO-56 stage data, so the field nowcast refuses them rather than inventing values.

---

## 6. How to run

```bash
scripts\db\start_db.cmd                                   # PostgreSQL (after every reboot)
.venv/Scripts/uvicorn geocrop.api.main:app --port 8000    # API (docs: http://localhost:8000/docs)
cd frontend && npm run dev                                # web app: http://localhost:5173
.venv/Scripts/python -m geocrop.monitor.update            # daily data update (~10-15 min)
.venv/Scripts/python -m pytest tests -p no:cacheprovider  # tests (43; DB tests skip if PostgreSQL is down)
```

---

## 7. Known issues and limitations

* **Daily update not scheduled.** Registering it in Windows Task Scheduler needs the user's OK, which was asked and not yet given. Without it the data go stale; one test fails when SMAP is more than 7 days old.
* **Memory pressure:** see section 2. An intermittent simulator test failure was seen under low memory.
* **Short baseline:** the 10-year satellite baseline exaggerates VHI extremes.
* **Nowcast:** no runoff term, so it is weaker in heavy-rain weeks.
* **Coarse inputs:** SMAP (9 km), rain (0.1–0.25°) and POWER (about 50 km) are district-scale.
* **Simulator yields** are attainable, not actual farm yields.
* **SoilGrids SOC** looks high (about 21 g/kg topsoil in Pune); check it against Soil Health Card data.
* **Missing data, not yet obtained:**
  * ECMWF reforecasts (account needed);
  * NBSS&LUP soil maps;
  * Soil Health Card data;
  * taluka and village boundaries;
  * IP102 pest images (manual download);
  * SAU crop calendar and calibration data;
  * DES crop statistics with crop names.
* **No authentication:** the profile ID is stored in the browser's localStorage.
* **README:** line 3 corrected 2026-11-19.

---

## 8. Next steps (candidates)

1. Schedule the daily update (Windows Task Scheduler), with user approval.
2. **Predict improvements:** add ECMWF reforecasts, the main missing source of skill; calibrate dry probabilities and improve recall; validate the proxy against ground data.
3. **Plant Doctor improvements:** collect expert-labelled Maharashtra field photos; add cotton, soybean, onion, pomegranate and grape-downy-mildew classes; add an IP102 pest model and a "not a leaf" gate.
4. **Crop Advisor improvements:** add pulses (tur, gram), onion, sugarcane, rice; SAU crop calendars and calibrated crop files; prices and costs (MSP/APMC) for an economic ranking.
5. **Simulator:** a "this season outlook" (observed weather to date plus ECMWF plus past-year analogues), calibration with SAU trial data, and a runoff term in the nowcast.
6. Report the AquaCrop bug to FAO, and get the Marathi text reviewed by a native speaker.
