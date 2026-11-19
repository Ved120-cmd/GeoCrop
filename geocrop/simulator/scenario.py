"""Maharashtra scenarios for AquaCrop: district weather, soil and initial water -> engine runs -> tidy results.

What the simulator answers: "with THIS crop, sown on THIS date, under THIS water management, what yield and water
use would the last N seasons' weather have produced in this district?" -> a distribution across real past seasons.

Honest framing (shown in the UI):
* Crop parameters are FAO AquaCrop defaults (calibrated elsewhere; Soybean at Patancheru, India). Not yet calibrated
  for Maharashtra varieties.
* Soil fertility is non-limiting and there are no pests/weeds -> results are WATER-LIMITED ATTAINABLE yield, typically
  well above farmers' actual yields (the yield gap).
* Weather and soil are district averages (POWER ~50 km, IMD 0.25 deg, SoilGrids 250 m averaged).
"""
import math
import shutil
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

from geocrop.config import PROCESSED
from geocrop.monitor import soilwater
from geocrop.simulator import aquacrop as ac

WEATHER = PROCESSED / "monitor/weather"

# crop code -> (AquaCrop file, calibration origin, yield column, yield label, max season days)
CROPS = {
    "soybean": ("SoybeanGDD.CRO", "FAO default, Patancheru (India) 1996", "Y(dry)", "grain (dry)", 200),
    "cotton": ("CottonGDD.CRO", "FAO default, Cordoba (Spain) 1986", "Y(dry)", "seed cotton (dry)", 260),
    "maize": ("MaizeGDD.CRO", "FAO default, Davis (USA) 1996", "Y(dry)", "grain (dry)", 220),
    "sorghum": ("SorghumGDD.CRO", "Bushland, Texas (USA) 1993", "Y(dry)", "grain (dry)", 200),
    "wheat": ("WheatGDD.CRO", "FAO default, Valenzano (Italy) 2007", "Y(dry)", "grain (dry)", 220),
    "sunflower": ("SunflowerGDD.CRO", "FAO default, Cordoba (Spain) 1986", "Y(dry)", "seed (dry)", 200),
    "tomato": ("TomatoGDD.CRO", "FAO default, Cordoba (Spain) 1986", "Y(fresh)", "fresh fruit", 220),
    "potato": ("PotatoGDD.CRO", "FAO default, Lima (Peru) 1995", "Y(fresh)", "fresh tubers", 200),
}
T_HA_TO_QUINTAL_ACRE = 10 / 2.47105  # 1 t/ha = 10 q/ha = 4.047 q/acre


# ------------------------------------------------------------------ weather
@lru_cache(maxsize=40)
def district_weather(district_id: int) -> pd.DataFrame:
    """Continuous daily weather for a district: tmin, tmax, eto (NASA POWER, FAO-56 PM) and rain
    (IMD gauge grid; after IMD's last release, IMERG scaled to IMD - provisional). Gaps filled by
    day-of-year climatology and flagged."""
    pw = pd.read_parquet(WEATHER / "power.parquet", columns=["date", "district_id", "tmin", "tmax", "eto"], filters=[("district_id", "==", district_id)])
    pw["date"] = pd.to_datetime(pw.date)
    ext = WEATHER / "rain_imd_extended.parquet"  # written by indices.rainfall_indices (daily update)
    if ext.exists():
        rain = pd.read_parquet(ext, filters=[("district_id", "==", district_id)])
    else:
        from geocrop.monitor.indices import rain_with_nrt_extension
        rain = rain_with_nrt_extension(); rain = rain[rain.district_id == district_id]
    rain["date"] = pd.to_datetime(rain.date)
    rain = rain[rain.date >= "2014-12-01"][["date", "precip_imd", "rain_source"]]
    w = pw[["date", "tmin", "tmax", "eto"]].merge(rain, on="date", how="outer").rename(columns={"precip_imd": "rain"})
    w = w[w.date >= "2015-01-01"].sort_values("date").drop_duplicates("date")
    # continuous calendar to +400 days: any day without all four observed values is climatology-filled and flagged
    full = pd.DataFrame({"date": pd.date_range("2015-01-01", pd.Timestamp.today().normalize() + pd.Timedelta(days=400), freq="D")})
    w = full.merge(w, on="date", how="left")
    w["filled"] = w[["tmin", "tmax", "eto", "rain"]].isna().any(axis=1)
    doy = w.date.dt.day_of_year
    for c in ("tmin", "tmax", "eto", "rain"):
        obs = w[c].notna()
        clim = w[obs].groupby(doy[obs])[c].agg("mean" if c != "rain" else "median")
        w[c] = w[c].fillna(doy.map(clim))
    return w.reset_index(drop=True)


