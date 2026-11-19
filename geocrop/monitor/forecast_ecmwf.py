"""ECMWF IFS open-data forecast -> daily district rain and reference ET (days 0-10).

Source: ECMWF open data (https://data.ecmwf.int/forecasts/), CC BY 4.0 - attribute ECMWF. No account needed.
This is the real-time forecast only; it is NOT the reforecast archive needed for model training.

Daily values use UTC days (IST = UTC+5:30; documented, not corrected).
  tmax/tmin  : max/min of instantaneous 2 m temperature at 3-hourly steps (6-hourly after step 144)
  rh_mean    : 100 * mean(e(Td)) / es(tmax, tmin)
  u2         : 10 m wind speed x 4.87 / ln(67.8*10 - 5.42)            (FAO-56 eq. 47)
  rs         : daily difference of accumulated ssrd / 1e6             (MJ m-2 day-1)
  precip     : daily difference of accumulated tp x 1000              (mm)
  eto_fc     : FAO-56 Penman-Monteith with these inputs
Outputs: data/processed/monitor/weather/ecmwf_forecast.parquet (latest run),
         data/processed/monitor/weather/ecmwf_forecast_archive.parquet (all runs, for verification)
"""
import shutil
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import xarray as xr

from geocrop.common.eto import penman_monteith, sat_vp
from geocrop.common.gridweights import district_means, grid_weights
from geocrop.common.districts import districts
from geocrop.config import PROCESSED, RAW, SCRATCH

OUT = PROCESSED / "monitor/weather"
BBOX = (15.0, 23.0, 72.0, 81.5)  # lat_min, lat_max, lon_min, lon_max
STEPS_INST = list(range(0, 145, 3)) + list(range(150, 241, 6))
STEPS_ACC = list(range(0, 241, 24))


def _download(workdir):
    from ecmwf.opendata import Client
    c = Client(source="ecmwf")
    run = c.latest(type="fc", step=240, param="2t")
    files = {}
    for params, steps, name in ((["2t", "2d", "10u", "10v"], STEPS_INST, "inst"), (["tp", "ssrd"], STEPS_ACC, "acc")):
        target = workdir / f"{name}.grib2"
        c.retrieve(date=run, type="fc", step=steps, param=params, target=str(target))
        files[name] = target
    return run, files


def _open(path, short):
    ds = xr.open_dataset(path, engine="cfgrib", backend_kwargs={"filter_by_keys": {"shortName": short}, "indexpath": ""})
    lon = ds.longitude
    ds = ds.assign_coords(longitude=((lon + 180) % 360) - 180).sortby("longitude")
    return ds[list(ds.data_vars)[0]].sel(latitude=slice(BBOX[1], BBOX[0]), longitude=slice(BBOX[2], BBOX[3])).load()


def _district_elevation_lat():
    pw = pd.read_csv(RAW / "weather/nasa_power/power_daily_mh_2015_2025.csv", usecols=["lat", "lon", "elev_m"]).drop_duplicates()
    g = districts().to_crs(32643)
    lat = g.geometry.centroid.to_crs(4326).y.values
    lats = np.round(np.arange(pw.lat.min(), pw.lat.max() + 0.01, 0.5), 3)
    lons = np.round(np.arange(pw.lon.min(), pw.lon.max() + 0.01, 0.625), 4)
    grid = np.full((len(lats), len(lons)), np.nan, "float32")
    grid[np.searchsorted(lats, pw.lat.round(3)), np.searchsorted(lons, pw.lon.round(4))] = pw.elev_m.values
    elev, _ = district_means(grid, grid_weights(lats, lons))
    return elev, lat


def build(keep_grib=False):
    work = SCRATCH / f"ecmwf_{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        run, files = _download(work)
        t2 = _open(files["inst"], "2t") - 273.15
        td = _open(files["inst"], "2d") - 273.15
        u = _open(files["inst"], "10u"); v = _open(files["inst"], "10v")
        tp = _open(files["acc"], "tp"); ssrd = _open(files["acc"], "ssrd")
        vt = pd.to_datetime(t2.valid_time.values)
        day = vt.floor("D")
        lat, lon = t2.latitude.values, t2.longitude.values
        W = grid_weights(lat, lon)
        rows = []
        elev, dlat = _district_elevation_lat()
        acc_vt = pd.to_datetime(tp.valid_time.values)
        for d in sorted(set(day)):
            sel = np.asarray(day == d)
            if sel.sum() < 4:  # need >= 4 instants for a meaningful daily max/min (drops the trailing partial day)
                continue
            i0 = np.where(acc_vt == d)[0]; i1 = np.where(acc_vt == d + pd.Timedelta(days=1))[0]
            if not len(i0) or not len(i1):
                continue
            tmax = t2.values[sel].max(0); tmin = t2.values[sel].min(0)
            ea = sat_vp(td.values[sel]).mean(0)
            es = (sat_vp(tmax) + sat_vp(tmin)) / 2
            u10 = np.sqrt(u.values[sel] ** 2 + v.values[sel] ** 2).mean(0)
            prec = (tp.values[i1[0]] - tp.values[i0[0]]) * 1000
            rs = (ssrd.values[i1[0]] - ssrd.values[i0[0]]) / 1e6
            fields = dict(tmax_fc=tmax, tmin_fc=tmin, rh_fc=np.clip(100 * ea / es, 1, 100), u2_fc=u10 * 4.87 / np.log(67.8 * 10 - 5.42),
                          precip_fc=np.maximum(prec, 0), rs_fc=np.maximum(rs, 0))
            dm = {k: district_means(f.astype("float32"), W)[0] for k, f in fields.items()}
            eto = penman_monteith(dm["tmax_fc"], dm["tmin_fc"], dm["rh_fc"], dm["u2_fc"], dm["rs_fc"], dlat, d.day_of_year, elev)
            rows.append(pd.DataFrame({"date": d, "district_id": np.arange(1, 37), **dm, "eto_fc": eto}))
        df = pd.concat(rows, ignore_index=True)
        df["run"] = pd.Timestamp(run)
        df["lead_day"] = (df.date - df.run.dt.floor("D")).dt.days
        df["source"] = "ECMWF IFS open data 0.25deg (CC BY 4.0)"
        df.to_parquet(OUT / "ecmwf_forecast.parquet", index=False)
        arch = OUT / "ecmwf_forecast_archive.parquet"
        if arch.exists():
            old = pd.read_parquet(arch)
            df_a = pd.concat([old[old.run != df.run.iloc[0]], df], ignore_index=True)
        else:
            df_a = df
        df_a.to_parquet(arch, index=False)
        return df
    finally:
        if not keep_grib:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    d = build()
    print(d.run.iloc[0], d.date.min().date(), "->", d.date.max().date(), d.shape)
    print(d.groupby("date")[["precip_fc", "eto_fc", "tmax_fc", "tmin_fc", "rh_fc"]].mean().round(2).to_string())
