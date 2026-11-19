# GeoCrop Monitor: method, validation and limitations

Status: backend prototype (data pipeline, indices, nowcast, API). No frontend yet.
Scope: Maharashtra, 36 districts, 2015 to today. Everything is district-level unless stated otherwise.

## 1. What Monitor shows, and how each value is produced

| Output | Source | Nature of the value | Update lag |
|---|---|---|---|
| NDVI / EVI | MODIS MOD13Q1, 250 m, 16-day | satellite observation | ~2–4 weeks |
| Land surface temperature, day/night | MODIS MOD11A2, 1 km, 8-day | satellite observation | ~1–2 weeks |
| ET, PET, ET/PET | MOD16A2GF (gap-filled, yearly release); MOD16A2 near-real-time, **provisional** | satellite-model product | ~3 weeks |
| Root-zone / surface soil moisture | SMAP L4 v008, daily mean of 3-hourly | model–satellite assimilation | ~2–3 days |
| Rainfall | IMD 0.25° gauge grid (reference); IMERG V07 (recent days **provisional**); CHIRPS (cross-check) | observation / satellite estimate | 1 day to weeks |
| Weather, reference ET | NASA POWER + FAO-56 Penman–Monteith | reanalysis-based estimate | ~3 days (radiation ~10) |
| Forecast rain and reference ET, 0–10 days | ECMWF IFS open data | **forecast** | real time |
| VCI / TCI / VHI | Kogan (1995) on NDVI and LST | statistical index | follows NDVI/LST |
| SMAP percentile, ET/PET anomaly | baseline 2015–2024 | statistical index | follows source |
| SPI-1 / SPI-3 | IMD monthly rain, gamma fit, baseline 1991–2020 | statistical index | monthly |
| Monsoon departure | IMD cumulative rain from 1 June vs 1991–2020 normal; IMD categories | statistical index | daily |
| Today's water stress | FAO-56 root-zone water balance started from SMAP | **model estimate** | daily |

Pixel handling:
- Satellite pixels failing quality flags are dropped. A gap is never written as 0.
- District statistics are the mean, median, 10th and 90th percentiles and the valid-pixel fraction. They are computed for all land and for cropland, where cropland is MODIS MCD12Q1 IGBP classes 12/14: broad land cover, not crop type.
- District-dates with less than 30% valid pixels are kept but flagged `low_confidence` and excluded from alerts.

## 2. Today's stress (nowcast)

1. Take the SMAP root-zone moisture on the latest SMAP day (usually 2–3 days old). Rescale it to the soil's available water with SMAP's own district climatology (5th/95th percentile), so SMAP's model soil is never mixed with SoilGrids values.
2. Run the FAO-56 daily balance forward:
   - rain: IMD, otherwise IMERG, otherwise the ECMWF forecast;
   - reference ET: POWER Penman–Monteith, otherwise the ECMWF forecast.
3. Report depletion, Ks, a stress class (none / mild / moderate / severe), and the days until stress over the 10-day forecast.

Two modes:
- **District (landscape):** water use = observed MODIS ET/PET. This is the validated configuration.
- **Field:** crop Kc, stage lengths, rooting depth and p from FAO-56 Tables 11, 12 and 22, with sources in `data/reference/fao56_crop_params.SOURCES.md`. Inputs are the crop, sowing date and optional irrigation events. With no irrigation reported, stress for irrigated fields is overstated, and the output says so.

Soil water-holding capacity uses the Saxton & Rawls (2006) pedotransfer equations on SoilGrids 2.0 sand, clay and organic carbon: 127–143 mm per metre across districts. The SoilGrids 2017 water layers were rejected as the default. Correctly read as *available* water capacity, they give only 22–77 mm/m, lowest in the Vidarbha black-soil districts, which is implausible. Both remain global-model estimates until NBSS&LUP or Soil Health Card data are available.

## 3. Validation

### 3.1 Indices against known events

| Event | Result |
|---|---|
| 2018 Marathwada drought (6 districts) | Oct–Nov VHI 2.6 (extreme); SPI-3 (Sep) −1.49; SMAP root-zone 5th percentile in October |
| 2015 drought | VHI 17.8 (severe); SPI-3 −1.44; SMAP 22nd percentile |
| Kolhapur floods, August 2019 | monsoon rain +83% above normal by 15 Aug ("large excess") |
| Wet September 2021 | SPI-3 +1.92 |
| Deficient 2023 monsoon | SMAP 21st percentile in October |
| Rain sources | IMD vs CHIRPS monthly district rain: r = 0.935, CHIRPS −3.7% |
| Temperature sources | POWER vs IMD Tmax: r = 0.925, bias −0.2 °C |
| Reference ET | FAO-56 worked examples reproduced (Ra example 8; ETo example 18 within 0.2 mm/day) |

