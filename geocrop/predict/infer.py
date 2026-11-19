"""Daily inference: 16/32-day district forecasts with uncertainty, dry-risk probability and SHAP drivers.

Issue date = the latest date whose SMAP input (t-3) exists, never later than today, so every forecast is built
from the same latency rules as in training. Output:
  data/processed/predict/district_forecast.parquet   one row per district x lead
  data/processed/predict/district_drivers.json       top SHAP drivers per district x lead
"""
import json
from datetime import date, timedelta
from functools import lru_cache

import lightgbm as lgb
import numpy as np
import pandas as pd

from geocrop.config import PROCESSED, ROOT
from geocrop.predict import features as F

MODELS = ROOT / "models/water_stress"
OUT = PROCESSED / "predict"


@lru_cache(maxsize=1)
def load_models():
    metrics = json.loads((MODELS / "metrics.json").read_text())
    out = {}
    for L in F.LEADS:
        d = MODELS / f"lead{L}"
        out[L] = dict(point=lgb.Booster(model_file=str(d / "lgbm_point.txt")), q10=lgb.Booster(model_file=str(d / "lgbm_q10.txt")),
                      q90=lgb.Booster(model_file=str(d / "lgbm_q90.txt")), dry=lgb.Booster(model_file=str(d / "lgbm_dry.txt")),
                      delta=bool(metrics[f"lead{L}"].get("predict_delta", False)), feats=metrics[f"lead{L}"]["features"],
                      skill=metrics[f"lead{L}"]["test_regression"], dry_skill=metrics[f"lead{L}"]["test_dry_classification"]["lightgbm"])
    return out, metrics


def issue_date_for(today: date | None = None) -> date:
    sm = pd.read_parquet(PROCESSED / "monitor/indices/soil_moisture.parquet", columns=["date"])
    last = pd.to_datetime(sm.date).max().date()
    today = today or date.today()
    return min(today, last + timedelta(days=F.LAT["smap"]))


def risk_class(p):
    return np.select([p >= 0.6, p >= 0.3, p >= 0.15], ["high", "elevated", "possible"], "low")


def run(today: date | None = None, top_k=5):
    models, metrics = load_models()
    t = pd.Timestamp(issue_date_for(today))
    X = F.build(issue_dates=[t], with_targets=False)
    rows, drivers = [], {}
    for L, m in models.items():
        feats = m["feats"]
        base = X.sm_pct_now.values if m["delta"] else 0.0
        med = np.clip(m["point"].predict(X[feats]) + base, 0, 100)
        lo = np.clip(m["q10"].predict(X[feats]) + base, 0, 100)
        hi = np.clip(m["q90"].predict(X[feats]) + base, 0, 100)
        lo, hi = np.minimum(lo, med), np.maximum(hi, med)
        pdry = m["dry"].predict(X[feats])
        contrib = m["point"].predict(X[feats], pred_contrib=True)
        for i, did in enumerate(X.district_id):
            rows.append(dict(district_id=int(did), lead_days=L, issue_date=t.date().isoformat(), valid_date=(t + pd.Timedelta(days=L)).date().isoformat(),
                             sm_pct_now=float(X.sm_pct_now.iloc[i]) if pd.notna(X.sm_pct_now.iloc[i]) else None,
                             sm_pct_median=round(float(med[i]), 1), sm_pct_p10=round(float(lo[i]), 1), sm_pct_p90=round(float(hi[i]), 1),
                             prob_dry=round(float(pdry[i]), 3), dry_risk=str(risk_class(pdry[i])),
                             ndvi_data_age_days=int(X.ndvi_anom_age_days.iloc[i]) if pd.notna(X.ndvi_anom_age_days.iloc[i]) else None))
            c = pd.Series(contrib[i, :-1], index=feats)
            top = c.abs().sort_values(ascending=False).head(top_k).index
            drivers[f"{int(did)}_{L}"] = dict(
                baseline=round(float(contrib[i, -1]) + (float(X.sm_pct_now.iloc[i]) if m["delta"] else 0.0), 1),
                explains="change from today's percentile" if m["delta"] else "forecast percentile",
                drivers=[dict(feature=f, label=F.FEATURE_LABELS.get(f, f), label_mr=F.FEATURE_LABELS_MR.get(f, f),
                              value=None if pd.isna(X[f].iloc[i]) else round(float(X[f].iloc[i]), 2), effect=round(float(c[f]), 2))
                         for f in top])
    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / "district_forecast.parquet", index=False)
    (OUT / "district_drivers.json").write_text(json.dumps(drivers, ensure_ascii=False), encoding="utf-8")
    return df


if __name__ == "__main__":
    d = run()
    print(d.groupby("lead_days").dry_risk.value_counts().to_dict())
    print(d[d.district_id == 17].to_string())
