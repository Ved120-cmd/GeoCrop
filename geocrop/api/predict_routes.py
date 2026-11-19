"""Predict API: 16/32-day district water-stress forecasts (proxy target) with uncertainty and SHAP drivers."""
import json
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from geocrop.common.districts import district_table
from geocrop.config import INDEX_DIR, PROCESSED, ROOT

router = APIRouter(prefix="/predict", tags=["predict"])
P = PROCESSED / "predict"
VALUE_TYPE = ("FORECAST of a PROXY: SMAP root-zone soil-moisture percentile (satellite-model product), "
              "not measured crop stress; no weather forecasts used")


def _load():
    f = P / "district_forecast.parquet"
    if not f.exists():
        raise HTTPException(503, "forecasts not generated yet (run geocrop.predict.infer)")
    return pd.read_parquet(f), json.loads((P / "district_drivers.json").read_text(encoding="utf-8"))


def _skill():
    m = json.loads((ROOT / "models/water_stress/metrics.json").read_text())
    out = {"trained_at": m["meta"]["trained_at"], "test_period": "2024-2026"}
    for L in (16, 32):
        r = m[f"lead{L}"]
        out[f"lead{L}"] = {"mae": r["test_regression"]["lightgbm"]["mae"], "mae_persistence": r["test_regression"]["persistence"]["mae"],
                           "skill_vs_persistence": r["test_regression"]["lightgbm"]["skill_vs_persistence"],
                           "interval_coverage": r["test_interval_10_90"]["coverage"],
                           "dry_brier_skill": r["test_dry_classification"]["lightgbm"]["brier_skill_vs_climatology"],
                           "dry_auc": r["test_dry_classification"]["lightgbm"]["auc"], "dry_precision": r["test_dry_classification"]["lightgbm"]["precision"],
                           "dry_recall": r["test_dry_classification"]["lightgbm"]["recall"],
                           "worse_than_persistence_in_2026": r["test_by_year"].get("2026", {}).get("lightgbm_mae", 0) > r["test_by_year"].get("2026", {}).get("persistence_mae", 1e9)}
    return out


@router.get("/overview")
def overview(lead: int = Query(16, description="16 or 32")):
    if lead not in (16, 32):
        raise HTTPException(422, "lead must be 16 or 32")
    df, _ = _load()
    d = df[df.lead_days == lead].merge(district_table(), on="district_id")
    return {"value_type": VALUE_TYPE, "lead_days": lead, "issue_date": d.issue_date.iloc[0], "valid_date": d.valid_date.iloc[0],
            "skill": _skill(), "districts": json.loads(d.to_json(orient="records"))}


@router.get("/district/{district_id}")
def district(district_id: int, history_days: int = Query(120, ge=30, le=400)):
    df, drivers = _load()
    d = df[df.district_id == district_id]
    if d.empty:
        raise HTTPException(404, "unknown district")
    sm = pd.read_parquet(INDEX_DIR / "soil_moisture.parquet", columns=["date", "district_id", "sm_percentile"], filters=[("district_id", "==", district_id)])
    sm["date"] = pd.to_datetime(sm.date)
    sm = sm[sm.date >= sm.date.max() - pd.Timedelta(days=history_days)]
    sm["date"] = sm.date.dt.strftime("%Y-%m-%d")
    name = district_table().set_index("district_id").loc[district_id, "district"]
    return {"value_type": VALUE_TYPE, "district_id": district_id, "district": name,
            "forecasts": json.loads(d.to_json(orient="records")),
            "drivers": {str(L): drivers.get(f"{district_id}_{L}") for L in (16, 32)},
            "history": json.loads(sm[["date", "sm_percentile"]].to_json(orient="records")), "skill": _skill()}


@router.get("/model-card")
def model_card():
    f = ROOT / "models/water_stress/model_card.md"
    return {"markdown": f.read_text(encoding="utf-8") if f.exists() else None, "skill": _skill()}
