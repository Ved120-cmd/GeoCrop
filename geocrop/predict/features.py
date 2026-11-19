"""Leakage-safe feature/target tables for 16- and 32-day water-stress forecasts (district level).

TARGET (proxy, not measured crop stress): NASA SMAP L4 root-zone soil-moisture percentile (vs 2015-2024, same
time of year) at issue date + LEAD days; "dry" = percentile <= 20.

FEATURES use only information that was published by the issue date t (operational latencies):
  SMAP (daily)            latest t-3          IMD/IMERG rain       latest t-1
  NASA POWER weather      latest t-3          MOD13Q1 NDVI/VHI     composite start <= t-32
  MOD11A2 LST             start <= t-16       MOD16A2 ET/PET       start <= t-24
plus climatology known in advance (normal rain over the target window, day of year) and static district soil.
No future weather is used (ECMWF reforecasts are not available); see the model card.
"""
import numpy as np
import pandas as pd

from geocrop.config import INDEX_DIR, PROCESSED, REFERENCE

WEATHER = PROCESSED / "monitor/weather"
LEADS = (16, 32)
LAT = dict(smap=3, rain=1, power=3, ndvi=32, lst=16, et=24)
ISSUE_STEP_DAYS = 3


def _daily(name, cols, filters=None):
    d = pd.read_parquet(name, columns=["date", "district_id", *cols], filters=filters)
    d["date"] = pd.to_datetime(d["date"]).astype("datetime64[ns]")
    return d


def load_inputs():
    sm = _daily(INDEX_DIR / "soil_moisture.parquet", ["sm_rootzone", "sm_percentile"])
    rain = _daily(WEATHER / "rain_imd_extended.parquet", ["precip_imd"]).rename(columns={"precip_imd": "rain"})
    pw = _daily(WEATHER / "power.parquet", ["tmax", "tmin", "rh", "eto"])
    veg = _daily(INDEX_DIR / "vegetation.parquet", ["ndvi_anom", "vhi"])
    lst = _daily(INDEX_DIR / "lst.parquet", ["lst_anom"])
    et = _daily(INDEX_DIR / "evaporative_stress.parquet", ["esi_z"])
    return sm, rain, pw, veg, lst, et


def _static():
    from geocrop.monitor import soilwater
    reg = pd.read_csv(REFERENCE / "regions.csv")
    from geocrop.common.districts import district_table
    t = district_table().merge(reg, on="district")
    taw = {int(d): soilwater.taw_mm(soilwater.profile_for_district_sr(int(d)), 1.0) for d in t.district_id}
    t["taw_1m"] = t.district_id.map(taw)
    t["region_code"] = t.region.astype("category").cat.codes
    return t[["district_id", "taw_1m", "region_code", "region"]]


def _rain_normals(rain):
    """Day-of-year mean daily rain 1991-2020 per district (known in advance)."""
    r = rain[(rain.date >= "1991-01-01") & (rain.date <= "2020-12-31")].copy()
    r["doy"] = r.date.dt.day_of_year.clip(upper=365)
    return r.groupby(["district_id", "doy"]).rain.mean()


