"""Today's crop water stress: FAO-56 single-coefficient root-zone water balance, started from SMAP.

ESTIMATE, not an observation. Chain:
  1. Initial depletion Dr0 on the latest SMAP day: SMAP root-zone moisture is rescaled to the soil's TAW using
     SMAP's own district climatology (5th/95th percentile = dry/wet ends):
        rel = clip((theta - p5) / (p95 - p5), 0, 1);  Dr0 = (1 - rel) * TAW
     (SMAP's model soil differs from SoilGrids, so absolute volumetric values are not mixed.)
  2. Daily FAO-56 balance (Allen et al. 1998, ch. 8):
        Dr_t = clip(Dr_{t-1} - P_t - I_t + Ks*Kc*ETo_t, 0, TAW_t)
        Ks = 1 if Dr <= RAW else (TAW - Dr) / ((1 - p) * TAW),  RAW = p*TAW,  p = clip(p_tab + 0.04(5 - ETc), .1, .8)
  3. Kc from FAO-56 stage table (linear in development and late stages); root depth grows linearly from
     ZR_INITIAL at sowing to the FAO max-root-depth midpoint at the end of the development stage.
Simplifications (all documented in outputs): no surface runoff term (excess becomes deep percolation),
no capillary rise, uniform rain over the district, Kc_ini from FAO-56 crop-group values.

Weather priority per day (`weather_for_district`):
  rain: IMD gridded (gauge) > IMERG (satellite; provisional within ~4 months) > ECMWF forecast
  ETo : NASA POWER Penman-Monteith > ECMWF-forecast Penman-Monteith > Hargreaves
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from geocrop.config import PROCESSED, REFERENCE, SERIES_DIR
from geocrop.monitor import soilwater

ZR_INITIAL = 0.15   # m, root depth at sowing (FAO-56 ch. 8 suggests ~0.15-0.20 m initial effective root depth)
WEATHER = PROCESSED / "monitor/weather"
CROPS = REFERENCE / "fao56_crop_params.csv"
SUPPORTED_TAW = ("saxton_rawls", "soilgrids2017")


def crop_table():
    return pd.read_csv(CROPS).set_index("crop")


@dataclass
class Crop:
    name: str
    sow: date

    def __post_init__(self):
        r = crop_table().loc[self.name]
        if pd.isna(r.l_ini):
            raise ValueError(f"{self.name}: no FAO-56 stage lengths - nowcast disabled ({r.suitability_note})")
        self.p_tab = float(r.p)
        self.kc = (float(r.kc_ini), float(r.kc_mid), float(r.kc_end))
        self.L = [int(r.l_ini), int(r.l_dev), int(r.l_mid), int(r.l_late)]
        self.zr_max = (float(r.zr_max_min_m) + float(r.zr_max_max_m)) / 2

    def stage(self, d: date):
        t = (d - self.sow).days
        a, b, c, e = np.cumsum(self.L)
        if t < 0 or t > e:
            return "off-season", np.nan, np.nan
        ki, km, ke = self.kc
        if t <= a:
            return "initial", ki, ZR_INITIAL
        if t <= b:
            f = (t - a) / self.L[1]
            return "development", ki + f * (km - ki), ZR_INITIAL + f * (self.zr_max - ZR_INITIAL)
        if t <= c:
            return "mid-season", km, self.zr_max
        return "late-season", km + (t - c) / self.L[3] * (ke - km), self.zr_max


def soil_profile(district_id, source="saxton_rawls"):
    if source == "saxton_rawls":
        return soilwater.profile_for_district_sr(district_id)
    return soilwater.profile_for_district(district_id)


# ------------------------------------------------------------------ weather assembly
def _read(name, cols):
    p = WEATHER / name
    if not p.exists():
        return pd.DataFrame(columns=["date", "district_id", *cols])
    df = pd.read_parquet(p)
    df["date"] = pd.to_datetime(df.date)
    return df


def weather_for_district(district_id, start, end):
    days = pd.DataFrame({"date": pd.date_range(start, end, freq="D")})
    imd = _read("rain_imd.parquet", ["precip_imd"]).query("district_id == @district_id")[["date", "precip_imd"]]
    imerg_p = SERIES_DIR / "IMERG"
    imerg = pd.read_parquet(imerg_p, filters=[("district_id", "==", district_id), ("mask", "==", "all")]) if imerg_p.exists() else pd.DataFrame()
    if len(imerg):
        imerg["date"] = pd.to_datetime(imerg.date)
        imerg = imerg[["date", "mean", "status"]].rename(columns={"mean": "precip_imerg", "status": "imerg_status"})
    pw = _read("power.parquet", ["eto"]).query("district_id == @district_id")[["date", "eto", "eto_method"]]
    fc = _read("ecmwf_forecast.parquet", ["precip_fc", "eto_fc"])
    if len(fc):
        fc = fc.query("district_id == @district_id")[["date", "precip_fc", "eto_fc", "run"]]
    w = days.merge(imd, on="date", how="left")
    if len(imerg):
        w = w.merge(imerg, on="date", how="left")
    w = w.merge(pw, on="date", how="left")
    if len(fc):
        w = w.merge(fc, on="date", how="left")
    for c in ("precip_imerg", "imerg_status", "precip_fc", "eto_fc", "run", "eto_method"):
        if c not in w:
            w[c] = np.nan
    w["rain_mm"] = w.precip_imd.combine_first(w.precip_imerg).combine_first(w.precip_fc)
    w["rain_src"] = np.select([w.precip_imd.notna(), w.precip_imerg.notna(), w.precip_fc.notna()],
                              ["IMD (gauge)", "IMERG " + w.imerg_status.fillna("final").astype(str), "ECMWF forecast"], "missing")
    w["eto_mm"] = w.eto.combine_first(w.eto_fc)
    w["eto_src"] = np.select([w.eto.notna(), w.eto_fc.notna()],
                             ["POWER " + w.eto_method.fillna("").astype(str), "ECMWF forecast (Penman-Monteith)"], "missing")
    w["kind"] = np.where(w.rain_src.str.startswith("ECMWF") | w.eto_src.str.startswith("ECMWF"), "forecast", "observed")
    # Gaps between the last observation and the first forecast day (e.g. POWER lags ~3 d, ECMWF starts at its run date):
    # fill with district day-of-year climatology (+/-7 d, 2015-2025): median rain, mean ETo. Flagged, never silent.
    gap_r, gap_e = w.rain_mm.isna(), w.eto_mm.isna()
    if gap_r.any() or gap_e.any():
        clim = _climatology(district_id)
        doy = w.date.dt.day_of_year
        w.loc[gap_r, "rain_mm"] = clim.loc[doy[gap_r], "rain_median"].values
        w.loc[gap_r, "rain_src"] = "climatology (gap fill)"
        w.loc[gap_e, "eto_mm"] = clim.loc[doy[gap_e], "eto_mean"].values
        w.loc[gap_e, "eto_src"] = "climatology (gap fill)"
        w.loc[gap_r | gap_e, "kind"] = "gap-filled"
    return w[["date", "rain_mm", "rain_src", "eto_mm", "eto_src", "kind"]]


def _climatology(district_id, window=7):
    """Day-of-year climatology for gap filling: median rain (IMD 2015-2025) and mean POWER ETo, +/- window days."""
    imd = _read("rain_imd.parquet", ["precip_imd"]).query("district_id == @district_id")
    imd = imd[imd.date >= "2015-01-01"]
    pw = _read("power.parquet", ["eto"]).query("district_id == @district_id")

    def windowed(df, col, how):
        # each observation contributes to every day-of-year within +/- window (circular), then one groupby
        doy = df.date.dt.day_of_year.values
        vals = df[col].values
        shifts = np.arange(-window, window + 1)
        tgt = ((doy[None, :] - 1 + shifts[:, None]) % 366) + 1
        s = pd.Series(np.tile(vals, len(shifts)), index=tgt.ravel())
        return getattr(s.groupby(level=0), how)().reindex(range(1, 367))

    return pd.DataFrame({"rain_median": windowed(imd, "precip_imd", "median"),
                         "eto_mean": windowed(pw, "eto", "mean")}).rename_axis("doy")


# ------------------------------------------------------------------ SMAP initial state
def smap_relative_wetness(district_id):
    s = pd.read_parquet(SERIES_DIR / "SMAP", filters=[("district_id", "==", district_id), ("mask", "==", "all"),
                                                      ("variable", "==", "sm_rootzone")])
    s["date"] = pd.to_datetime(s.date)
    base = s[(s.date >= "2015-04-01") & (s.date <= "2024-12-31")]["mean"]
    p5, p95 = np.nanpercentile(base, 5), np.nanpercentile(base, 95)
    s["rel_wetness"] = ((s["mean"] - p5) / (p95 - p5)).clip(0, 1)
    return s[["date", "mean", "rel_wetness"]].rename(columns={"mean": "sm_rootzone"}).set_index("date"), (p5, p95)


# ------------------------------------------------------------------ the balance
@dataclass
class Result:
    daily: pd.DataFrame
    meta: dict = field(default_factory=dict)


def run_balance(district_id, crop: Crop, start: date, end: date, dr0_frac: float, weather: pd.DataFrame,
                irrigation: dict | None = None, taw_source="saxton_rawls"):
    """dr0_frac: initial depletion as a fraction of TAW (0 = field capacity). irrigation: {date: mm}."""
    prof = soil_profile(district_id, taw_source)
    irrigation = irrigation or {}
    rows = []
    dr = None
    w = weather.set_index("date")
    for d in pd.date_range(start, end, freq="D"):
        st, kc, zr = crop.stage(d.date())
        if st == "off-season":
            rows.append(dict(date=d, stage=st)); continue
        taw = soilwater.taw_mm(prof, zr)
        if dr is None:
            dr = dr0_frac * taw
        else:
            dr = dr * taw / prev_taw if prev_taw > 0 else dr  # keep relative depletion as roots extend
        wx = w.loc[d] if d in w.index else None
        p_mm = float(wx.rain_mm) if wx is not None and pd.notna(wx.rain_mm) else np.nan
        eto = float(wx.eto_mm) if wx is not None and pd.notna(wx.eto_mm) else np.nan
        if np.isnan(p_mm) or np.isnan(eto):
            irr = float(irrigation.get(d.date(), 0.0))  # user irrigation is applied even when weather is missing
            dr = float(np.clip(dr - irr, 0, taw))
            rows.append(dict(date=d, stage=st, kc=kc, zr_m=zr, taw_mm=taw, irrigation_mm=irr, dr_mm=dr,
                             depletion_pct=round(100 * dr / taw, 1), note="missing weather - no ET/rain applied"))
            prev_taw = taw; continue
        etc = kc * eto
        p = float(np.clip(crop.p_tab + 0.04 * (5 - etc), 0.1, 0.8))
        raw = p * taw
        ks = 1.0 if dr <= raw else max(0.0, (taw - dr) / ((1 - p) * taw))
        irr = float(irrigation.get(d.date(), 0.0))
        dr_new = dr - p_mm - irr + ks * etc
        dp = max(0.0, -dr_new)
        dr = float(np.clip(dr_new, 0, taw))
        ks_end = 1.0 if dr <= raw else max(0.0, (taw - dr) / ((1 - p) * taw))
        rows.append(dict(date=d, stage=st, kc=round(kc, 3), zr_m=round(zr, 3), taw_mm=round(taw, 1), raw_mm=round(raw, 1),
                         p=round(p, 3), rain_mm=p_mm, irrigation_mm=irr, eto_mm=eto, etc_adj_mm=round(ks * etc, 2),
                         deep_perc_mm=round(dp, 1), dr_mm=round(dr, 1), depletion_pct=round(100 * dr / taw, 1),
                         ks=round(ks_end, 3), rain_src=wx.rain_src, eto_src=wx.eto_src, kind=wx.kind))
        prev_taw = taw
    df = pd.DataFrame(rows)
    df["stress"] = pd.cut(df.get("ks", pd.Series(dtype=float)), [-0.01, 0.5, 0.75, 0.999, 1.01],
                          labels=["severe", "moderate", "mild", "none"]).astype(str)
    return Result(df, dict(district_id=district_id, crop=crop.name, sow=str(crop.sow), taw_source=taw_source,
                           zr_initial_m=ZR_INITIAL, simplifications="no runoff term, no capillary rise, district-uniform rain"))


def landscape_kc_series(district_id):
    """Observed landscape water-use coefficient = MODIS ET/PET (cropland mask): gap-filled MOD16A2GF, then
    near-real-time MOD16A2 (provisional). Returns daily series (each composite value held over its 8 days)."""
    frames = []
    for prod in ("MOD16A2GF", "MOD16A2"):
        p = SERIES_DIR / prod
        if p.exists():
            r = pd.read_parquet(p, filters=[("district_id", "==", district_id), ("variable", "==", "et_pet_ratio"), ("mask", "==", "cropland")])
            frames.append(r.assign(product=prod))
    r = pd.concat(frames)
    r["date"] = pd.to_datetime(r.date)
    r = r.sort_values(["date", "product"]).drop_duplicates("date", keep="first").set_index("date")
    daily = r["mean"].resample("D").ffill(limit=7).clip(0.05, 1.2)
    return daily, r.index.max()


def district_stress_nowcast(district_id, today: date, horizon_days=10, zr=1.0, p_tab=0.5, taw_source="saxton_rawls"):
    """District-level landscape stress ESTIMATE (no crop needed). This is the configuration validated against SMAP
    (scripts/validation/validate_nowcast.py, kc_mode='landscape'). Days after the latest MODIS ET composite reuse the
    last observed ET/PET (flagged)."""
    smap, (p5, p95) = smap_relative_wetness(district_id)
    smap = smap[smap.index <= pd.Timestamp(today)].dropna(subset=["rel_wetness"])
    t0 = smap.index.max()
    dr0 = 1 - float(smap.loc[t0, "rel_wetness"])
    end = pd.Timestamp(today) + timedelta(days=horizon_days)
    wx = weather_for_district(district_id, t0, end).set_index("date")
    kc_obs, kc_last = landscape_kc_series(district_id)
    taw = soilwater.taw_mm(soil_profile(district_id, taw_source), zr)
    dr = dr0 * taw
    rows = []
    last_kc = float(kc_obs[kc_obs.index <= t0].iloc[-1]) if (kc_obs.index <= t0).any() else 1.0
    for d in pd.date_range(t0, end, freq="D"):
        k = kc_obs.get(d, np.nan)
        kc_src = "MODIS ET/PET observed"
        if np.isnan(k):
            k, kc_src = last_kc, f"persisted from MODIS composite {kc_last.date()}"
        last_kc = k
        wxd = wx.loc[d] if d in wx.index else None
        if wxd is None or pd.isna(wxd.rain_mm) or pd.isna(wxd.eto_mm):
            rows.append(dict(date=d, dr_mm=dr, note="missing weather - state held")); continue
        etc = k * wxd.eto_mm
        p = float(np.clip(p_tab + 0.04 * (5 - etc), 0.1, 0.8))
        ks = 1.0 if dr <= p * taw else max(0.0, (taw - dr) / ((1 - p) * taw))
        dr = float(np.clip(dr - wxd.rain_mm + ks * etc, 0, taw))
        ks_e = 1.0 if dr <= p * taw else max(0.0, (taw - dr) / ((1 - p) * taw))
        rows.append(dict(date=d, landscape_kc=round(k, 3), kc_src=kc_src, rain_mm=wxd.rain_mm, eto_mm=wxd.eto_mm,
                         dr_mm=round(dr, 1), depletion_pct=round(100 * dr / taw, 1), ks=round(ks_e, 3),
                         rain_src=wxd.rain_src, eto_src=wxd.eto_src, kind=wxd.kind))
    df = pd.DataFrame(rows)
    df["stress"] = pd.cut(df.ks, [-0.01, 0.5, 0.75, 0.999, 1.01], labels=["severe", "moderate", "mild", "none"]).astype(str)
    tr = df[df.date == pd.Timestamp(today)]
    meta = dict(district_id=district_id, mode="district landscape stress (validated configuration)", today=str(today),
                initialised_from=f"SMAP L4 root-zone on {t0.date()}", data_age_days=int((pd.Timestamp(today) - t0).days),
                taw_mm=round(taw, 1), taw_source=taw_source, root_zone_m=zr,
                today_stress=None if tr.empty else str(tr.iloc[0].stress),
                today_depletion_pct=None if tr.empty else float(tr.iloc[0].depletion_pct),
                interpretation=("Ks here reflects ADDITIONAL soil-water limitation only: the observed MODIS ET/PET already includes "
                                "stress the vegetation shows, which is reported separately by the ET/PET anomaly (evaporative_stress)."),
                validation="vs SMAP 2016-2024: skill over persistence +0.10 (7 d), +0.25 (14 d); weaker in heavy-rain weeks (no runoff term)")
    return Result(df, meta)


def nowcast(district_id, crop_name, sow: date, today: date, irrigation=None, horizon_days=10, taw_source="saxton_rawls"):
    """Initialise from the latest SMAP day <= today, run observed weather to today, then forecast to today+horizon."""
    crop = Crop(crop_name, sow)
    smap, (p5, p95) = smap_relative_wetness(district_id)
    smap = smap[smap.index <= pd.Timestamp(today)].dropna(subset=["rel_wetness"])
    if smap.empty:
        raise ValueError("no SMAP data before 'today'")
    t0 = smap.index.max()
    if t0.date() < sow:
        t0 = pd.Timestamp(sow); dr0 = 1 - float(smap.loc[smap.index.max(), "rel_wetness"])
    else:
        dr0 = 1 - float(smap.loc[t0, "rel_wetness"])
    end = pd.Timestamp(today) + timedelta(days=horizon_days)
    wx = weather_for_district(district_id, t0, end)
    # The run starts ON the SMAP day: its row is the initial state after that day's water fluxes.
    res = run_balance(district_id, crop, t0.date(), end.date(), dr0, wx, irrigation, taw_source)
    d = res.daily
    today_row = d[d.date == pd.Timestamp(today)]
    fut = d[(d.date > pd.Timestamp(today)) & (d.get("ks", pd.Series(dtype=float)) < 0.999)] if "ks" in d else d.iloc[0:0]
    res.meta.update(initialised_from=f"SMAP L4 root-zone on {t0.date()} (rel. wetness {1 - dr0:.2f}; district SMAP p5={p5:.3f}, p95={p95:.3f})",
                    today=str(today),
                    today_stress=None if today_row.empty else str(today_row.iloc[0].get("stress")),
                    today_ks=None if today_row.empty else float(today_row.iloc[0].get("ks")),
                    days_until_stress=(0 if (not today_row.empty and today_row.iloc[0].get("ks", 1) < 0.999)
                                       else None if fut.empty else int((fut.date.min() - pd.Timestamp(today)).days)),
                    irrigation_assumption=("irrigation events supplied by user" if irrigation
                                           else "NO irrigation assumed - stress for irrigated fields will be overstated"),
                    data_age_days=int((pd.Timestamp(today) - t0).days),
                    weather_sources=d[["rain_src", "eto_src"]].dropna().drop_duplicates().values.tolist() if "rain_src" in d else [])
    return res


def precompute_district_today(today: date | None = None, horizon_days=10):
    """Run the district stress nowcast for all 36 districts; saved for fast map/overview requests."""
    from geocrop.config import NOWCAST_DIR
    today = today or date.today()
    summ, daily = [], []
    for did in range(1, 37):
        try:
            r = district_stress_nowcast(did, today, horizon_days)
        except Exception as e:  # keep going; record the failure
            summ.append(dict(district_id=did, error=f"{type(e).__name__}: {e}")); continue
        m = r.meta
        d = r.daily.assign(district_id=did)
        fut = d[(d.date > pd.Timestamp(today)) & (d.ks < 0.999)]
        summ.append(dict(district_id=did, today=str(today), stress=m["today_stress"], depletion_pct=m["today_depletion_pct"],
                         initialised_from=m["initialised_from"], data_age_days=m["data_age_days"], taw_mm=m["taw_mm"],
                         days_until_stress=0 if m["today_stress"] not in (None, "none") else (None if fut.empty else int((fut.date.min() - pd.Timestamp(today)).days))))
        daily.append(d)
    s = pd.DataFrame(summ); dd = pd.concat(daily, ignore_index=True)
    s.to_parquet(NOWCAST_DIR / "district_today.parquet", index=False)
    dd.to_parquet(NOWCAST_DIR / "district_today_daily.parquet", index=False)
    return s