### 3.2 Water-balance nowcast against SMAP (`scripts/validation/validate_nowcast.py`)

Setup: 36 districts × 40 random start dates (June–February, 2016–2024), observed weather, compared with SMAP-implied depletion. This is a consistency check against a model product, **not field truth**.

| Configuration | Skill vs persistence, 3 d | 7 d | 14 d |
|---|---|---|---|
| Kc = 1 everywhere | −0.53 | −0.32 | −0.10 |
| Landscape Kc = MODIS ET/PET (district mode) | −0.09 | **+0.10** | **+0.25** |

With Kc = 1 the model dries the soil about 2.9× too fast in Nov–Feb, because fallow land transpires little. With observed ET/PET, dry-period error falls from 0.042 to 0.013.

Remaining weakness: heavy-rain weeks (June, August). The model refills the soil faster than SMAP because there is no surface-runoff term.

### 3.3 First live run (13 Nov 2026)

Freshness on the run date:

| Source | Latest data | Status |
|---|---|---|
| NDVI | composite from 16 Oct | final |
| LST | composite from 1 Nov | final |
| ET (MOD16A2) | composite from 24 Oct | provisional |
| SMAP | 10 Nov | final |
| IMERG | 11 Nov | provisional |
| ECMWF | run of 13 Nov, 10 days | forecast |

What the data show, all provisional because IMD's 2026 gridded rain is not yet published:

| Indicator | 2026 value | Comparison |
|---|---|---|
| Jun–Sep rain (IMERG) | 891 mm district mean | lowest of 2015–2026 (2015: 924 mm) |
| October rain | 9 mm | also the lowest |
| Monsoon departure (IMERG scaled to IMD) | 27 of 35 districts deficient, state mean −29% | 2015: −26%, 2018: −12% |
| SPI-3 for October | "extremely dry" in 25 districts | |
| SMAP root-zone moisture, Oct–early Nov | ≈ 0.297 statewide | equal to the 2018 drought year (0.300) |

33 districts are at or below the 20th percentile for the season.

The update job also has these behaviours:
- **Rain after IMD's last published day** is IMERG linearly scaled to IMD, by district and calendar month (2015–2024 ratio), flagged `provisional`.
- **Gap filling:** days between the last observation and the first forecast day (e.g. the POWER lag) are filled with district day-of-year climatology (median rain, mean ETo) and labelled `gap-filled`.
- **Irrigation:** user irrigation is always applied.

District IDs are alphabetical by current official name (1 = Ahilyanagar … 24 = Palghar, 26 = Pune … 36 = Yavatmal). Use `/districts`.

## 4. Known limitations
- **Short baseline.** The satellite baseline is 10 years (2015–2024), so the worst year sits at or near the baseline minimum and VCI/VHI extremes are exaggerated, e.g. VHI ≈ 0 in 2018. SPI uses the full 30-year IMD baseline.
- **Coarse resolution.** SMAP is about 9 km, rainfall 0.1–0.25° and POWER about 50 km. None of these is field-scale. Field-scale monitoring needs Sentinel-1/2 on demand (not yet built).
- **Provisional data.** IMERG near-real-time and MOD16A2 values are replaced by final versions when available; every row carries `status`.
- **Model simplifications.** No runoff or capillary rise; FAO-56 stage lengths are not Maharashtra-specific; Kc ini uses FAO-56 crop-group values.
- **Rainfed assumption.** Field-mode stress assumes rainfed conditions unless irrigation is entered.
- **Day boundaries.** Days are UTC for ECMWF/IMERG and 08:30 IST for IMD; this is not harmonised.

## 5. Running

```
.venv/Scripts/python -m geocrop.monitor.update                      # daily incremental update
.venv/Scripts/uvicorn geocrop.api.main:app --port 8000              # API, docs at http://localhost:8000/docs
.venv/Scripts/python -m pytest tests -p no:cacheprovider            # tests
.venv/Scripts/python scripts/validation/validate_nowcast.py landscape
```
