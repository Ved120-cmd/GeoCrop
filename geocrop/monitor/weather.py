"""District daily weather: rainfall (IMD, CHIRPS; IMERG comes from build_series), IMD temperature,
NASA POWER meteorology and FAO-56 reference ET.

Output (data/processed/monitor/weather/):
  rain_imd.parquet       date, district_id, precip_imd (mm, 24 h ending 08:30 IST on `date`), coverage
  rain_chirps.parquet    date, district_id, precip_chirps (mm, UTC day)
  temp_imd.parquet       date, district_id, tmax_imd, tmin_imd (degC)
  power.parquet          date, district_id, tmax, tmin, rh, u2, rs, precip_power, eto, eto_method
Usage: python -m geocrop.monitor.weather [--only imd chirps temp power]
"""
import argparse
import glob

import numpy as np
import pandas as pd
import xarray as xr

from geocrop.common.eto import hargreaves, penman_monteith
from geocrop.common.gridweights import district_means, grid_weights
from geocrop.config import INTERIM, PROCESSED, RAW

OUT = PROCESSED / "monitor/weather"
OUT.mkdir(parents=True, exist_ok=True)
BBOX = dict(lat=(15.0, 23.0), lon=(72.0, 81.5))


def _to_long(arr, dates, name, cov=None):
    df = pd.DataFrame(arr, index=pd.DatetimeIndex(dates, name="date"), columns=np.arange(1, 37))
    df.columns.name = "district_id"
    df = df.reset_index().melt(id_vars="date", var_name="district_id", value_name=name)
    df["district_id"] = df.district_id.astype("int16")
    df = df.sort_values(["date", "district_id"]).reset_index(drop=True)
    if cov is not None:
        df["coverage"] = np.tile(np.minimum(cov, 1), len(dates))
    return df


def imd_rain():
    frames = []
    for f in sorted(glob.glob(str(RAW / "weather/imd/rain_0p25/ind*_rfp25.nc"))):
        ds = xr.open_dataset(f)
        lat = ds.LATITUDE.values; lon = ds.LONGITUDE.values
        sub = ds.RAINFALL.sel(LATITUDE=slice(*BBOX["lat"]), LONGITUDE=slice(*BBOX["lon"]))
        W = grid_weights(sub.LATITUDE.values, sub.LONGITUDE.values)
        a = sub.values.astype("float32")
        a[a < 0] = np.nan  # IMD missing = -999
        m, den = district_means(a, W)
        frames.append(_to_long(m, pd.to_datetime(sub.TIME.values), "precip_imd"))
        ds.close()
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(OUT / "rain_imd.parquet", index=False)
    return df


def chirps_rain():
    frames = []
    for f in sorted(glob.glob(str(RAW / "weather/chirps/global_daily_p25/*.nc"))):
        ds = xr.open_dataset(f)
        sub = ds.precip.sel(latitude=slice(*BBOX["lat"]), longitude=slice(*BBOX["lon"]))
        W = grid_weights(sub.latitude.values, sub.longitude.values)
        a = sub.values.astype("float32"); a[a < 0] = np.nan
        m, _ = district_means(a, W)
        frames.append(_to_long(m, pd.to_datetime(sub.time.values), "precip_chirps"))
        ds.close()
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(OUT / "rain_chirps.parquet", index=False)
    return df


def imd_temp():
    out = None
    for var in ("tmax", "tmin"):
        frames = []
        for f in sorted(glob.glob(str(INTERIM / f"imd_temp_1deg/imd_{var}_1deg_*.nc"))):
            ds = xr.open_dataset(f)
            sub = ds[var].sel(lat=slice(14, 24), lon=slice(71, 82))
            W = grid_weights(sub.lat.values, sub.lon.values, ss=40)
            m, _ = district_means(sub.values.astype("float32"), W)
            frames.append(_to_long(m, pd.to_datetime(sub.time.values), f"{var}_imd"))
            ds.close()
        d = pd.concat(frames, ignore_index=True)
        out = d if out is None else out.merge(d, on=["date", "district_id"])
    out.to_parquet(OUT / "temp_imd.parquet", index=False)
    return out


def power():
    """ETo is computed per POWER cell (PM where radiation exists, else Hargreaves), then area-averaged."""
    df = pd.read_csv(RAW / "weather/nasa_power/power_daily_mh_2015_2025.csv", parse_dates=["date"])
    recent = RAW / "weather/nasa_power/power_daily_mh_recent.csv"  # rolling window refreshed by the update job
    if recent.exists():
        r = pd.read_csv(recent, parse_dates=["date"])
        df = pd.concat([df[~df.date.isin(r.date.unique())], r], ignore_index=True)
    for c in ("T2M", "T2M_MAX", "T2M_MIN", "RH2M", "PRECTOTCORR", "WS2M", "ALLSKY_SFC_SW_DWN"):
        df.loc[df[c] == -999, c] = np.nan
    df = df.rename(columns={"T2M_MAX": "tmax", "T2M_MIN": "tmin", "RH2M": "rh", "WS2M": "u2",
                            "ALLSKY_SFC_SW_DWN": "rs", "PRECTOTCORR": "precip_power"})
    doy = df.date.dt.day_of_year.values
    pm = penman_monteith(df.tmax.values, df.tmin.values, df.rh.values, df.u2.values, df.rs.values,
                         df.lat.values, doy, df.elev_m.values)
    hg = hargreaves(df.tmax.values, df.tmin.values, df.lat.values, doy)
    df["eto"] = np.where(np.isfinite(pm), pm, hg)
    df["eto_pm"] = np.where(np.isfinite(pm), 1.0, 0.0)  # fraction of cells using Penman-Monteith
    lats = np.sort(df.lat.unique()); lons = np.sort(df.lon.unique())
    # complete regular grid (POWER cells outside MH were not requested -> NaN)
    full_lat = np.round(np.arange(lats.min(), lats.max() + 0.01, 0.5), 3)
    full_lon = np.round(np.arange(lons.min(), lons.max() + 0.01, 0.625), 4)
    W = grid_weights(full_lat, full_lon)
    dates = np.sort(df.date.unique())
    res = {"date": [], "district_id": []}
    cols = ["tmax", "tmin", "rh", "u2", "rs", "precip_power", "eto", "eto_pm"]
    cube = {c: np.full((len(dates), len(full_lat), len(full_lon)), np.nan, "float32") for c in cols}
    ti = pd.Index(dates).get_indexer(df.date); yi = np.searchsorted(full_lat, df.lat.round(3)); xi = np.searchsorted(full_lon, df.lon.round(4))
    for c in cols:
        cube[c][ti, yi, xi] = df[c].values
    out = None
    for c in cols:
        m, _ = district_means(cube[c], W)
        d = _to_long(m, dates, c)
        out = d if out is None else out.merge(d, on=["date", "district_id"])
    out["eto_method"] = np.where(out.eto_pm >= 0.999, "penman_monteith", np.where(out.eto_pm <= 0.001, "hargreaves", "mixed"))
    out = out.drop(columns="eto_pm")
    out.to_parquet(OUT / "power.parquet", index=False)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--only", nargs="*", default=["imd", "chirps", "temp", "power"])
    a = ap.parse_args()
    for k, fn in (("imd", imd_rain), ("chirps", chirps_rain), ("temp", imd_temp), ("power", power)):
        if k in a.only:
            d = fn(); print(k, d.shape, d.date.min().date(), d.date.max().date(), flush=True)
