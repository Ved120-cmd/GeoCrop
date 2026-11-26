"""Routes used by the web app: geography, Maharashtra overview, soil summary, crop options, farmer profiles."""
import json
import uuid
from datetime import date
from functools import lru_cache
from typing import Literal, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from geocrop.common.districts import district_table, districts
from geocrop.config import NOWCAST_DIR, PROCESSED, REFERENCE
from geocrop.db import CropPlanting, Farm, Farmer, IrrigationEvent, SessionLocal
from geocrop.monitor import nowcast as nc

router = APIRouter()

# ------------------------------------------------------------------ geography
@lru_cache(maxsize=1)
def _regions():
    r = pd.read_csv(REFERENCE / "regions.csv")
    t = district_table()
    m = t.merge(r, on="district", how="left")
    if m.region.isna().any():
        raise RuntimeError(f"regions.csv missing {m[m.region.isna()].district.tolist()}")
    return m


@router.get("/geo/districts", tags=["geo"])
def geo_districts():
    """Simplified district polygons (GeoJSON) with ids, names and regions. Boundaries: geoBoundaries 2021 (ODbL)."""
    return _geojson()


@lru_cache(maxsize=1)
def _geojson():
    g = districts().merge(_regions()[["district_id", "division", "region", "region_mr", "subregion"]], on="district_id")
    g["geometry"] = g.geometry.simplify(0.004, preserve_topology=True)
    g["subregion"] = g.subregion.fillna("")
    return json.loads(g.drop(columns=["gb_name"]).to_json())


@router.get("/geo/regions", tags=["geo"])
def geo_regions():
    r = _regions()
    out = [{"key": k, "name": k, "name_mr": g.region_mr.iloc[0], "district_ids": g.district_id.astype(int).tolist()}
           for k, g in r.groupby("region", sort=False)]
    kh = r[r.subregion == "Khandesh"]
    out.append({"key": "Khandesh", "name": "Khandesh", "name_mr": "खानदेश", "district_ids": kh.district_id.astype(int).tolist(),
                "note": "Cultural region within North Maharashtra (Dhule, Jalgaon, Nandurbar)"})
    return out


@router.get("/geo/locate", tags=["geo"])
def geo_locate(lat: float, lon: float):
    """Which district contains this point (to check a farm pin against the chosen district)."""
    from shapely.geometry import Point
    g = districts()
    hit = g[g.contains(Point(lon, lat))]
    if hit.empty:
        return {"inside_maharashtra": False, "district_id": None, "district": None}
    return {"inside_maharashtra": True, "district_id": int(hit.district_id.iloc[0]), "district": hit.district.iloc[0]}


# ------------------------------------------------------------------ Maharashtra overview (one request for the map)
_OV_CACHE: dict = {}


def _data_version():
    from geocrop.config import INDEX_DIR
    files = list(INDEX_DIR.glob("*.parquet")) + list(NOWCAST_DIR.glob("*.parquet"))
    return tuple(sorted((f.name, f.stat().st_mtime_ns) for f in files))


@router.get("/monitor/overview", tags=["monitor"])
def overview():
    """Latest value of every indicator for all 36 districts + today's stress estimate (precomputed daily).
    Cached in memory until any index / nowcast file changes (i.e. after the daily update)."""
    v = _data_version()
    if _OV_CACHE.get("v") != v:
        from geocrop.api import main as _m
        _m._index.cache_clear()
        _OV_CACHE.update(v=v, data=_overview_build())
    return _OV_CACHE["data"]


def _overview_build():
    from geocrop.api.main import status  # reuse the per-district status logic
    reg = _regions().set_index("district_id")
    today = pd.read_parquet(NOWCAST_DIR / "district_today.parquet").set_index("district_id") if (NOWCAST_DIR / "district_today.parquet").exists() else None
    rows = []
    for did in reg.index:
        s = status(int(did))
        ind = s["indicators"]
        if today is not None and did in today.index:
            t = today.loc[did]
            ind["stress_today"] = {"as_of": t.today, "status": "estimate", "stress": t.stress, "depletion_pct": float(t.depletion_pct),
                                   "days_until_stress": None if pd.isna(t.days_until_stress) else int(t.days_until_stress),
                                   "initialised_from": t.initialised_from}
        rows.append({"district_id": int(did), "district": s["district"], "region": reg.loc[did, "region"],
                     "subregion": reg.loc[did, "subregion"] if isinstance(reg.loc[did, "subregion"], str) else None, "indicators": ind})
    return {"districts": rows, "freshness": _freshness()}


