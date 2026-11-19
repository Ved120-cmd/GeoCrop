"""Convert IMD 1-degree daily Tmax/Tmin binary (.GRD) files to CF-style NetCDF (originals untouched).

IMD format (imdpune.gov.in Max_1_Bin.html): 31 x 31 float32 grid per day, little-endian, longitude fastest,
first point 7.5N 67.5E, 1-degree spacing, missing value 99.9.

Usage: python scripts/preprocessing/imd_temp_to_netcdf.py
Output: data/interim/imd_temp_1deg/imd_{tmax|tmin}_1deg_{year}.nc
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data/raw/weather/imd/temp_1deg"
OUT = ROOT / "data/interim/imd_temp_1deg"
LAT = 7.5 + np.arange(31)
LON = 67.5 + np.arange(31)


def convert(f: Path):
    var, year = f.stem.split("_")
    a = np.fromfile(f, dtype="<f4")
    nd = a.size // (31 * 31)
    days = pd.date_range(f"{year}-01-01", periods=nd, freq="D")
    if days[-1].year != int(year):
        raise ValueError(f"{f.name}: {nd} records inconsistent with year {year}")
    a = a.reshape(nd, 31, 31).astype("float32")
    a[a > 90] = np.nan  # 99.9 = missing (outside India / no data); never zero-filled
    name = {"maxtemp": "tmax", "mintemp": "tmin"}[var]
    da = xr.DataArray(a, dims=("time", "lat", "lon"), coords=dict(time=days, lat=LAT, lon=LON), name=name,
                      attrs=dict(units="degC", long_name=f"daily {'maximum' if name == 'tmax' else 'minimum'} temperature",
                                 source="IMD Pune 1.0 deg gridded temperature (Srivastava et al. 2009)", original_file=f.name,
                                 missing_value_original=99.9, value_type="measured (gridded station interpolation)"))
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"imd_{name}_1deg_{year}.nc"
    da.to_netcdf(out, encoding={name: {"zlib": True, "complevel": 4}})
    return out, nd


if __name__ == "__main__":
    for f in sorted(SRC.glob("*.GRD")):
        try:
            out, nd = convert(f)
            print("ok", out.name, nd, "days")
        except Exception as e:
            print("FAILED", f.name, e, file=sys.stderr)
