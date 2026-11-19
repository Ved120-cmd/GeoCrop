"""Climatologies, anomalies and drought/condition indices per district.

All baselines are frozen (config.BASELINE_*; SPI uses WMO-standard 1991-2020 from IMD) so values do not
drift between runs. Every output row keeps the observation date, the baseline version and a quality flag.

Indices (cropland mask unless noted):
  VCI  = 100 (NDVI - NDVImin) / (NDVImax - NDVImin)          per 16-day composite slot      (Kogan 1995)
  TCI  = 100 (LSTmax - LST) / (LSTmax - LSTmin)              per 8-day slot, daytime LST     (Kogan 1995)
  VHI  = 0.5 VCI + 0.5 TCI (TCI = mean of LST slots starting inside the NDVI composite)
  SM percentile  = rank of SMAP root-zone moisture within baseline days of year +/- 15 d   (all land)
  ESI-like z     = standardized anomaly of ET/PET per 8-day slot
  SPI-1, SPI-3   = gamma-fitted standardized precipitation index on IMD monthly rain (with zero mass)
  Rain departure = % departure of cumulative IMD rain from the 1991-2020 normal (IMD categories)
Caveat: the satellite baseline is only 10 years, so VCI/TCI extremes are less stable than with 30+ years.
"""
import numpy as np
import pandas as pd
from scipy import stats

from geocrop.config import BASELINE_END, BASELINE_START, BASELINE_VERSION, INDEX_DIR, PROCESSED, SERIES_DIR

WEATHER = PROCESSED / "monitor/weather"
MIN_VALID_FRAC = 0.3  # below this a district-date is kept but flagged low-confidence and excluded from alerts


def load_series(product, variable, mask="cropland"):
    df = pd.read_parquet(SERIES_DIR / product, filters=[("variable", "==", variable), ("mask", "==", mask)])
    df["date"] = pd.to_datetime(df["date"])
    if product == "MOD16A2GF" and (SERIES_DIR / "MOD16A2").exists():
        # gap-filled ET is released yearly; after its last date use near-real-time MOD16A2, flagged provisional
        nrt = pd.read_parquet(SERIES_DIR / "MOD16A2", filters=[("variable", "==", variable), ("mask", "==", mask)])
        nrt["date"] = pd.to_datetime(nrt["date"])
        nrt = nrt[nrt.date > df.date.max()].assign(status="provisional")
        df = pd.concat([df, nrt], ignore_index=True)
    return df[["date", "district_id", "mean", "valid_frac", "status"]].rename(columns={"mean": variable})


def _in_baseline(d):
    return (d >= pd.Timestamp(BASELINE_START)) & (d <= pd.Timestamp(BASELINE_END))


def slot_climatology(df, var):
    """Per district and composite slot (day-of-year of composite start): mean, std, min, max over baseline years."""
    df = df.copy()
    df["slot"] = df.date.dt.day_of_year
    ok = _in_baseline(df.date) & (df.valid_frac >= MIN_VALID_FRAC)
    clim = df[ok].groupby(["district_id", "slot"])[var].agg(["mean", "std", "min", "max", "count"]).reset_index()
    return df.merge(clim, on=["district_id", "slot"], how="left")


def vegetation_condition():
    ndvi = slot_climatology(load_series("MOD13Q1", "ndvi"), "ndvi")
    ndvi["ndvi_anom"] = ndvi.ndvi - ndvi["mean"]
    ndvi["ndvi_pct_normal"] = 100 * ndvi.ndvi / ndvi["mean"]
    ndvi["vci"] = (100 * (ndvi.ndvi - ndvi["min"]) / (ndvi["max"] - ndvi["min"])).clip(0, 100)
    lst = slot_climatology(load_series("MOD11A2", "lst_day"), "lst_day")
    lst["tci"] = (100 * (lst["max"] - lst.lst_day) / (lst["max"] - lst["min"])).clip(0, 100)
    lst["lst_anom"] = lst.lst_day - lst["mean"]
    # TCI for each NDVI composite = mean of 8-day LST slots starting within [date, date + 15]
    tci_rows = []
    lst_idx = lst.set_index("date")
    for d in ndvi.date.unique():
        w = lst[(lst.date >= d) & (lst.date <= d + pd.Timedelta(days=15))]
        g = w.groupby("district_id").agg(tci=("tci", "mean"), lst_valid=("valid_frac", "min"))
        g["date"] = d
        tci_rows.append(g.reset_index())
    tci16 = pd.concat(tci_rows, ignore_index=True)
    out = ndvi.merge(tci16, on=["date", "district_id"], how="left")
    out["vhi"] = 0.5 * out.vci + 0.5 * out.tci
    out["low_confidence"] = (out.valid_frac < MIN_VALID_FRAC) | (out.lst_valid < MIN_VALID_FRAC) | out["count"].lt(5)
    out["vhi_class"] = pd.cut(out.vhi, [-1, 10, 20, 30, 40, 101],
                              labels=["extreme", "severe", "moderate", "mild", "no stress"]).astype(str)
    cols = ["date", "district_id", "ndvi", "ndvi_anom", "ndvi_pct_normal", "vci", "tci", "vhi", "vhi_class",
            "valid_frac", "low_confidence", "status"]
    out = out[cols].assign(baseline=BASELINE_VERSION)
    out.to_parquet(INDEX_DIR / "vegetation.parquet", index=False)
    lst[["date", "district_id", "lst_day", "lst_anom", "tci", "valid_frac", "status"]].assign(baseline=BASELINE_VERSION) \
        .to_parquet(INDEX_DIR / "lst.parquet", index=False)
    return out


