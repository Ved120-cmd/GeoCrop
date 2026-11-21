"""Crop Advisor API: crop ranking for a district, season and water situation, from simulated past seasons."""
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from geocrop.common.districts import district_table
from geocrop.config import INDEX_DIR, PROCESSED

router = APIRouter(prefix="/advisor", tags=["crop advisor"])
VALUE_TYPE = ("MODEL ESTIMATE: FAO AquaCrop water-limited attainable yield over past seasons (district weather and soil; "
              "fertility non-limiting, no pests; crop parameters not calibrated for Maharashtra varieties)")


def _rank():
    from geocrop.advisor import rank
    try:
        rank.table()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
    return rank


@router.get("/options")
def options():
    from geocrop.advisor.precompute import SEASONS
    r = _rank()
    return {"seasons": {k: dict(crops=v["crops"], sow_dates=[f"{m:02d}-{d:02d}" for m, d in v["sow"]]) for k, v in SEASONS.items()},
            "water": ["rainfed", "irrigated"], "classes": [dict(code=c[1], min_relative_yield=c[0], label=c[2], label_mr=c[3]) for c in r.CLASSES],
            "coverage": r.coverage()}


def _context(district_id: int):
    """This season's conditions: latest SMAP root-zone percentile and Predict dry-soil risk (if available)."""
    ctx = {}
    try:
        sm = pd.read_parquet(INDEX_DIR / "soil_moisture.parquet", columns=["date", "district_id", "sm_percentile"], filters=[("district_id", "==", district_id)])
        r = sm.sort_values("date").dropna().iloc[-1]
        ctx["soil_moisture"] = dict(as_of=str(pd.Timestamp(r.date).date()), percentile=round(float(r.sm_percentile), 1))
    except Exception:
        pass
    f = PROCESSED / "predict" / "district_forecast.parquet"
    if f.exists():
        p = pd.read_parquet(f)
        p = p[p.district_id == district_id]
        ctx["dry_risk"] = [dict(lead_days=int(x.lead_days), valid_date=str(x.valid_date), prob_dry=round(float(x.prob_dry), 3), dry_risk=x.dry_risk)
                           for x in p.itertuples()]
    return ctx


@router.get("/district/{district_id}")
def district(district_id: int, season: str = Query("kharif", pattern="^(kharif|rabi)$"), water: str = Query("rainfed", pattern="^(rainfed|irrigated)$")):
    r = _rank()
    t = district_table().set_index("district_id")
    if district_id not in t.index:
        raise HTTPException(404, "unknown district")
    recs, excluded = r.recommend(district_id, season, water)
    if not recs:
        raise HTTPException(503, "simulations for this district are not available yet")
    return {"value_type": VALUE_TYPE, "district_id": district_id, "district": t.loc[district_id, "district"], "season": season, "water": water,
            "recommendations": recs, "not_ranked": excluded, "context": _context(district_id), "warnings": r.warnings_for(district_id),
            "method": "Ranked by relative yield (district median / best 5% of districts under the same water regime) at the best tested sowing date; "
                      "classes after the FAO (1976) framework (S1 >= 80%, S2 40-80%, S3 20-40%, N < 20%); within a class, crops with better bad-year (1 in 10) yields rank higher.",
            "caveats": ["Yields are attainable (no pests, ample nutrients) and usually above farm yields; use them to compare crops, not as a promise.",
                        "Only 8 crops can be simulated so far; pulses (tur, chickpea, moong), rice, onion, sugarcane and fruit crops are not covered.",
                        "Market prices, input costs, labour and local practice are not included: discuss the choice with your KVK or agriculture officer."]}


@router.get("/ipm/{crop}")
def ipm(crop: str):
    r = _rank()
    name = r.IPM_FILE.get(crop)
    if not name or not (r.IPM_DIR / name).exists():
        raise HTTPException(404, "no official IPM package for this crop")
    return FileResponse(r.IPM_DIR / name, media_type="application/pdf", filename=name,
                        headers={"Content-Disposition": f'inline; filename="{name}"'})
