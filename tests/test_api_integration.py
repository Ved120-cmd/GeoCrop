"""Integration tests of the Monitor API on the real processed data (skipped if data not built)."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from geocrop.config import INDEX_DIR

pytestmark = pytest.mark.skipif(not (INDEX_DIR / "vegetation.parquet").exists(), reason="indices not built")


@pytest.fixture(scope="module")
def client():
    from geocrop.api.main import app
    return TestClient(app)


def test_districts(client):
    r = client.get("/districts").json()
    assert len(r) == 36 and {"district_id", "district"} <= set(r[0])


def test_series_ndvi(client):
    r = client.get("/monitor/district/24/series", params={"variable": "ndvi", "start": "2024-01-01", "end": "2024-12-31"}).json()
    assert r["units"] == "-" and 20 <= len(r["data"]) <= 23
    vals = [x["mean"] for x in r["data"] if x["mean"] is not None]
    assert all(-0.2 < v < 1 for v in vals)


def test_series_et_includes_provisional_nrt(client):
    r = client.get("/monitor/district/24/series", params={"variable": "et", "start": "2026-01-01"}).json()
    assert r["data"] and all(x["status"] == "provisional" for x in r["data"])


def test_status_has_dates_per_indicator(client):
    r = client.get("/monitor/district/1/status").json()
    assert {"vegetation", "soil_moisture", "spi"} <= set(r["indicators"])
    for v in r["indicators"].values():
        assert "as_of" in v


def test_alerts_shape(client):
    r = client.get("/monitor/alerts").json()
    assert "alerts" in r and r["n_districts"] == len(r["alerts"])


def test_district_stress_nowcast_today(client):
    r = client.get("/monitor/district/36/stress-nowcast").json()
    assert r["value_type"].startswith("MODEL ESTIMATE")
    assert r["meta"]["data_age_days"] <= 7
    kinds = {d.get("kind") for d in r["daily"] if d.get("kind")}
    assert "forecast" in kinds  # days beyond observations come from ECMWF


def test_field_nowcast_validation_errors(client):
    assert client.get("/monitor/nowcast", params={"district_id": 1, "crop": "banana", "sow_date": "2026-06-20"}).status_code == 400
    r = client.get("/monitor/nowcast", params={"district_id": 1, "crop": "chickpea", "sow_date": "2026-10-20"})
    assert r.status_code == 422  # no FAO-56 stage lengths -> refused, not invented


def test_field_nowcast_irrigation_reduces_stress(client):
    p = {"district_id": 1, "crop": "wheat", "sow_date": "2026-10-25", "today": str(date(2026, 11, 13)), "horizon_days": 10}
    dry = client.get("/monitor/nowcast", params=p).json()
    # irrigation ON the start day (the SMAP-initialised state already contains anything before it)
    wet = client.get("/monitor/nowcast", params=p | {"irrigation": "2026-11-13:60"}).json()
    d_dry = [x["depletion_pct"] for x in dry["daily"] if x.get("depletion_pct") is not None][-1]
    d_wet = [x["depletion_pct"] for x in wet["daily"] if x.get("depletion_pct") is not None][-1]
    assert d_wet < d_dry
    assert "NO irrigation assumed" in dry["meta"]["irrigation_assumption"]