def last_weather_date(district_id: int) -> date:
    """Last day with fully observed weather (all of tmin, tmax, eto, rain)."""
    w = district_weather(district_id)
    return w.loc[~w.filled, "date"].max().date()


# ------------------------------------------------------------------ soil
def saxton_rawls_ksat_mm_day(wp, fc, sat):
    """Saxton & Rawls (2006) eqs. 15-16: Ksat (mm/h) = 1930 (theta_s - theta_33)^(3 - lambda); lambda = 1/B,
    B = (ln 1500 - ln 33) / (ln theta_33 - ln theta_1500). Returns mm/day."""
    B = (math.log(1500) - math.log(33)) / (math.log(fc) - math.log(wp))
    lam = 1 / B
    return 1930 * max(sat - fc, 1e-4) ** (3 - lam) * 24


@lru_cache(maxsize=40)
def district_horizons(district_id: int) -> list[ac.Horizon]:
    p = soilwater.profile_for_district_sr(district_id)
    wp, fc, sat = p["theta_wp"], p["theta_fc"], p["theta_sat"]
    # SoilGrids depth intervals: 0-5, 5-15, 15-30, 30-60, 60-100, 100-200 cm -> 4 AquaCrop horizons
    groups = [((0, 1, 2), (0.05, 0.10, 0.15), 0.30, "0-30 cm"), ((3,), (1,), 0.30, "30-60 cm"), ((4,), (1,), 0.40, "60-100 cm"), ((5,), (1,), 1.00, "100-200 cm")]
    out = []
    for idx, wts, thick, desc in groups:
        wts = np.array(wts) / sum(wts)
        w_, f_, s_ = (float(np.dot(arr[list(idx)], wts)) for arr in (wp, fc, sat))
        out.append(ac.Horizon(thick, round(100 * s_, 1), round(100 * f_, 1), round(100 * w_, 1),
                              round(saxton_rawls_ksat_mm_day(w_, f_, s_), 1), description=desc))
    return out


# ------------------------------------------------------------------ initial water
def initial_water(district_id: int, sow: date, horizons):
    """Relative wetness from SMAP root zone (district climatology rescaling, as in the nowcast) on the sowing date,
    applied between WP and FC of every horizon. Falls back to 50 % of available water before SMAP's record."""
    from geocrop.monitor.nowcast import smap_relative_wetness
    rel = 0.5
    src = "assumed 50% of available water (no SMAP data for this date)"
    try:
        sm, _ = smap_relative_wetness(district_id)
        s = sm[sm.index <= pd.Timestamp(sow)].dropna(subset=["rel_wetness"])
        if not s.empty and (pd.Timestamp(sow) - s.index.max()).days <= 7:
            rel = float(s.rel_wetness.iloc[-1]); src = f"SMAP root zone on {s.index.max().date()} (relative wetness {rel:.2f})"
    except Exception:
        pass
    depths, vols, z = [], [], 0.0
    for h in horizons:
        z += h.thickness_m
        depths.append(round(z - h.thickness_m / 2, 2))
        vols.append(round(h.wp + rel * (h.fc - h.wp), 2))
    return depths, vols, src


# ------------------------------------------------------------------ scenario run
@dataclass
class Irrigation:
    mode: str = "rainfed"                 # rainfed | net | schedule
    allowable_depletion_raw_pct: int = 50  # for net: irrigate when depletion exceeds this % of RAW
    schedule: list = field(default_factory=list)  # for schedule: [(day after sowing, mm), ...]
    method: int = 1                        # 1 sprinkler, 3 drip, 4 furrow, 5 basin
    wetted_pct: int = 100

    def label(self):
        if self.mode == "rainfed": return "Rainfed"
        if self.mode == "net": return f"Irrigate when needed (refill at {self.allowable_depletion_raw_pct}% of RAW)"
        return f"Fixed schedule ({len(self.schedule)} irrigations, {sum(mm for _, mm in self.schedule):.0f} mm)"


