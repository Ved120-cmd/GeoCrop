"""Predict module: leakage rules, saved models, inference output and API. Uses the built artefacts on disk."""
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from geocrop.config import INDEX_DIR, PROCESSED, ROOT
from geocrop.predict import features as F

FEAT = PROCESSED / "predict_features.parquet"
FC = PROCESSED / "predict" / "district_forecast.parquet"
pytestmark = pytest.mark.skipif(not FEAT.exists(), reason="run geocrop.predict.features first")


@pytest.fixture(scope="module")
def feats():
    return pd.read_parquet(FEAT)


def test_satellite_inputs_respect_publication_latency(feats):
    # a composite may only be used once it has been published: age >= latency for every row
    assert feats.ndvi_anom_age_days.min() >= F.LAT["ndvi"]
    assert feats.lst_anom_age_days.min() >= F.LAT["lst"]
    assert feats.esi_z_age_days.min() >= F.LAT["et"]


def test_soil_moisture_now_is_lagged_and_target_is_future(feats):
    sm = pd.read_parquet(INDEX_DIR / "soil_moisture.parquet", columns=["date", "district_id", "sm_percentile"])
    sm["date"] = pd.to_datetime(sm.date)
    s = sm[sm.district_id == 26].set_index("date").sm_percentile
    row = feats[(feats.district_id == 26) & feats.y_pct_32.notna()].iloc[500]
    t = pd.Timestamp(row.issue_date)
    assert row.sm_pct_now == pytest.approx(s.loc[t - pd.Timedelta(days=F.LAT["smap"])])
    assert row.y_pct_16 == pytest.approx(s.loc[t + pd.Timedelta(days=16)])
    assert row.y_pct_32 == pytest.approx(s.loc[t + pd.Timedelta(days=32)])


def test_features_have_no_target_columns():
    for L in F.LEADS:
        assert not any(c.startswith("y_") for c in F.features_for(L))


def test_metrics_use_time_split_and_selection_on_validation():
    m = json.loads((ROOT / "models/water_stress/metrics.json").read_text())
    for L in F.LEADS:
        r = m[f"lead{L}"]
        sel = r["model_selection_on_validation"]
        assert sel["chosen"] == min((k for k in sel["val_mae"] if k.startswith("lgbm")), key=sel["val_mae"].get)
        assert r["predict_delta"] == (sel["chosen"] == "lgbm_delta_l1")
        for f in ("lgbm_point.txt", "lgbm_q10.txt", "lgbm_q90.txt", "lgbm_dry.txt", "xgb_point.json"):
            assert (ROOT / f"models/water_stress/lead{L}/{f}").exists()
        # honest baselines are always reported beside the model
        assert {"lightgbm", "persistence", "climatology"} <= set(r["test_regression"])


@pytest.mark.skipif(not FC.exists(), reason="run geocrop.predict.infer first")
def test_forecast_output_ranges():
    fc = pd.read_parquet(FC)
    assert set(fc.lead_days) == {16, 32} and fc.district_id.nunique() == 36
    assert fc.prob_dry.between(0, 1).all()
    for c in ("sm_pct_median", "sm_pct_p10", "sm_pct_p90"):
        assert fc[c].between(0, 100).all()
    assert (fc.sm_pct_p10 <= fc.sm_pct_p90 + 1e-9).all()
    assert set(fc.dry_risk) <= {"low", "possible", "elevated", "high"}


@pytest.mark.skipif(not FC.exists(), reason="run geocrop.predict.infer first")
def test_predict_api():
    from geocrop.api.main import app
    c = TestClient(app)
    o = c.get("/predict/overview", params={"lead": 32}).json()
    assert o["lead_days"] == 32 and len(o["districts"]) == 36 and "PROXY" in o["value_type"]
    assert c.get("/predict/overview", params={"lead": 7}).status_code == 422
    d = c.get("/predict/district/26").json()
    assert d["district"] == "Pune" and len(d["forecasts"]) == 2 and d["history"]
    assert d["drivers"]["16"]["drivers"] and "label_mr" in d["drivers"]["16"]["drivers"][0]
    assert c.get("/predict/district/999").status_code == 404
