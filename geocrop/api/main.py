"""GeoCrop Monitor API (FastAPI). Run: uvicorn geocrop.api.main:app --port 8000   (docs at /docs)

Every response carries data dates, provisional/final status and the nature of the value
(observed satellite/gauge data, statistical index, or model ESTIMATE) so the UI never presents an estimate
as a measurement.
"""
from datetime import date
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query

from geocrop.common.districts import district_table
from geocrop.config import INDEX_DIR, SERIES_DIR
from geocrop.monitor import nowcast as nc
from geocrop.monitor.products import PRODUCTS

app = FastAPI(title="GeoCrop Monitor API", version="0.1.0",
                description="District-level crop monitoring for Maharashtra: satellite observations, anomalies, drought indices "
                            "and an FAO-56 water-balance stress ESTIMATE. Soil properties are global-model estimates.")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

VAR_PRODUCT = {v: p for p, (_, _, vs) in PRODUCTS.items() for v in vs if p != "MOD16A2"}


def _clean(df: pd.DataFrame):
    """DataFrame -> JSON-safe records (dates as YYYY-MM-DD, NaN as null, numpy scalars as Python)."""
    import json
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%Y-%m-%d")
    return json.loads(df.to_json(orient="records", double_precision=6))


@lru_cache(maxsize=16)
def _index(name):
    p = INDEX_DIR / f"{name}.parquet"
    if not p.exists():
        raise HTTPException(503, f"index '{name}' not built yet")
    df = pd.read_parquet(p)
    for c in ("date", "month"):
        if c in df:
            df[c] = pd.to_datetime(df[c])
    return df


def _district(district_id):
    t = district_table()
    if district_id not in set(t.district_id):
        raise HTTPException(404, "unknown district_id (see /districts)")
    return t.set_index("district_id").loc[district_id, "district"]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/districts")
def districts():
    return _clean(district_table())


@app.get("/monitor/variables")
def variables():
    return [{"variable": v, "product": p, "units": PRODUCTS[p][2][v]} for v, p in VAR_PRODUCT.items()]


@app.get("/monitor/district/{district_id}/series")
def series(district_id: int, variable: str, mask: str = Query("cropland", pattern="^(cropland|all)$"),
           start: Optional[date] = None, end: Optional[date] = None):
    name = _district(district_id)
    if variable not in VAR_PRODUCT:
        raise HTTPException(400, f"unknown variable; choose from {sorted(VAR_PRODUCT)}")
    prods = [VAR_PRODUCT[variable]] + (["MOD16A2"] if VAR_PRODUCT[variable] == "MOD16A2GF" and (SERIES_DIR / "MOD16A2").exists() else [])
    frames = []
    for p in prods:
        df = pd.read_parquet(SERIES_DIR / p, filters=[("district_id", "==", district_id), ("variable", "==", variable), ("mask", "==", mask)])
        frames.append(df)
    df = pd.concat(frames).sort_values("date").drop_duplicates("date", keep="first")
    df["date"] = pd.to_datetime(df.date)
    if start: df = df[df.date >= pd.Timestamp(start)]
    if end: df = df[df.date <= pd.Timestamp(end)]
    return {"district": name, "variable": variable, "units": PRODUCTS[VAR_PRODUCT[variable]][2][variable], "mask": mask,
            "value_type": "satellite observation (district statistic)",
            "data": _clean(df[["date", "mean", "median", "p10", "p90", "valid_frac", "status"]])}


@app.get("/monitor/district/{district_id}/status")
def status(district_id: int):
    """Latest value of every index for one district, each with its own date (sources update at different lags)."""
    name = _district(district_id)
    out = {"district": name, "district_id": district_id, "indicators": {}}
    specs = {"vegetation": ["vhi", "vhi_class", "vci", "tci", "ndvi", "ndvi_pct_normal"],
             "soil_moisture": ["sm_percentile", "sm_class", "sm_rootzone"],
             "evaporative_stress": ["esi_z", "et_pet_ratio"], "spi": ["spi_1", "spi_3", "spi_class"],
             "monsoon_departure": ["departure_pct", "departure_class", "monsoon_cum_mm", "monsoon_normal_mm"]}
    for k, cols in specs.items():
        try:
            df = _index(k)
        except HTTPException:
            continue
        tcol = "month" if "month" in df else "date"
        d = df[df.district_id == district_id]
        if "low_confidence" in d:
            d = d[~d.low_confidence.astype(bool)]
        d = d.dropna(subset=[cols[0]])
        if d.empty:
            continue
        r = d.sort_values(tcol).iloc[-1]
        out["indicators"][k] = {"as_of": r[tcol].strftime("%Y-%m-%d"), "status": r.get("status", "final"),
                                **{c: (None if pd.isna(r[c]) else (r[c].item() if hasattr(r[c], "item") else r[c])) for c in cols}}
    return out