def _prepare(D, LIST, tag, district_id, crop, sow, irrigation):
    """Write one season's input files (prefixed with tag) and its project file. Returns metadata."""
    cro, origin, ycol, ylabel, maxdays = CROPS[crop]
    w = district_weather(district_id)
    end = sow + timedelta(days=maxdays)
    seg = w[(w.date >= pd.Timestamp(sow)) & (w.date <= pd.Timestamp(end))]
    if seg.empty or seg.date.min().date() != sow or seg.date.max().date() < end:
        raise ValueError(f"weather series does not cover {sow}..{end}")
    hz = district_horizons(district_id)
    depths, vols, init_src = initial_water(district_id, sow, hz)
    ac.write_climate(D, f"{tag}W", seg[["date", "tmin", "tmax", "eto", "rain"]], f"GeoCrop district {district_id} {sow}..{end}")
    if not (D / cro).exists():
        shutil.copy(ac.GUI_DATA / cro, D / cro)
    if not (D / "Soil.SOL").exists():
        ac.write_soil(D, "Soil", hz, f"GeoCrop district {district_id} - Saxton-Rawls on SoilGrids 2.0 (estimate)")
    ac.write_initial_conditions(D, f"{tag}I", depths, vols, init_src[:60])
    files = dict(clim=f"{tag}W.CLI", tnx=f"{tag}W.Tnx", eto=f"{tag}W.ETo", plu=f"{tag}W.PLU", co2="MaunaLoa.CO2", cro=cro, sol="Soil.SOL", sw0=f"{tag}I.SW0")
    if irrigation.mode == "net":
        ac.write_irrigation_net(D, f"{tag}R", irrigation.allowable_depletion_raw_pct, irrigation.method, irrigation.wetted_pct); files["irr"] = f"{tag}R.IRR"
    elif irrigation.mode == "schedule" and irrigation.schedule:
        ac.write_irrigation_schedule(D, f"{tag}R", irrigation.schedule, irrigation.method, irrigation.wetted_pct); files["irr"] = f"{tag}R.IRR"
    ac.write_project(LIST / f"{tag}.PRO", f"GeoCrop {crop} d{district_id} sown {sow}", sow, end, sow, end, files)
    return dict(sow=sow, init_src=init_src, filled=seg.set_index("date").filled, ycol=ycol, ylabel=ylabel)


def _summarise(res, meta, keep_daily):
    s = res.season.iloc[0]
    sow, ycol = meta["sow"], meta["ycol"]
    y = float(s[ycol])
    cyc_end = pd.Timestamp(sow) + pd.Timedelta(days=max(int(s["Cycle"]), 1))
    filled = meta["filled"]
    cyc_filled = float(filled[(filled.index >= pd.Timestamp(sow)) & (filled.index <= cyc_end)].mean())
    out = dict(sow_date=str(sow), year=sow.year, yield_t_ha=round(y, 2), yield_q_acre=round(y * T_HA_TO_QUINTAL_ACRE, 1), yield_type=meta["ylabel"],
               biomass_t_ha=round(float(s["BioMass"]), 2), harvest_index_pct=float(s["HI"]), cycle_days=int(s["Cycle"]),
               rain_mm=float(s["Rain"]), irrigation_mm=float(s["Irri"]), eto_mm=float(s["ETo"]), transpiration_mm=float(s["Tr"]),
               evaporation_mm=float(s["E"]), drainage_mm=float(s["Drain"]), runoff_mm=float(s["Runoff"]),
               water_stress_expansion_pct=int(s["ExpStr"]), water_stress_stomata_pct=int(s["StoStr"]), temperature_stress_pct=int(s["TempStr"]),
               water_productivity_kg_m3=float(s["WPet"]), weather_gap_filled_pct=round(100 * cyc_filled, 1), complete_observed_weather=cyc_filled == 0.0, initial_water=meta["init_src"],
               harvest_date=str(sow + timedelta(days=int(s["Cycle"]))) if s["Cycle"] > 0 else None)
    if keep_daily:
        d = res.daily
        d = d[d["Stage"] > 0] if "Stage" in d else d
        cols = {"DAP": "dap", "CC": "canopy_pct", "Biomass": "biomass_t_ha", ycol: "yield_t_ha", "Tr/Trx": "transp_rel_pct",
                "Rain": "rain_mm", "Irri": "irrigation_mm", "StSto": "stress_stomata_pct", "Wr": "root_zone_water_mm",
                "Wr(FC)": "root_zone_fc_mm", "Wr(PWP)": "root_zone_pwp_mm"}
        dd = d[[c for c in cols if c in d.columns]].rename(columns=cols)
        dd.insert(0, "date", [str(sow + timedelta(days=int(x) - 1)) for x in dd.dap])
        out["daily"] = dd.astype(object).where(dd != -9, None).to_dict(orient="records")
    return out


