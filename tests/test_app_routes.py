"""Integration tests for the web-app routes (geo, overview, soil, profiles). Needs the local PostgreSQL running."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from geocrop.api.main import app
    return TestClient(app, headers={"X-GeoCrop-Client": "web"})


def _db_up():
    try:
        from geocrop.db import engine
        with engine.connect():
            return True
    except Exception:
        return False


def test_geo(client):
    g = client.get("/geo/districts").json()
    assert len(g["features"]) == 36 and {"district_id", "region"} <= set(g["features"][0]["properties"])
    regs = {r["key"]: r for r in client.get("/geo/regions").json()}
    assert sorted(regs["Khandesh"]["district_ids"]) and len(regs["Khandesh"]["district_ids"]) == 3
    assert sum(len(r["district_ids"]) for k, r in regs.items() if k != "Khandesh") == 36
    assert client.get("/geo/locate", params={"lat": 18.52, "lon": 73.85}).json()["district"] == "Pune"
    assert client.get("/geo/locate", params={"lat": 21.0, "lon": 72.6}).json()["inside_maharashtra"] is False


def test_overview_cached(client):
    a = client.get("/monitor/overview").json()
    assert len(a["districts"]) == 36
    assert client.get("/monitor/overview").json() == a  # served from cache, identical


def test_soil(client):
    s = client.get("/soil/district/26").json()
    assert "ESTIMATE" in s["value_type"] and len(s["texture"]) == 6
    ph = [p for p in s["properties"] if p["property"] == "phh2o" and p["depth"] == "0-5cm"][0]
    assert 4 < ph["mean"] < 9.5


@pytest.mark.skipif(not _db_up(), reason="PostgreSQL not running")
def test_profile_roundtrip(client):
    body = {"name": "pytest farmer", "language": "en", "farm": {"district_id": 26, "area_unit": "acre", "irrigation_source": "borewell",
            "soil_type_reported": "black", "crops": [{"crop": "wheat", "season": "rabi", "sowing_date": "2026-10-28"}]}}
    p = client.post("/profiles", json=body).json()
    try:
        fid = p["farms"][0]["id"]
        assert client.post(f"/farms/{fid}/irrigation", json={"date": "2026-11-10", "amount_mm": 40}).status_code == 201
        assert client.post(f"/farms/{fid}/irrigation", json={"date": "2026-11-10", "amount_mm": 999}).status_code == 422
        assert client.post("/profiles", json={**body, "farm": {**body["farm"], "lat": 40.0}}).status_code == 422
        assert client.post("/profiles", json={**body, "farm": {**body["farm"], "crops": [{"crop": "banana", "season": "rabi"}]}}).status_code == 422
        n = client.get(f"/farms/{fid}/nowcast").json()
        assert n["available"] and n["meta"]["irrigation_assumption"].startswith("irrigation events")
    finally:
        assert client.delete(f"/profiles/{p['id']}").status_code == 204
    assert client.get(f"/profiles/{p['id']}").status_code == 404
