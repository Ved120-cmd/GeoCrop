"""Farm Simulator API: AquaCrop 7.3 'what if' runs over past seasons for a district."""
import hashlib
import json
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from geocrop.simulator import scenario as sc

router = APIRouter(prefix="/simulator", tags=["simulator"])
_CACHE: dict[str, dict] = {}
_CACHE_MAX = 200

SEASON_HINT = {"soybean": "kharif", "cotton": "kharif", "maize": "kharif or rabi", "sorghum": "kharif or rabi", "wheat": "rabi",
               "sunflower": "kharif, rabi or summer", "tomato": "rabi / any (irrigated)", "potato": "rabi"}
LABEL_MR = {"soybean": "सोयाबीन", "cotton": "कापूस", "maize": "मका", "sorghum": "ज्वारी", "wheat": "गहू", "sunflower": "सूर्यफूल", "tomato": "टोमॅटो", "potato": "बटाटा"}


class IrrigationIn(BaseModel):
    mode: Literal["rainfed", "net", "schedule"] = "rainfed"
    allowable_depletion_raw_pct: int = Field(50, ge=0, le=100)
    schedule: list[tuple[int, float]] = Field(default_factory=list, description="[(day after sowing, mm), ...]")
    method: Literal[1, 3, 4, 5] = 1   # 1 sprinkler, 3 drip, 4 furrow, 5 basin/flood

    @model_validator(mode="after")
    def check(self):
        if self.mode == "schedule":
            if not self.schedule:
                raise ValueError("schedule mode needs at least one (day, mm) event")
            for d, mm in self.schedule:
                if not (1 <= d <= 365 and 0 < mm <= 300):
                    raise ValueError("schedule events must be day 1..365 and 0 < mm <= 300")
        return self

    def to_sc(self):
        wetted = 30 if self.method == 3 else 100
        return sc.Irrigation(self.mode, self.allowable_depletion_raw_pct, [(int(d), float(m)) for d, m in self.schedule], self.method, wetted)


class ScenarioIn(BaseModel):
    label: Optional[str] = Field(None, max_length=60)
    sow_month: int = Field(ge=1, le=12)
    sow_day: int = Field(ge=1, le=31)
    irrigation: IrrigationIn = IrrigationIn()


class RunIn(BaseModel):
    district_id: int = Field(ge=1, le=36)
    crop: str
    scenarios: list[ScenarioIn] = Field(min_length=1, max_length=3)
    detail_year: Optional[int] = Field(None, ge=2015, le=2030, description="return daily curves for this season")


@router.get("/crops")
def crops():
    return [{"code": k, "label": k.capitalize(), "label_mr": LABEL_MR.get(k), "crop_file": v[0], "calibration": v[1], "yield_type": v[3],
             "season_hint": SEASON_HINT.get(k)} for k, v in sc.CROPS.items()]


@router.get("/district/{district_id}/soil")
def district_soil(district_id: int):
    """The soil profile the simulator uses for this district (estimate)."""
    return {"value_type": "ESTIMATE (Saxton & Rawls 2006 on SoilGrids 2.0, cropland mean)",
            "horizons": [h.__dict__ for h in sc.district_horizons(district_id)], "last_observed_weather": str(sc.last_weather_date(district_id))}


@router.post("/run")
def run(req: RunIn):
    """Simulate each scenario over all past seasons with observed weather. Scenario 1 is the reference for differences."""
    if req.crop not in sc.CROPS:
        raise HTTPException(400, f"crop must be one of {list(sc.CROPS)}")
    key = hashlib.sha1(json.dumps(req.model_dump(), sort_keys=True, default=str).encode()).hexdigest()
    if key in _CACHE:
        return _CACHE[key] | {"cached": True}
    out = []
    for i, s in enumerate(req.scenarios):
        try:
            r = sc.simulate_years(req.district_id, req.crop, s.sow_month, s.sow_day, s.irrigation.to_sc(), keep_daily_for=req.detail_year)
        except ValueError as e:
            raise HTTPException(422, str(e))
        r["label"] = s.label or f"Scenario {i + 1}"
        out.append(r)
    ref = out[0]["summary"]
    if ref:
        for r in out[1:]:
            if r["summary"]:
                common = {x["year"]: x for x in out[0]["runs"] if x["complete_observed_weather"]}
                pairs = [(x, common[x["year"]]) for x in r["runs"] if x["complete_observed_weather"] and x["year"] in common]
                if pairs:
                    import numpy as np
                    dy = [a["yield_t_ha"] - b["yield_t_ha"] for a, b in pairs]
                    dw = [a["irrigation_mm"] - b["irrigation_mm"] for a, b in pairs]
                    r["vs_reference"] = {"median_yield_change_t_ha": round(float(np.median(dy)), 2),
                                         "median_yield_change_pct": round(100 * float(np.median([d / max(b["yield_t_ha"], 0.01) for d, (a, b) in zip(dy, pairs)])), 0),
                                         "median_extra_irrigation_mm": round(float(np.median(dw)), 0), "seasons_better": int(sum(d > 0.05 for d in dy)),
                                         "seasons_worse": int(sum(d < -0.05 for d in dy)), "n_seasons": len(pairs)}
    resp = {"district_id": req.district_id, "crop": req.crop, "value_type": "SIMULATION (FAO AquaCrop 7.3, uncalibrated FAO crop parameters)",
            "scenarios": out, "cached": False}
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = resp
    return resp
