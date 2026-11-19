# Model card: GeoCrop water-stress forecasts (16 and 32 days)

*Generated from `metrics.json`; trained 2026-11-19T11:28:00+00:00; training-data hash `7549b8146d8221e3`.*

## What it predicts
* **Target (proxy):** SMAP L4 root-zone soil-moisture percentile (vs 2015-2024, same time of year) at issue date + lead.
* **Nature:** PROXY for crop water stress (model-assimilated satellite soil moisture), not measured crop stress.
* **Dry:** percentile ≤ 20.0. Outputs are the median, the 10–90% range, and the probability of dry conditions.
* **Unit:** district (36 districts of Maharashtra). These are not field-level forecasts.

## Inputs and leakage control
* No weather forecasts used (ECMWF reforecasts unavailable): only information published by the issue date + climatology.
* **Publication delays (days) applied at every issue date:** smap 3, rain 1, power 3, ndvi 32, lst 16, et 24.
* **Climatology known in advance:** normal rain for the coming window and the time of year. Static inputs: district soil water capacity and region.
* **Time split:** train 2015–2021, validation 2022–2023 (model choice and early stopping), test 2024–2026, used once. The deployed models were trained on 2015–2023 and are exactly the ones evaluated.

## Models
* **LightGBM point forecast:** the formulation was chosen on validation years only (L2, L1, or L1 on change-from-today).
* **Range and dry risk:** LightGBM quantile models (p10, p90) and a LightGBM dry classifier.
* **XGBoost:** the same formulation, kept as a required baseline. Explanations are TreeSHAP from LightGBM's native `pred_contrib`.
* **Library versions:** {'lightgbm': '4.5.0', 'xgboost': '2.1.3'}.

## 16-day forecast: held-out test results (2024–2026, n = 12420)
Chosen on validation: **lgbm_delta_l1** (validation MAE {'lgbm_l2': 14.516, 'lgbm_l1': 14.466, 'lgbm_delta_l1': 14.052, 'persistence': 14.94}).

### Where will the percentile be? (point forecast)
| Method | MAE (pct points) | RMSE | Skill vs persistence |
|---|---|---|---|
| persistence | 13.51 | 20.13 | 0.0 |
| climatology | 20.37 | 25.11 | -0.508 |
| damped_persistence | 13.3 | 18.63 | 0.015 |
| xgboost | 12.62 | 18.79 | 0.066 |
| lightgbm | 12.59 | 18.78 | 0.068 |

**10–90% range:** coverage 0.808 (nominal 0.80), mean width 38.8 percentile points.

### Will it be dry? (≤ 20th percentile)
| Method | Brier | Brier skill vs climatology | AUC | Precision | Recall |
|---|---|---|---|---|---|
| lightgbm | 0.0604 | 0.482 | 0.944 | 0.884 | 0.387 |
| persistence (dry now -> dry later) | 0.078 | 0.331 | 0.784 | 0.711 | 0.602 |
| climatology | 0.1166 | 0.0 | 0.5 | 0.0 | 0.0 |

### By season (LightGBM vs persistence MAE)
* dry season (Feb-May): 12.6 vs 13.02 (n = 4320)
* monsoon (Jun-Sep): 18.68 vs 20.23 (n = 4392)
* post-monsoon (Oct-Jan): 5.36 vs 6.11 (n = 3708)

### By year (LightGBM vs persistence MAE)
* 2024: 11.87 vs 13.01 (n = 4392)
* 2025: 14.06 vs 15.6 (n = 4392)
* 2026: 11.69 vs 11.58 (n = 3636)

### Most influential inputs (mean |SHAP| on the test years)
sm_pct_now (2.809), doy_cos (1.19), sm_change_14d (0.999), sm_pct_lag7 (0.605), normal_rain_next16d (0.498), doy_sin (0.484), rain_7d (0.364), sm_pct_lag30 (0.32)

## 32-day forecast: held-out test results (2024–2026, n = 12240)
Chosen on validation: **lgbm_l1** (validation MAE {'lgbm_l2': 17.139, 'lgbm_l1': 17.03, 'lgbm_delta_l1': 17.33, 'persistence': 18.767}).

### Where will the percentile be? (point forecast)
| Method | MAE (pct points) | RMSE | Skill vs persistence |
|---|---|---|---|
| persistence | 17.09 | 24.05 | 0.0 |
| climatology | 20.53 | 25.29 | -0.201 |
| damped_persistence | 16.0 | 21.59 | 0.064 |
| xgboost | 16.58 | 22.25 | 0.03 |
| lightgbm | 16.47 | 22.11 | 0.036 |

**10–90% range:** coverage 0.78 (nominal 0.80), mean width 54.0 percentile points.

### Will it be dry? (≤ 20th percentile)
| Method | Brier | Brier skill vs climatology | AUC | Precision | Recall |
|---|---|---|---|---|---|
| lightgbm | 0.0749 | 0.365 | 0.888 | 0.784 | 0.274 |
| persistence (dry now -> dry later) | 0.0919 | 0.222 | 0.731 | 0.674 | 0.496 |
| climatology | 0.118 | 0.0 | 0.5 | 0.0 | 0.0 |

### By season (LightGBM vs persistence MAE)
* dry season (Feb-May): 18.86 vs 19.09 (n = 4320)
* monsoon (Jun-Sep): 21.79 vs 22.6 (n = 4392)
* post-monsoon (Oct-Jan): 6.93 vs 7.8 (n = 3528)

### By year (LightGBM vs persistence MAE)
* 2024: 13.68 vs 15.53 (n = 4392)
* 2025: 17.61 vs 20.38 (n = 4392)
* 2026: 18.58 vs 14.9 (n = 3456)

### Most influential inputs (mean |SHAP| on the test years)
sm_pct_now (7.763), doy_cos (2.228), sm_pct_lag7 (1.701), sm_pct_lag14 (1.255), sm_pct_lag30 (1.22), doy_sin (1.059), rain_7d (0.812), vhi (0.709)

## Honest assessment
* **Dry-risk probability is the useful product.** It beats both persistence and climatology clearly at 16 days, and less so at 32 days.
* **Point forecasts are only slightly better than assuming no change.** At 32 days, simple damped persistence is competitive. In the persistent 2026 drought the models expected some recovery that did not happen, and were worse than persistence.
* **Skill is limited without forecasts.** No weather forecasts are used, so rain in the coming weeks cannot be anticipated. ECMWF reforecasts would be needed to add forecast weather without leakage.
* **The target is a proxy.** SMAP soil moisture is a model-assimilated satellite product at about 9 km. It is not measured crop stress.
* **Effective sample size is smaller than the row count.** Issue dates every 3 days are autocorrelated, and neighbouring districts are spatially correlated.

## Intended use
Early warning of dry soil conditions at district level, to prompt checking fields and planning irrigation. It is not a yield forecast, and it is not for field-level decisions on its own.
