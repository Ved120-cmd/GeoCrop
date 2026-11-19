# Predict: 16- and 32-day dry-soil early warning

**What it forecasts:** for each of Maharashtra's 36 districts, where root-zone soil moisture will sit 16 and 32 days from the issue date. It is expressed as a percentile against 2015–2024 for the same time of year.

**Outputs:**
- the median forecast;
- a 10–90% likely range;
- the **probability of dry soil** (percentile ≤ 20).

**What it is not:** the target is a **proxy**. It is SMAP L4 root-zone soil moisture, a satellite and land-model product, not measured crop stress. Forecasts are at district level, not field level.

Full metrics: [`models/water_stress/model_card.md`](../models/water_stress/model_card.md), generated from `metrics.json`.

## Pipeline

| Step | Code | Output |
|---|---|---|
| Features + targets | `geocrop/predict/features.py` | `data/processed/predict_features.parquet` (one row per district every 3 days, 2015 → now) |
| Train + evaluate | `geocrop/predict/train.py` | `models/water_stress/lead{16,32}/` (LightGBM point, q10, q90, dry; XGBoost baseline), `metrics.json`, `model_card.md` |
| Daily forecast | `geocrop/predict/infer.py` (also the `predict_forecast` step of `geocrop.monitor.update`) | `data/processed/predict/district_forecast.parquet`, `district_drivers.json` |
| API | `geocrop/api/predict_routes.py` | `GET /predict/overview?lead=16\|32`, `GET /predict/district/{id}`, `GET /predict/model-card` |
| Web page | `frontend/src/pages/PredictPage.tsx` | `/predict`, `/predict/district/:id` |

## Leakage control

Every input uses only data that had actually been **published** by the issue date. These publication delays (in days) are applied: SMAP 3, rain 1, POWER weather 3, NDVI/VHI 32, LST 16, ET/PET 24. `tests/test_predict.py` checks them.

The only forward-looking inputs are climatology: the normal rain for the coming window and the time of year.

**No weather forecasts are used.** Training with them would need ECMWF reforecasts for the past, which require an account. As a result, a big rain event in the coming weeks cannot be anticipated.

**Time split:**
- train 2015–2021;
- validation 2022–2023, for model choice and early stopping only;
- test 2024–2026, used once.

The deployed models are exactly the ones evaluated: refit on 2015–2023 with the iteration counts fixed on validation.

## Honest results (test 2024–2026)

| | 16 days | 32 days |
|---|---|---|
| Point-forecast MAE (model / "no change") | 12.6 / 13.5 percentile points (+7%) | 16.5 / 17.1 (+4%); damped persistence is better (16.0) |
| 10–90% range coverage | 81% | 78% |
| Dry-risk Brier skill vs normal-year odds | +0.48 | +0.37 |
| Dry-risk AUC / precision / recall | 0.94 / 0.88 / 0.39 | 0.89 / 0.78 / – |
| 2026 drought year | slightly worse than "no change" | clearly worse than "no change" |

**What to trust:**
- **The dry-risk probability is the useful product.** When it says "high", soil was usually dry.
- **It misses many dry spells:** recall is low.
- **The exact percentile is only marginally better than assuming no change,** especially at 32 days. In the persistent 2026 drought the model expected a recovery that never came.
- The page states all of this in a "How reliable is this?" card.

**Explanations:** the five largest TreeSHAP contributions per district and lead, from LightGBM `pred_contrib`, with English/Marathi labels. For the 16-day model they explain the *change from today's percentile*; for the 32-day model, the percentile itself.

## Run

```bash
.venv/Scripts/python -m geocrop.predict.features   # rebuild training table
.venv/Scripts/python -m geocrop.predict.train      # retrain + metrics + model card (stop preview servers first: memory)
.venv/Scripts/python -m geocrop.predict.infer      # today's forecast (also run by the daily update)
```

## Improving it

1. Add ECMWF extended-range reforecasts. This is the main source of skill beyond persistence.
2. Validate the target against ground truth: IMD/ICRISAT soil-moisture stations, crop-cutting yields, drought declarations.
3. Calibrate the dry probabilities (isotonic regression on validation) and tune the classifier threshold for recall.
4. Retrain each year as new seasons arrive.
