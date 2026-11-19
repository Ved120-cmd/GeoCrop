# GeoCrop readiness report: data and ML foundation

Generated 2026-11-12, updated 2026-11-13 after the Earth Engine downloads (`scripts/audit/final_audit.py` plus manual review). Scope: Maharashtra, 2015–2025.
Every status below comes from inspecting file contents (raster metadata and sampled pixels, NetCDF variables and time axes, CSV schemas, geometry validity, checksums). No status is based on filenames alone.

## Update 2026-11-13: Earth Engine data acquired

After you authenticated Earth Engine (project `neuramach`), `scripts/gee/download_gee_direct.py` downloaded the products below straight to E:. Every image is clipped to the Maharashtra polygon on the product's native grid. Pixels outside the state, or masked in the source, are explicit NODATA, never 0. QA bands are kept; raw values are stored with scale factors in the GeoTIFF tags.

| ID | Product | Time steps | Coverage | Status |
|---|---|---|---|---|
| A1 | MOD13Q1 NDVI/EVI + SummaryQA, 250 m 16-day | 253 / 253 | 2015-01-01 → 2025-12-19 | NEEDS PREPROCESSING (scaling, QA masking) |
| A2 | MOD11A2 LST day/night + QC, 1 km 8-day | 506 / 506 | 2015-01-01 → 2025-12-27 | NEEDS PREPROCESSING |
| A3 | MOD16A2GF ET/PET + QC, 500 m 8-day | 506 / 506 | 2015-01-01 → 2025-12-27 | NEEDS PREPROCESSING |
| A4 | MCD12Q1 land cover (IGBP/UMD) + QC, 500 m annual | 11 / 11 | 2015 → 2025 | VALID (broad land cover, not crop type) |
| C10 | SMAP L4 v008 surface/root-zone/profile moisture, daily mean of 3-hourly | 3,929 / 3,929 | 2015-03-31 (start of record) → 2025-12-31 | NEEDS PREPROCESSING |
| B9 | GPM IMERG V07 Final, daily total (UTC day) | 4,018 / 4,018 | 2015-01-01 → 2025-12-31 | NEEDS PREPROCESSING |

The test batches caught and fixed two problems in the downloader. Earth Engine fills outside-footprint pixels with 0 or −inf depending on the data type, so out-of-state pixels are now masked locally. A mask-aware merge would also have erased valid QC = 0 ("good quality") values, so tiles are now merged exactly. A handful of requests hung; they were retried successfully and a call deadline was added. There are no duplicate dates, and all 40 sampled rasters per product pass coverage and validity checks. These products total about 6.6 GB.

The 60 invalid `datasets/out*.tif` files (Gulf of Guinea exports, item X1) were deleted by the owner on 2026-11-13 and sent to the Windows Recycle Bin. That was confirmed intentional; they carried no readiness weight.

## 1. Overall readiness: **32.6 %** (was 25.0 % before Earth Engine; 5.7 % data at start)

| Component | Score | Weight in overall |
|---|---|---|
| Data readiness (weighted) | **54.3 %** (41.7 % before Earth Engine; 5.7 % at start) | 60 % |
| Model readiness | **0 %** (no model, pipeline or ML library exists) | 40 % |

**How the weighting works.** Each of the 39 required datasets carries an importance weight from 1 to 5, defined in `scripts/audit/catalog.py`. Critical items such as MODIS NDVI, SMAP, NASA POWER, IMD rain, SoilGrids, boundaries, the crop calendar and AquaCrop get 5.

Each dataset scores by its status:

| Status | Score |
|---|---|
| VALID | 1.0 |
| NEEDS PREPROCESSING | 0.75 |
| INCOMPLETE | 0.4 |
| MISSING / INVALID / RESTRICTED | 0 |

Each of the 7 models scores by the fraction of 8 components present: labels, preprocessing, training code, config, checkpoint, metrics, inference and docs. The rule-based crop-suitability model is scored on 6 of these, since it needs no checkpoint or labels.