def run_seasons(district_id: int, crop: str, sows: list[date], irrigation: Irrigation, keep_daily_for: set | None = None, parallel=2):
    """Simulate several seasons, batched into `parallel` engine processes. Returns (results, errors)."""
    from concurrent.futures import ThreadPoolExecutor
    if crop not in CROPS:
        raise ValueError(f"crop must be one of {list(CROPS)}")
    keep_daily_for = keep_daily_for or set()
    chunks = [sows[i::parallel] for i in range(parallel) if sows[i::parallel]]

    def one_batch(chunk):
        r = ac.new_run_dir()
        D, LIST = r / "testcase/DATA", r / "testcase/LIST"
        metas, errs = {}, []
        for i, sow in enumerate(chunk):
            tag = f"S{i:02d}"
            try:
                metas[tag] = _prepare(D, LIST, tag, district_id, crop, sow, irrigation)
            except Exception as e:
                errs.append(dict(sow_date=str(sow), error=str(e)[:300]))
        outs = []
        if metas:
            res = ac.run_batch(r, list(metas))
            for tag, rr in res.items():
                if isinstance(rr, Exception):
                    errs.append(dict(sow_date=str(metas[tag]["sow"]), error=str(rr)[:300]))
                else:
                    outs.append(_summarise(rr, metas[tag], metas[tag]["sow"] in keep_daily_for))
        shutil.rmtree(r, ignore_errors=True)
        return outs, errs

    results, errors = [], []
    with ThreadPoolExecutor(len(chunks) or 1) as ex:
        for o, e in ex.map(one_batch, chunks):
            results += o; errors += e
    return sorted(results, key=lambda x: x["sow_date"]), errors


def simulate_season(district_id: int, crop: str, sow: date, irrigation: Irrigation, keep_daily=True) -> dict:
    res, err = run_seasons(district_id, crop, [sow], irrigation, {sow} if keep_daily else set(), parallel=1)
    if not res:
        raise RuntimeError(err[0]["error"] if err else "simulation failed")
    return res[0]


def simulate_years(district_id: int, crop: str, sow_month: int, sow_day: int, irrigation: Irrigation, years=None, keep_daily_for=None):
    """Run the same management over past seasons. Returns per-year results + summary statistics."""
    cro, origin, ycol, ylabel, maxdays = CROPS[crop]
    last = last_weather_date(district_id)
    years = years or [y for y in range(2015, last.year + 1) if date(2015, 4, 1) <= date(y, sow_month, sow_day) <= last]
    sows = [date(y, sow_month, sow_day) for y in years]
    keep = {date(keep_daily_for, sow_month, sow_day)} if keep_daily_for else set()
    runs, errors = run_seasons(district_id, crop, sows, irrigation, keep)
    complete = [r for r in runs if r["complete_observed_weather"]]
    ys = np.array([r["yield_t_ha"] for r in complete])
    summary = None
    if len(ys):
        summary = dict(n_seasons=len(ys), median_t_ha=round(float(np.median(ys)), 2), p10_t_ha=round(float(np.percentile(ys, 10)), 2),
                       p90_t_ha=round(float(np.percentile(ys, 90)), 2), min_t_ha=round(float(ys.min()), 2), max_t_ha=round(float(ys.max()), 2),
                       median_q_acre=round(float(np.median(ys)) * T_HA_TO_QUINTAL_ACRE, 1),
                       median_irrigation_mm=round(float(np.median([r["irrigation_mm"] for r in complete])), 0),
                       median_rain_mm=round(float(np.median([r["rain_mm"] for r in complete])), 0),
                       worst_year=int(complete[int(ys.argmin())]["year"]), best_year=int(complete[int(ys.argmax())]["year"]),
                       note="Statistics use only seasons whose whole crop cycle had observed weather.")
    return dict(crop=crop, crop_file=cro, crop_calibration=origin, yield_type=ylabel, district_id=district_id, sow=f"{sow_day:02d}-{sow_month:02d}",
                irrigation=irrigation.label(), runs=runs, errors=errors, summary=summary,
                soil=[h.__dict__ for h in district_horizons(district_id)],
                caveats=["Water-limited attainable yield: soil fertility non-limiting, no pests or weeds - real farm yields are usually lower.",
                         f"Crop parameters: {origin}; not yet calibrated for Maharashtra varieties.",
                         "District-average weather and soil; your field can differ."])
