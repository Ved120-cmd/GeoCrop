"""Turn raw satellite rasters into district time series (incremental, append-only per year).

Output: data/processed/monitor/district_series/<PRODUCT>/year=<YYYY>.parquet with columns
  date, district_id, mask (all|cropland), variable, mean, median, p10, p90, n_valid, n_total,
  valid_frac, source_file, status (final|provisional), processed_at

Usage:
  python -m geocrop.monitor.build_series --product MOD13Q1 [--year 2024]
  python -m geocrop.monitor.build_series --all
"""
import argparse
import glob
from datetime import datetime, timezone

import pandas as pd
import rasterio

from geocrop.common.zonal import zonal_all_and_cropland
from geocrop.config import RAW, SERIES_DIR
from geocrop.monitor.products import DECODERS, PRODUCTS, file_date


def out_path(product, year):
    p = SERIES_DIR / product
    p.mkdir(parents=True, exist_ok=True)
    return p / f"year={year}.parquet"


def process_file(product, path, status="final"):
    d = file_date(path)
    with rasterio.open(path) as src:
        vals = DECODERS[product](src, d)
        crs, tr, shape = src.crs.to_wkt(), src.transform, (src.height, src.width)
    rows = []
    for var, arr in vals.items():
        z = zonal_all_and_cropland(arr, crs, tr, shape, d.year)
        z["variable"] = var
        rows.append(z)
    df = pd.concat(rows, ignore_index=True)
    df.insert(0, "date", pd.Timestamp(d))
    df["valid_frac"] = (df.n_valid / df.n_total.where(df.n_total > 0)).round(4)
    df["source_file"] = str(path).split("data")[-1].replace("\\", "/")
    df["status"] = status
    df["processed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return df


IMERG_FINAL_LAG_DAYS = 120  # IMERG Final Run appears ~3.5 months after observation; newer days are Early/Late run


def status_for(product, d):
    from datetime import date as _date
    if product == "MOD16A2":
        return "provisional"
    if product == "IMERG" and (_date.today() - d).days < IMERG_FINAL_LAG_DAYS:
        return "provisional"
    return "final"


def build(product, years=None, status=None, verbose=True):
    rawdir, prefix, _ = PRODUCTS[product]
    files = sorted(f for f in glob.glob(str(RAW / rawdir / f"{prefix}_*.tif")) if ".part" not in f)
    by_year = {}
    for f in files:
        by_year.setdefault(file_date(f).year, []).append(f)
    n_new = 0
    for y, fl in sorted(by_year.items()):
        if years and y not in years:
            continue
        op = out_path(product, y)
        old = pd.read_parquet(op) if op.exists() else None
        done = set(old.date.dt.date) if old is not None else set()
        todo = [f for f in fl if file_date(f) not in done]
        if not todo:
            continue
        new = [process_file(product, f, status_for(product, file_date(f)) if status is None else status) for f in todo]
        df = pd.concat(([old] if old is not None else []) + new, ignore_index=True).sort_values(["date", "variable", "mask", "district_id"])
        tmp = op.with_suffix(".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(op)
        n_new += len(todo)
        if verbose:
            print(f"{product} {y}: +{len(todo)} dates (total {df.date.nunique()})", flush=True)
    return n_new


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", choices=list(PRODUCTS)); ap.add_argument("--all", action="store_true")
    ap.add_argument("--year", type=int, nargs="*")
    a = ap.parse_args()
    for p in (PRODUCTS if a.all else [a.product]):
        build(p, years=a.year)