Overall readiness = 0.6 × data + 0.4 × models.

### Module readiness

| Module | Data | Models | Overall | Main blockers |
|---|---|---|---|---|
| Monitor | 78.0 % | 0 % | **46.8 %** | Sentinel-1/2 (per-farm, on demand), crop-classification model |
| Predict | 59.8 % | 0 % | **35.9 %** | ECMWF reforecasts, crop calendar, validated labels, models |
| Soil Intelligence | 63.0 % | n/a | **63.0 %** | NBSS&LUP maps, Soil Health Card lab data |
| Crop Advisor | 43.7 % | 0 % | **26.2 %** | crop calendar, SAU recommendations, FAO Kc tables, SHC |
| Plant Doctor | 73.5 % | 0 % | **44.1 %** | IP102, Maharashtra field images, no trained model |
| Farm Simulator | 66.9 % | n/a | **66.9 %** | no AquaCrop project file, no calibration data, crop calendar |

## 2. Datasets present and valid (9)

| ID | Dataset | Evidence |
|---|---|---|
| B5 | NASA POWER daily: T2M, T2M_MAX, T2M_MIN, RH2M, PRECTOTCORR, WS2M, ALLSKY_SFC_SW_DWN | 127 MERRA-2 cells (0.5° × 0.625°, **not** 1 km). 2015-01-01 to 2025-12-31. 0 duplicate rows, 0 fill values. Units in `.meta.json`. |
| B6 | IMD 0.25° daily rainfall | 11 yearly NetCDFs (2015–2025). Variable `RAINFALL`; Maharashtra subset valid. |
| B8 | CHIRPS v2.0 daily, 0.25° | 2015–2025 global yearly files (crop to Maharashtra during preprocessing). |
| D14b | SoilGrids250m 2017 water retention | 35 layers: **available** water capacity with field capacity at −10/−20/−31.6 kPa (AWCh1–3, i.e. θFC − θWP), water content at wilting point (WWP, −1500 kPa) and saturation (AWCtS), 7 depths, Maharashtra window. *(Corrected 2026-11-13: AWCh layers were earlier mis-described as water contents.)* |
| E17 | Copernicus DEM GLO-90 (substitutes for SRTM, which needs a login) | 44 tiles covering 100 % of the state polygon; slope can be derived. |
| E18a | State plus 36 district boundaries (geoBoundaries 2021, sourced from LGD) | 36 polygons, 0 invalid geometries, EPSG:4326. Names predate the 2023–24 renames; crosswalk in `data/reference/`. |
| P29 | PlantVillage (color) | 38 classes, 54,305 images, leaf-grouped train/test splits (prevents leakage). |
| P30 | PlantDoc | 29 classes, 2,573 field images; 87 filenames sanitised for Windows (logged). |
| S35 / S35b | FAO AquaCrop 7.3 Python source and GUI databases | SHA-256 matches the official GitHub release. 29 crop files and 14 soil files. Engine runs on Python 3.11. |

## 3. Present but needs preprocessing or incomplete (7)

| ID | Dataset | What is needed |
|---|---|---|
| D14 | SoilGrids 2.0: clay, sand, silt, bdod, cfvo, pH, SOC, CEC, N, OCD; 6 depths, mean (60/60 layers) | Values are integer-scaled (`CONVERSION_FACTORS.json`) and in Homolosine projection. Quantile/uncertainty layers exist on the server but were not downloaded (`--sg-quantities Q0.05 Q0.95 uncertainty`). This is a global model: do not claim farm-level accuracy. |
| B7 | IMD 1° Tmax/Tmin | Raw binaries for 2015–2025; **already converted** to NetCDF in `data/interim/imd_temp_1deg/` (sanity check: Maharashtra May Tmax 39 °C). |
| P32 | NIPHM AESA IPM packages | 38 Maharashtra-relevant crop PDFs (no Cashew package exists). Needs curation into a structured knowledge base. |
| P33 | CIB&RC Major Uses of Pesticides (as on 30.09.2026) | 6 PDFs. Label claims, dose and waiting period must be extracted verbatim, never inferred. |
| F20 | FAO GIEWS India brief | National level only; reference use. |
| F19 | DES district APY (your 5 files) | **Incomplete.** HTML tables saved as `.xls`. 4 of 5 don't name their crop or crop group. Years 2014-15 to 2022-23 only (no 2023-24 onward). Only the sugarcane/tobacco report is crop-identified. |