def evaporative_stress():
    r = slot_climatology(load_series("MOD16A2GF", "et_pet_ratio"), "et_pet_ratio")
    r["esi_z"] = (r.et_pet_ratio - r["mean"]) / r["std"]
    r["low_confidence"] = (r.valid_frac < MIN_VALID_FRAC) | r["count"].lt(5)
    out = r[["date", "district_id", "et_pet_ratio", "esi_z", "valid_frac", "low_confidence", "status"]].assign(baseline=BASELINE_VERSION)
    out.to_parquet(INDEX_DIR / "evaporative_stress.parquet", index=False)
    return out


def soil_moisture_percentile(window=15):
    sm = load_series("SMAP", "sm_rootzone", mask="all")
    sm["doy"] = sm.date.dt.day_of_year
    base = sm[_in_baseline(sm.date) & (sm.valid_frac >= MIN_VALID_FRAC)]
    rows = []
    for did, g in sm.groupby("district_id"):
        b = base[base.district_id == did]
        bd = b.doy.values; bv = b.sm_rootzone.values
        pct = np.full(len(g), np.nan)
        for i, (doy, v) in enumerate(zip(g.doy.values, g.sm_rootzone.values)):
            dd = np.minimum(np.abs(bd - doy), 366 - np.abs(bd - doy))
            ref = bv[(dd <= window) & np.isfinite(bv)]
            if len(ref) >= 30 and np.isfinite(v):
                pct[i] = 100 * (ref < v).mean() + 50 * (ref == v).mean()
        rows.append(g.assign(sm_percentile=pct))
    out = pd.concat(rows, ignore_index=True)
    out["sm_class"] = pd.cut(out.sm_percentile, [-1, 5, 10, 20, 30, 70, 101],
                             labels=["exceptionally dry", "very dry", "dry", "below normal", "normal", "wet"]).astype(str)
    out["low_confidence"] = out.valid_frac < MIN_VALID_FRAC
    out = out[["date", "district_id", "sm_rootzone", "sm_percentile", "sm_class", "valid_frac", "low_confidence", "status"]] \
        .assign(baseline=BASELINE_VERSION)
    out.to_parquet(INDEX_DIR / "soil_moisture.parquet", index=False)
    return out


def _spi(series_mm, base_mask):
    """Gamma SPI with zero-rain mass (McKee 1993; Lloyd-Hughes & Saunders 2002)."""
    x = series_mm.values; b = x[base_mask & np.isfinite(x)]
    q = (b == 0).mean()
    nz = b[b > 0]
    if len(nz) < 10:
        return np.full(len(x), np.nan)
    a, loc, scale = stats.gamma.fit(nz, floc=0)
    cdf = q + (1 - q) * stats.gamma.cdf(np.where(x > 0, x, 0), a, loc=0, scale=scale)
    cdf = np.where(x == 0, q / 2 if q > 0 else 1e-6, cdf)  # zero rain: mid-point of the zero mass
    return stats.norm.ppf(np.clip(cdf, 1e-6, 1 - 1e-6))


