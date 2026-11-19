# GeoCrop Farm Simulator: method, validation and limitations

## What it does

The simulator answers "what if": with this crop, sown on this date, with this water management, what yield and water use would the **last ~10 seasons of real weather** in this district have produced? Up to three scenarios run side by side, for example rainfed vs. "irrigate when needed", or sowing on 20 June vs. 10 July. The output is a distribution across real past seasons (median, 10–90% range, worst and best season), the per-season difference against scenario A, and daily canopy and root-zone water curves for any chosen season.

## Engine

* **FAO AquaCrop 7.3, official Python release.** The SHA-256 checksum is verified against the GitHub release.
* **One documented bug fix.** The engine crashed whenever canopy growth was stressed: a missing argument to `RequiredTimeNew`. The fix is in `simulator/aquacrop/engine_patched/PATCHES.md`, and the original extraction is untouched. It should be reported to FAO.
* **Isolation.** Each request writes AquaCrop input files to an isolated run folder on D: and runs the engine in a separate process. Several seasons are batched per process. A season takes about 0.6 s of engine time; 10 seasons × 2 scenarios take about 15–30 s.

## Inputs (district level)

| Input | Source |
|---|---|
| Tmin/Tmax, reference ET | NASA POWER, FAO-56 Penman–Monteith (district area-weighted) |
| Rain | IMD 0.25° gauge grid. After IMD's last release: IMERG scaled to IMD per district and month (provisional). |
| Soil | 4 horizons (0–30, 30–60, 60–100, 100–200 cm) from SoilGrids 2.0 sand/clay/SOC via Saxton & Rawls (2006): SAT, FC, WP, Ksat. Curve number and REW follow AquaCrop defaults; capillary-rise CRa/CRb use AquaCrop's soil-class relations. |
| Initial soil water | NASA SMAP root-zone relative wetness on the sowing date, applied between WP and FC (50% if no SMAP data) |
| Crop | FAO AquaCrop default crop files, GDD versions, which transfer between climates better. Calibration sites: soybean Patancheru (India); cotton, sunflower and tomato Cordoba (Spain); maize Davis (USA); sorghum Bushland (USA); wheat Valenzano (Italy); potato Lima (Peru). |
| Irrigation | Rainfed; "irrigate when needed" (net irrigation requirement, refill when depletion exceeds X% of RAW); or a fixed schedule (every N days, D mm, from day a to b). Methods: sprinkler, drip (30% wetted), furrow, basin. |

Days without observed weather are filled from district climatology and flagged. A season counts in the statistics only if its **whole crop cycle** had observed weather.

## Validation and checks

* **FAO example:** Cordoba maize. Rainfed gave 1.4 t/ha; irrigated gave 14.5 t/ha using 493 mm. This is plausible for the dry Cordoba summer.
* **Latur soybean, rainfed, sown 25 June, 2015–2024:** the 2015 and 2018 drought years collapse (0.5 and 1.85 t/ha) against about 5 t/ha in wet years. This matches the known Marathwada drought years.
* **"Irrigate when needed":** yields stabilise at 4.9–5.7 t/ha. Irrigation demand runs about 450 mm in drought years and 60–110 mm in wet years.
* **Tests** (`tests/test_simulator.py`): engine day numbering, Ksat ordering, the FAO example round-trip, irrigation never lowering yield, and drought years being worse than wet years.

## Limitations (shown in the UI)

1. **Water-limited attainable yield.** Soil fertility is non-limiting, with no pests or weeds. Real farm yields are usually much lower (Latur soybean is typically about 1 t/ha), so use the simulator to **compare choices**, not to predict a harvest. AquaCrop's fertility-stress setting has no effect with these crop files, because their fertility response is not calibrated, so we do not offer it.
2. **No local calibration.** The crop parameters are not calibrated for Maharashtra varieties. Calibration needs field-trial data from the agricultural universities (SAUs) or AICRP.
3. **District averages.** Weather and soil are district averages; one field can differ.
4. **Leap days.** AquaCrop's internal calendar has no 29 February. This is harmless here, because every climate file starts on the sowing date.

## API

`GET /simulator/crops`, `GET /simulator/district/{id}/soil`, and `POST /simulator/run`, which takes `{district_id, crop, scenarios: [{label, sow_month, sow_day, irrigation: {mode, allowable_depletion_raw_pct, schedule, method}}], detail_year?}`. Results are cached in memory per request body.