## 4. Present but invalid (3)

| ID | Item | Problem |
|---|---|---|
| X1 | `datasets/out*.tif` (60 files; **deleted by owner 2026-11-13**) | Earth Engine exports with no region set: they cover 0–2° E / 0–2° N (Gulf of Guinea) and contain only zeros or nodata. 59 are identical. **Not usable.** `scripts/gee/export_gee_collections.py` fixes the cause. |
| B6-legacy | `datasets/RF25_indselect_rfp25.nc` | 0 bytes (failed download). Superseded by the 11 downloaded years. |
| C12 | `datasets/Madhya Pradesh - Depth of First Aquifer.zip` | Valid CGWB raster, but for **Madhya Pradesh**, not Maharashtra. |

## 5. Missing (14 after the Earth Engine update)

**Access restricted (4)**

* ~~A1–A4 MODIS, C10 SMAP, B9 IMERG~~: **acquired 2026-11-13** via Earth Engine (see Update).
* H26–H28 Sentinel-2/1 and Landsat: Earth Engine works now, but a statewide 10–30 m archive for 2015–2025 is multi-terabyte. Acquire per farm or AOI on demand when the crop-classification work starts.
* G24 ECMWF S2S forecasts and **reforecasts**: ECMWF account (S2S archive, non-commercial) or CDS account plus licence acceptance. Reforecasts are mandatory for training the 16/32-day models without future-weather leakage.

**Manual, portal or data-request (10)**