def _freshness():
    import glob
    logs = sorted(glob.glob(str(PROCESSED.parent.parent / "reports/monitor_logs/update_*.json")))
    if not logs:
        return None
    d = json.load(open(logs[-1]))
    return {"last_update": d.get("finished"), "sources": d.get("freshness", {})}


@router.get("/monitor/district/{district_id}/stress-today", tags=["monitor"])
def stress_today(district_id: int):
    p = NOWCAST_DIR / "district_today_daily.parquet"
    if not p.exists():
        raise HTTPException(503, "nowcast not precomputed yet")
    d = pd.read_parquet(p)
    d = d[d.district_id == district_id].drop(columns=["district_id"])
    d["date"] = d.date.dt.strftime("%Y-%m-%d")
    return {"value_type": "MODEL ESTIMATE", "daily": json.loads(d.to_json(orient="records"))}


INDEX_FILES = {"vegetation": "vegetation", "soil_moisture": "soil_moisture", "evaporative_stress": "evaporative_stress",
               "spi": "spi", "monsoon_departure": "monsoon_departure", "lst": "lst"}


@router.get("/monitor/district/{district_id}/index/{name}", tags=["monitor"])
def district_index(district_id: int, name: str, start: Optional[date] = None, end: Optional[date] = None):
    """Time series of one index for a district (for charts). Rows keep status (final/provisional) and quality flags."""
    from geocrop.config import INDEX_DIR
    if name not in INDEX_FILES:
        raise HTTPException(400, f"index must be one of {list(INDEX_FILES)}")
    d = pd.read_parquet(INDEX_DIR / f"{INDEX_FILES[name]}.parquet", filters=[("district_id", "==", district_id)])
    tcol = "month" if "month" in d else "date"
    d[tcol] = pd.to_datetime(d[tcol])
    if start: d = d[d[tcol] >= pd.Timestamp(start)]
    if end: d = d[d[tcol] <= pd.Timestamp(end)]
    if name == "vegetation":
        d["ndvi_normal"] = d.ndvi - d.ndvi_anom
    d = d.sort_values(tcol)
    d[tcol] = d[tcol].dt.strftime("%Y-%m-%d")
    return {"district_id": district_id, "index": name, "time_column": tcol, "data": json.loads(d.to_json(orient="records", double_precision=4))}


# ------------------------------------------------------------------ soil
@router.get("/soil/district/{district_id}", tags=["soil"])
def soil_district(district_id: int):
    """SoilGrids 2.0 district profile + Saxton-Rawls water properties. GLOBAL MODEL ESTIMATES (250 m), not lab data."""
    from geocrop.monitor import soilwater
    from geocrop.soil.district_props import OUT, usda_texture
    if not OUT.exists():
        raise HTTPException(503, "soil summary not built yet")
    d = pd.read_parquet(OUT)
    d = d[d.district_id == district_id]
    if d.empty:
        raise HTTPException(404, "unknown district")
    props = json.loads(d.drop(columns=["district_id"]).to_json(orient="records"))
    tex = []
    for dep in ["0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm"]:
        s = d[(d.property == "sand") & (d.depth == dep)]["mean"].iloc[0]; c = d[(d.property == "clay") & (d.depth == dep)]["mean"].iloc[0]
        tex.append({"depth": dep, "texture": usda_texture(s, c)})
    prof = soilwater.profile_for_district_sr(district_id)
    water = {"field_capacity_topsoil": round(float(prof["theta_fc"][0]), 3), "wilting_point_topsoil": round(float(prof["theta_wp"][0]), 3),
             "available_water_mm_per_m": round(soilwater.taw_mm(prof, 1.0), 0), "method": "Saxton & Rawls (2006) on SoilGrids 2.0 sand/clay/SOC"}
    return {"district_id": district_id, "value_type": "GLOBAL MODEL ESTIMATE (SoilGrids 2.0, 250 m); not a laboratory measurement",
            "properties": props, "texture": tex, "water": water,
            "caveat": "Field soils vary within a district. Use Soil Health Card lab results for fertilizer decisions."}