def rain_with_nrt_extension():
    """IMD gauge rain, extended past IMD's last published day with IMERG linearly scaled to IMD
    (per district and calendar month, ratio of 2015-2024 totals). Extension rows are flagged provisional."""
    rain = pd.read_parquet(WEATHER / "rain_imd.parquet")
    rain["date"] = pd.to_datetime(rain.date)
    rain["rain_source"] = "IMD"
    last = rain.dropna(subset=["precip_imd"]).date.max()
    p = SERIES_DIR / "IMERG"
    if not p.exists():
        return rain
    im = pd.read_parquet(p, columns=["date", "district_id", "mean", "mask", "variable"], filters=[("mask", "==", "all")])
    im["date"] = pd.to_datetime(im.date)
    im = im[["date", "district_id", "mean"]].rename(columns={"mean": "precip_imerg"})
    both = rain.merge(im, on=["date", "district_id"])
    both = both[(both.date >= "2015-01-01") & (both.date <= "2024-12-31")]
    both["m"] = both.date.dt.month
    tot = both.groupby(["district_id", "m"])[["precip_imd", "precip_imerg"]].sum()
    factor = (tot.precip_imd / tot.precip_imerg.where(tot.precip_imerg > 1)).clip(0.3, 3).fillna(1.0).rename("factor")
    ext = im[im.date > last].copy()
    ext["m"] = ext.date.dt.month
    ext = ext.join(factor, on=["district_id", "m"])
    ext["precip_imd"] = ext.precip_imerg * ext.factor
    ext["rain_source"] = "IMERG scaled to IMD (provisional)"
    return pd.concat([rain, ext[["date", "district_id", "precip_imd", "rain_source"]]], ignore_index=True)


def rainfall_indices():
    rain = rain_with_nrt_extension()
    # persisted so consumers (simulator, nowcast) read one district's rows instead of rebuilding the state series
    rain[["date", "district_id", "precip_imd", "rain_source"]].to_parquet(WEATHER / "rain_imd_extended.parquet", index=False)
    prov_months = set(rain[rain.rain_source != "IMD"].date.dt.to_period("M").astype(str))
    mon = rain.set_index("date").groupby("district_id").precip_imd.resample("MS").sum(min_count=25).reset_index()
    out = []
    for did, g in mon.groupby("district_id"):
        g = g.sort_values("date").reset_index(drop=True)
        base = (g.date >= "1991-01-01") & (g.date <= "2020-12-31")
        for k in (1, 3):
            acc = g.precip_imd.rolling(k, min_periods=k).sum()
            spi = np.full(len(g), np.nan)
            for m in range(1, 13):  # fit per calendar month (end month of the window)
                sel = (g.date.dt.month == m).values
                spi[sel] = _spi(acc[sel], base.values[sel])
            g[f"spi_{k}"] = spi
        out.append(g)
    spi = pd.concat(out, ignore_index=True)
    spi["spi_class"] = pd.cut(spi.spi_3, [-99, -2, -1.5, -1, 1, 1.5, 2, 99],
                              labels=["extremely dry", "severely dry", "moderately dry", "near normal",
                                      "moderately wet", "very wet", "extremely wet"]).astype(str)
    spi["status"] = np.where(spi.date.dt.to_period("M").astype(str).isin(prov_months), "provisional", "final")
    spi = spi.rename(columns={"date": "month"}).assign(baseline="spi_imd_1991_2020")
    spi.to_parquet(INDEX_DIR / "spi.parquet", index=False)

    # Seasonal departure (IMD convention): cumulative rain since 1 June (monsoon) vs 1991-2020 normal
    rain["doy"] = rain.date.dt.day_of_year
    rain["season_year"] = rain.date.dt.year
    jun1 = pd.to_datetime(rain.season_year.astype(str) + "-06-01").dt.day_of_year
    in_season = (rain.date.dt.month >= 6) & (rain.date.dt.month <= 9)
    r = rain[in_season].sort_values("date").copy()
    r["cum"] = r.groupby(["district_id", "season_year"]).precip_imd.cumsum()
    r["season_day"] = r.doy - jun1[in_season].loc[r.index]
    normal = r[(r.season_year >= 1991) & (r.season_year <= 2020)].groupby(["district_id", "season_day"]).cum.mean().rename("cum_normal")
    r = r.join(normal, on=["district_id", "season_day"])
    r["departure_pct"] = 100 * (r.cum - r.cum_normal) / r.cum_normal
    r["departure_class"] = pd.cut(r.departure_pct, [-101, -99.5, -60, -20, 19.5, 59.5, 1e9],
                                  labels=["no rain", "large deficient", "deficient", "normal", "excess", "large excess"]).astype(str)
    r["status"] = np.where(r.rain_source == "IMD", "final", "provisional")
    dep = r[["date", "district_id", "precip_imd", "cum", "cum_normal", "departure_pct", "departure_class", "rain_source", "status"]] \
        .rename(columns={"cum": "monsoon_cum_mm", "cum_normal": "monsoon_normal_mm"})
    dep.to_parquet(INDEX_DIR / "monsoon_departure.parquet", index=False)
    return spi, dep


def build_all():
    for fn in (vegetation_condition, evaporative_stress, soil_moisture_percentile, rainfall_indices):
        r = fn()
        print(fn.__name__, "ok", [x.shape for x in (r if isinstance(r, tuple) else (r,))], flush=True)


if __name__ == "__main__":
    build_all()