* D15 NBSS&LUP soil resource maps: written request to the Director, ICAR-NBSS&LUP, Amravati Road, Nagpur 440033 (https://nbsslup.icar.gov.in/). Bhoomi Geoportal layers are view-only.
* D16 Soil Health Card laboratory data (https://soilhealth.dac.gov.in/): use aggregated village/block reports. Farmer-level cards are personal data.
* E18b Taluka/village boundaries: MRSAC (https://mrsac.gov.in/), Survey of India (https://onlinemaps.surveyofindia.gov.in/) or Bhuvan. No verified open bulk download.
* F21 SAU package of practices (MPKV, PDKV, VNMKV, DBSKKV) and F23 **structured crop calendar**. Template: `data/raw/crop/crop_calendar/CROP_CALENDAR_TEMPLATE.md`. Nothing was invented.
* F22 FAO-56 Kc, stage lengths, root depth and p: reference tables at https://www.fao.org/4/x0490e/x0490e00.htm, to be transcribed with citations.
* C11 India-WRIS, C13 Maharashtra WRD: interactive portals.
* G25 IMD extended-range forecast archive: on request from IMD Pune.
* P31 IP102: README links to Google Drive/AliyunDrive only, and no licence is stated. Download manually after accepting its research-use terms.
* P34 NCOF / natural farming references.
* S35c AquaCrop calibration/validation data (SAU or AICRP field trials).

## 6. Models

| Model | Status | Present | Missing |
|---|---|---|---|
| Water stress 16-day and 32-day (XGBoost/LightGBM) | NOT TRAINED | nothing | labels, features, reforecasts, all code, libraries |
| Crop suitability (rule-based) | NOT BUILT | soil inputs (D14/D14b) | crop requirement KB, calendar, rules code |
| Plant disease (EfficientNet/MobileNet) | NOT TRAINED | PlantVillage and PlantDoc data | pipeline, checkpoint, metrics, Maharashtra field images |
| Pest detection (IP102) | NOT TRAINED | nothing | IP102 data and all components |
| Crop classification (S1/S2) | NOT TRAINED | nothing | S1/S2 data and, critically, **ground-truth crop labels** |
| Explainability (SHAP) | NOT BUILT | nothing | everything |

There are no checkpoints anywhere in the project. In `.venv`, xgboost, lightgbm, shap, scikit-learn, torch and timm are **not installed**. Your global Python has torch 2.5.1, but its numpy/scikit-learn stack is broken: importing sklearn raises a RecursionError.

**Label gap (blocks M1).** No validated crop-water-stress labels exist. SMAP-derived indices may be used only as clearly marked *proxy* targets, not as ground truth.

## 7. Downloaded in this run

Project total is now about 14.8 GB on E: (including the 0.8 GB Python environment). Earth Engine products: MODIS 6.5 GB, SMAP 0.1 GB, IMERG 0.03 GB. Earlier public downloads: weather 1.26 GB, soil 0.61 GB, terrain 0.20 GB, plant health 4.9 GB including the PlantDoc archive. See `reports/download_logs/download_log.csv` for the URL, timestamp, SHA-256 and licence of every file.

geoBoundaries IND ADM1/ADM2 · NASA POWER (127 cells) · IMD rain (11 yr) · IMD Tmax/Tmin (22 files) · CHIRPS p25 (11 yr) · SoilGrids 2.0 (60 layers) · SoilGrids 2017 water retention (35 layers) · Copernicus GLO-90 (44 tiles) · AquaCrop 7.3 GUI, release notes and source (checksum verified) · PlantVillage · PlantDoc · 38 NIPHM IPM PDFs · 6 CIB&RC PDFs.

These were unavailable at the source: GLO-90 tile N17E072 (all sea) and the NIPHM Cashew package (HTTP 404).

## 8. Data-quality notes

* NASA POWER is about 50 km resolution and IMD temperature is 1°. Do not present either as field-scale.
* District names differ across sources (geoBoundaries 2021 vs DES current names). Use `data/reference/district_name_crosswalk.csv`.
* PlantVillage images are lab backgrounds; PlantDoc has severe class imbalance (1–191 images per class). Expect poor field generalisation without Maharashtra images.
* AquaCrop's code is © FAO: non-commercial use is free on request (copyright@fao.org). Check this before any commercial deployment.
* SoilGrids 2.0 has no water-retention layers. The 2017 release (D14b) fills that gap but is an older model. NBSS&LUP data should eventually supersede both.

## 9. Recommended next steps (in order)

1. ~~Authenticate Earth Engine~~: done. Next, build the preprocessing step (apply scale factors and QA masks, then aggregate to district and 8/16-day feature tables), followed by the **water-stress proxy model** (XGBoost/LightGBM + SHAP). It is trainable now with a clearly labelled proxy target such as the root-zone soil-moisture percentile 16/32 days ahead.
2. **Register for ECMWF S2S** (reforecasts) before designing the 16/32-day training set.
3. **Re-export the DES APY reports** with the crop name in each filename, and add 2023-24 onward.
4. **Curate the crop calendar and FAO-56 parameters** for Maharashtra's main crops (soybean, cotton, tur, sugarcane, jowar, gram, wheat, onion), with citations.
5. **Create an AquaCrop project (.PRO)** in the GUI for one crop/district to get a first runnable simulation, then calibrate it with trial data.
6. **Install ML libraries in `.venv`** and build the first pipelines: the plant-disease classifier (data ready) and a rule-based crop-suitability baseline (soil ready).
7. **Send data requests** to NBSS&LUP and the Soil Health Card portal.

## Re-running

```
.venv/Scripts/python scripts/download/download_missing.py   # skips anything already valid
.venv/Scripts/python scripts/audit/final_audit.py            # rescans, revalidates, recomputes readiness
```