# ------------------------------------------------------------------ options for forms
CROP_LABELS = {"cotton": ("Cotton", "कापूस"), "soybean": ("Soybean", "सोयाबीन"), "maize_kharif": ("Maize (kharif)", "मका (खरीप)"),
               "maize_rabi": ("Maize (rabi)", "मका (रब्बी)"), "sorghum": ("Sorghum / Jowar", "ज्वारी"), "wheat": ("Wheat", "गहू"),
               "groundnut": ("Groundnut", "भुईमूग"), "millet": ("Pearl millet / Bajra", "बाजरी"), "onion": ("Onion", "कांदा"),
               "tomato": ("Tomato", "टोमॅटो"), "sugarcane": ("Sugarcane", "ऊस"), "chickpea": ("Chickpea / Gram", "हरभरा")}
EXTRA_CROPS = {"rice": ("Rice / Paddy", "भात"), "pigeonpea": ("Pigeon pea / Tur", "तूर"), "other": ("Other", "इतर")}


@router.get("/meta/crops", tags=["meta"])
def meta_crops():
    t = nc.crop_table()
    out = []
    for code, (en, mr) in CROP_LABELS.items():
        r = t.loc[code]
        out.append({"code": code, "label": en, "label_mr": mr, "season_hint": r.season_hint,
                    "stress_estimate_supported": not pd.isna(r.l_ini), "note": None if pd.isna(r.suitability_note) else r.suitability_note})
    for code, (en, mr) in EXTRA_CROPS.items():
        out.append({"code": code, "label": en, "label_mr": mr, "season_hint": None, "stress_estimate_supported": False,
                    "note": "No FAO-56 water-balance parameters (paddy needs a ponded balance; tur not in FAO-56 tables)" if code != "other" else None})
    return out


# ------------------------------------------------------------------ profiles (PostgreSQL)
IrrigationSrc = Literal["rainfed", "well", "borewell", "canal", "tank", "river", "drip", "sprinkler", "other"]
SoilType = Literal["black", "red", "laterite", "alluvial", "sandy", "unknown"]


class CropIn(BaseModel):
    crop: str
    crop_other: Optional[str] = Field(None, max_length=80)
    season: Literal["kharif", "rabi", "summer", "annual"]
    sowing_date: Optional[date] = None

    @field_validator("crop")
    @classmethod
    def known(cls, v):
        if v not in CROP_LABELS and v not in EXTRA_CROPS:
            raise ValueError("unknown crop code")
        return v