@app.get("/monitor/alerts")
def alerts(vhi_below: float = 40, sm_percentile_below: float = 20, spi3_below: float = -1.0, esi_z_below: float = -1.0):
    """Districts whose LATEST high-confidence value crosses a threshold (thresholds adjustable)."""
    res = []
    for did in district_table().district_id:
        s = status(int(did))["indicators"]
        flags = []
        v = s.get("vegetation", {}).get("vhi")
        if v is not None and v < vhi_below: flags.append(f"VHI {v:.0f} < {vhi_below:g} ({s['vegetation']['vhi_class']}, {s['vegetation']['as_of']})")
        v = s.get("soil_moisture", {}).get("sm_percentile")
        if v is not None and v < sm_percentile_below: flags.append(f"root-zone soil moisture at {v:.0f}th percentile ({s['soil_moisture']['as_of']})")
        v = s.get("spi", {}).get("spi_3")
        if v is not None and v < spi3_below: flags.append(f"SPI-3 {v:.2f} ({s['spi']['spi_class']}, month {s['spi']['as_of'][:7]})")
        v = s.get("evaporative_stress", {}).get("esi_z")
        if v is not None and v < esi_z_below: flags.append(f"ET/PET anomaly z={v:.2f} ({s['evaporative_stress']['as_of']})")
        if flags:
            res.append({"district_id": int(did), "district": district_table().set_index('district_id').loc[did, 'district'], "flags": flags})
    return {"thresholds": dict(vhi_below=vhi_below, sm_percentile_below=sm_percentile_below, spi3_below=spi3_below, esi_z_below=esi_z_below),
            "n_districts": len(res), "alerts": res}


@app.get("/monitor/district/{district_id}/stress-nowcast")
def district_stress(district_id: int, today: Optional[date] = None, horizon_days: int = Query(10, ge=0, le=10)):
    """District landscape water-stress ESTIMATE for today (+ forecast days). No crop input needed."""
    _district(district_id)
    r = nc.district_stress_nowcast(district_id, today or date.today(), horizon_days)
    return {"value_type": "MODEL ESTIMATE (FAO-56 balance, SMAP-initialised, MODIS ET/PET landscape coefficient)",
            "meta": r.meta, "daily": _clean(r.daily)}


@app.get("/monitor/nowcast")
def nowcast(district_id: int, crop: str, sow_date: date, today: Optional[date] = None, horizon_days: int = Query(10, ge=0, le=10),
            irrigation: Optional[str] = Query(None, description="comma list of YYYY-MM-DD:mm, e.g. 2026-11-05:40"),
            taw_source: str = Query("saxton_rawls", pattern="^(saxton_rawls|soilgrids2017)$")):
    """ESTIMATED root-zone water stress today and over the forecast horizon (FAO-56 water balance from SMAP)."""
    _district(district_id)
    if crop not in nc.crop_table().index:
        raise HTTPException(400, f"crop must be one of {list(nc.crop_table().index)}")
    irr = {}
    if irrigation:
        for item in irrigation.split(","):
            d, mm = item.split(":"); irr[date.fromisoformat(d.strip())] = float(mm)
    try:
        r = nc.nowcast(district_id, crop, sow_date, today or date.today(), irrigation=irr, horizon_days=horizon_days, taw_source=taw_source)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"value_type": "MODEL ESTIMATE (FAO-56 water balance initialised from SMAP; not a measurement)",
            "meta": r.meta, "daily": _clean(r.daily)}


from geocrop.api.app_routes import router as _app_router  # noqa: E402

app.include_router(_app_router)

from geocrop.api.simulator_routes import router as _sim_router  # noqa: E402

app.include_router(_sim_router)

from geocrop.api.predict_routes import router as _pred_router  # noqa: E402

app.include_router(_pred_router)

from geocrop.api.doctor_routes import router as _doc_router  # noqa: E402

app.include_router(_doc_router)

from geocrop.api.advisor_routes import router as _adv_router  # noqa: E402

app.include_router(_adv_router)