def build(issue_dates=None, with_targets=True):
    """Feature table: one row per (district, issue date). If issue_dates is None, every ISSUE_STEP_DAYS from
    2015-05-15 to the last SMAP date."""
    sm, rain, pw, veg, lst, et = load_inputs()
    static = _static()
    normals = _rain_normals(rain)
    out = []
    last_sm = sm.date.max()
    if issue_dates is None:
        issue_dates = pd.date_range("2015-05-15", last_sm + pd.Timedelta(days=LAT["smap"]), freq=f"{ISSUE_STEP_DAYS}D")
    issue_dates = pd.DatetimeIndex(issue_dates).astype("datetime64[ns]")
    for did in range(1, 37):
        s = sm[sm.district_id == did].set_index("date").sort_index()
        r = rain[rain.district_id == did].set_index("date").rain.sort_index()
        p = pw[pw.district_id == did].set_index("date").sort_index()
        full = pd.date_range(min(s.index.min(), r.index.min()), max(issue_dates.max(), last_sm) + pd.Timedelta(days=40), freq="D")
        s = s.reindex(full); r = r.reindex(full); p = p.reindex(full)
        t = issue_dates
        f = pd.DataFrame(index=t)
        f["district_id"] = did
        # --- SMAP state and trend (latest available = t-3)
        def at(series, lag):
            return series.reindex(t - pd.Timedelta(days=lag)).values
        f["sm_pct_now"] = at(s.sm_percentile, LAT["smap"])
        f["sm_now"] = at(s.sm_rootzone, LAT["smap"])
        for k in (7, 14, 30):
            f[f"sm_pct_lag{k}"] = at(s.sm_percentile, LAT["smap"] + k)
        f["sm_change_14d"] = f.sm_now - at(s.sm_rootzone, LAT["smap"] + 14)
        # --- rain sums ending t-1
        csum = r.fillna(0).cumsum()
        for w in (7, 15, 30, 60, 90):
            end = t - pd.Timedelta(days=LAT["rain"]); start = end - pd.Timedelta(days=w)
            f[f"rain_{w}d"] = csum.reindex(end).values - csum.reindex(start).values
        # --- weather means ending t-3
        for c in ("tmax", "rh", "eto"):
            roll = p[c].rolling(14, min_periods=10).mean()
            f[f"{c}_14d"] = roll.reindex(t - pd.Timedelta(days=LAT["power"])).values
        f["eto_30d"] = p.eto.rolling(30, min_periods=20).sum().reindex(t - pd.Timedelta(days=LAT["power"])).values
        # --- satellite composites with publication latency (asof on composite start date)
        for frame, cols, lag in ((veg, ["ndvi_anom", "vhi"], LAT["ndvi"]), (lst, ["lst_anom"], LAT["lst"]), (et, ["esi_z"], LAT["et"])):
            g = frame[frame.district_id == did].sort_values("date")[["date", *cols]]
            key = pd.DataFrame({"key": (t - pd.Timedelta(days=lag)).astype("datetime64[ns]")})
            m = pd.merge_asof(key, g, left_on="key", right_on="date", direction="backward")
            for c in cols:
                f[c] = m[c].values
            f[f"{cols[0]}_age_days"] = (t - m["date"]).dt.days.values if "date" in m else np.nan
        # --- climatology known in advance
        doy = t.day_of_year.values
        f["doy_sin"] = np.sin(2 * np.pi * doy / 365.25); f["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
        nd = normals.loc[did] if did in normals.index.get_level_values(0) else None
        if nd is not None:
            nd = nd.reindex(range(1, 366)).fillna(0).values
            ncum = np.concatenate([[0], np.cumsum(np.concatenate([nd, nd]))])
            for L in LEADS:
                a = np.clip(doy, 1, 365)
                f[f"normal_rain_next{L}d"] = ncum[a - 1 + L] - ncum[a - 1]
        # --- targets
        if with_targets:
            for L in LEADS:
                f[f"y_pct_{L}"] = s.sm_percentile.reindex(t + pd.Timedelta(days=L)).values
        out.append(f.reset_index(names="issue_date"))
    df = pd.concat(out, ignore_index=True).merge(static, on="district_id", how="left")
    return df


FEATURES = ["sm_pct_now", "sm_now", "sm_pct_lag7", "sm_pct_lag14", "sm_pct_lag30", "sm_change_14d",
            "rain_7d", "rain_15d", "rain_30d", "rain_60d", "rain_90d", "tmax_14d", "rh_14d", "eto_14d", "eto_30d",
            "ndvi_anom", "vhi", "lst_anom", "esi_z", "doy_sin", "doy_cos", "taw_1m", "region_code"]


def features_for(lead):
    return FEATURES + [f"normal_rain_next{lead}d"]


FEATURE_LABELS = {
    "sm_pct_now": "Soil moisture now (percentile)", "sm_now": "Soil moisture now (m³/m³)", "sm_pct_lag7": "Soil moisture 1 week earlier",
    "sm_pct_lag14": "Soil moisture 2 weeks earlier", "sm_pct_lag30": "Soil moisture 1 month earlier", "sm_change_14d": "Soil moisture change, last 2 weeks",
    "rain_7d": "Rain, last 7 days", "rain_15d": "Rain, last 15 days", "rain_30d": "Rain, last 30 days", "rain_60d": "Rain, last 60 days",
    "rain_90d": "Rain, last 90 days", "tmax_14d": "Max temperature, last 2 weeks", "rh_14d": "Humidity, last 2 weeks",
    "eto_14d": "Evaporative demand, last 2 weeks", "eto_30d": "Evaporative demand, last month", "ndvi_anom": "Vegetation greenness vs normal",
    "vhi": "Vegetation health index", "lst_anom": "Land temperature vs normal", "esi_z": "Crop water use vs normal",
    "doy_sin": "Time of year", "doy_cos": "Time of year", "taw_1m": "Soil water-holding capacity", "region_code": "Region",
    "normal_rain_next16d": "Normal rain expected (next 16 days)", "normal_rain_next32d": "Normal rain expected (next 32 days)",
}
FEATURE_LABELS_MR = {
    "sm_pct_now": "सध्याचा मातीतील ओलावा", "sm_now": "सध्याचा मातीतील ओलावा", "sm_pct_lag7": "एक आठवड्यापूर्वीचा ओलावा", "sm_pct_lag14": "दोन आठवड्यांपूर्वीचा ओलावा",
    "sm_pct_lag30": "एक महिन्यापूर्वीचा ओलावा", "sm_change_14d": "मागील २ आठवड्यांतील ओलाव्यातील बदल", "rain_7d": "मागील ७ दिवसांचा पाऊस", "rain_15d": "मागील १५ दिवसांचा पाऊस",
    "rain_30d": "मागील ३० दिवसांचा पाऊस", "rain_60d": "मागील ६० दिवसांचा पाऊस", "rain_90d": "मागील ९० दिवसांचा पाऊस", "tmax_14d": "मागील २ आठवड्यांचे कमाल तापमान",
    "rh_14d": "आर्द्रता", "eto_14d": "बाष्पीभवन मागणी", "eto_30d": "बाष्पीभवन मागणी (महिना)", "ndvi_anom": "वनस्पती हिरवेपणा वि. सरासरी", "vhi": "वनस्पती आरोग्य",
    "lst_anom": "जमिनीचे तापमान वि. सरासरी", "esi_z": "पिकाचा पाणी वापर वि. सरासरी", "doy_sin": "वर्षातील वेळ", "doy_cos": "वर्षातील वेळ",
    "taw_1m": "मातीची पाणी धारण क्षमता", "region_code": "विभाग", "normal_rain_next16d": "पुढील १६ दिवसांचा सरासरी पाऊस", "normal_rain_next32d": "पुढील ३२ दिवसांचा सरासरी पाऊस",
}