class FarmIn(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    district_id: int = Field(ge=1, le=36)
    taluka: Optional[str] = Field(None, max_length=80)
    village: Optional[str] = Field(None, max_length=80)
    lat: Optional[float] = Field(None, ge=15, le=23)
    lon: Optional[float] = Field(None, ge=72, le=81.5)
    area_value: Optional[float] = Field(None, gt=0, le=10000)
    area_unit: Literal["acre", "hectare", "guntha"] = "acre"
    irrigation_source: IrrigationSrc = "rainfed"
    soil_type_reported: SoilType = "unknown"
    crops: list[CropIn] = []


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: Optional[str] = Field(None, pattern=r"^[0-9+ -]{7,20}$")
    language: Literal["en", "mr"] = "en"
    farm: FarmIn


class IrrigationIn(BaseModel):
    date: date
    amount_mm: float = Field(gt=0, le=300)
    method: Optional[str] = Field(None, max_length=20)


def _profile_out(f: Farmer):
    names = district_table().set_index("district_id")["district"]
    return {"id": str(f.id), "name": f.name, "phone": f.phone, "language": f.language, "created_at": f.created_at.isoformat(),
            "farms": [{"id": str(fm.id), "name": fm.name, "district_id": fm.district_id, "district": names.get(fm.district_id),
                       "taluka": fm.taluka, "village": fm.village, "lat": fm.lat, "lon": fm.lon, "area_value": fm.area_value,
                       "area_unit": fm.area_unit, "irrigation_source": fm.irrigation_source, "soil_type_reported": fm.soil_type_reported,
                       "crops": [{"id": str(c.id), "crop": c.crop, "crop_other": c.crop_other, "season": c.season,
                                  "sowing_date": c.sowing_date.isoformat() if c.sowing_date else None} for c in fm.crops],
                       "irrigation": [{"id": str(i.id), "date": i.date.isoformat(), "amount_mm": i.amount_mm, "method": i.method}
                                      for i in fm.irrigation]} for fm in f.farms]}


def _uuid(value: str, what: str) -> uuid.UUID:
    """Parse an id from the URL; anything that is not a UUID is simply 'not found' (never reaches SQL as text)."""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(404, f"{what} not found")


def _load(session, farmer_id):
    fid = _uuid(farmer_id, "profile")
    f = session.execute(select(Farmer).where(Farmer.id == fid).options(
        selectinload(Farmer.farms).selectinload(Farm.crops), selectinload(Farmer.farms).selectinload(Farm.irrigation))).scalar_one_or_none()
    if not f:
        raise HTTPException(404, "profile not found")
    return f


def _apply_farm(fm: Farm, data: FarmIn):
    for k, v in data.model_dump(exclude={"crops"}).items():
        setattr(fm, k, v)
    fm.crops = [CropPlanting(**c.model_dump()) for c in data.crops]


@router.post("/profiles", status_code=201, tags=["profiles"])
def create_profile(p: ProfileIn):
    with SessionLocal() as s, s.begin():
        f = Farmer(name=p.name.strip(), phone=p.phone, language=p.language)
        fm = Farm(); _apply_farm(fm, p.farm); f.farms = [fm]
        s.add(f)
    with SessionLocal() as s:
        return _profile_out(_load(s, str(f.id)))


@router.get("/profiles/{farmer_id}", tags=["profiles"])
def get_profile(farmer_id: str):
    with SessionLocal() as s:
        return _profile_out(_load(s, farmer_id))


@router.put("/profiles/{farmer_id}", tags=["profiles"])
def update_profile(farmer_id: str, p: ProfileIn):
    with SessionLocal() as s, s.begin():
        f = _load(s, farmer_id)
        f.name, f.phone, f.language = p.name.strip(), p.phone, p.language
        fm = f.farms[0] if f.farms else Farm()
        _apply_farm(fm, p.farm)
        if not f.farms:
            f.farms = [fm]
    with SessionLocal() as s:
        return _profile_out(_load(s, farmer_id))


@router.delete("/profiles/{farmer_id}", status_code=204, tags=["profiles"])
def delete_profile(farmer_id: str):
    with SessionLocal() as s, s.begin():
        s.delete(_load(s, farmer_id))


@router.post("/farms/{farm_id}/irrigation", status_code=201, tags=["profiles"])
def add_irrigation(farm_id: str, ev: IrrigationIn):
    with SessionLocal() as s, s.begin():
        fm = s.get(Farm, _uuid(farm_id, "farm"))
        if not fm:
            raise HTTPException(404, "farm not found")
        s.add(IrrigationEvent(farm_id=fm.id, **ev.model_dump()))
    return {"ok": True}


@router.delete("/farms/{farm_id}/irrigation/{event_id}", status_code=204, tags=["profiles"])
def delete_irrigation(farm_id: str, event_id: str):
    with SessionLocal() as s, s.begin():
        ev = s.get(IrrigationEvent, _uuid(event_id, "event"))
        if not ev or ev.farm_id != _uuid(farm_id, "farm"):
            raise HTTPException(404, "event not found")
        s.delete(ev)


@router.get("/farms/{farm_id}/nowcast", tags=["profiles"])
def farm_nowcast(farm_id: str, crop_id: Optional[str] = None):
    """Field stress ESTIMATE for the farm's crop, using its district, sowing date and logged irrigation."""
    with SessionLocal() as s:
        fm = s.execute(select(Farm).where(Farm.id == _uuid(farm_id, "farm")).options(selectinload(Farm.crops), selectinload(Farm.irrigation))).scalar_one_or_none()
        if not fm:
            raise HTTPException(404, "farm not found")
        crops = [c for c in fm.crops if (crop_id is None or str(c.id) == crop_id)]
        supported = [c for c in crops if c.crop in nc.crop_table().index and not pd.isna(nc.crop_table().loc[c.crop].l_ini) and c.sowing_date]
        if not supported:
            return {"available": False, "reason": "No crop with a sowing date and FAO-56 water-balance parameters on this farm."}
        c = supported[-1]
        irr = {i.date: i.amount_mm for i in fm.irrigation}
        try:
            r = nc.nowcast(fm.district_id, c.crop, c.sowing_date, date.today(), irrigation=irr, horizon_days=10)
        except ValueError as e:
            return {"available": False, "reason": str(e)}
        d = r.daily.copy(); d["date"] = d.date.dt.strftime("%Y-%m-%d")
        return {"available": True, "value_type": "MODEL ESTIMATE", "crop": c.crop, "sowing_date": c.sowing_date.isoformat(),
                "irrigation_source": fm.irrigation_source, "meta": json.loads(json.dumps(r.meta, default=str)),
                "daily": json.loads(d.to_json(orient="records"))}
