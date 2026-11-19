"""District zonal statistics on a product's native grid, optionally restricted to cropland.

The cropland mask comes from MODIS MCD12Q1 (IGBP classes 12/14) for the matching year, resampled to the
target grid as a cropland *fraction* (average of 500 m pixels); a target pixel counts as cropland when
fraction >= 0.5. This is broad land cover, not crop type.
"""
import glob
import re
from functools import lru_cache

import numpy as np
import pandas as pd

from geocrop.common.districts import label_raster
from geocrop.config import CROPLAND_CLASSES, LABEL_CACHE, RAW

STATS = ("mean", "median", "p10", "p90", "n_valid", "n_total")


@lru_cache(maxsize=16)
def _lc_files():
    out = {}
    for f in glob.glob(str(RAW / "modis/mcd12q1/MCD12Q1_*.tif")):
        y = int(re.search(r"MCD12Q1_(\d{4})", f).group(1))
        out[y] = f
    return out


def cropland_fraction(year: int, crs_wkt, transform, shape):
    """Cropland fraction (0-1, NaN outside data) on the target grid, cached per (year, grid)."""
    import hashlib
    import rasterio
    from rasterio.warp import Resampling, reproject
    files = _lc_files()
    y = min(files, key=lambda k: abs(k - year))  # nearest available year
    key = hashlib.sha1(f"{y}|{crs_wkt}|{tuple(transform)[:6]}|{shape}".encode()).hexdigest()[:16]
    cache = LABEL_CACHE / f"cropfrac_{key}.npy"
    if cache.exists():
        return np.load(cache)
    with rasterio.open(files[y]) as src:
        lc = src.read(1)
        nod = src.nodata
        crop = np.where(lc == nod, np.nan, np.isin(lc, CROPLAND_CLASSES).astype("float32"))
        dst = np.full(shape, np.nan, dtype="float32")
        reproject(crop, dst, src_transform=src.transform, src_crs=src.crs, dst_transform=transform, dst_crs=crs_wkt,
                  resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
    np.save(cache, dst)
    return dst


def _stats_from_sorted(vs, ls, n_total):
    """vs/ls sorted by (district, value). Linear-interpolated quantiles identical to numpy/pandas defaults."""
    n = np.bincount(ls, minlength=37)[1:]
    start = np.concatenate(([0], np.cumsum(n)[:-1]))
    sums = np.bincount(ls, weights=vs, minlength=37)[1:]
    has = n > 0

    def q(p):
        out = np.full(36, np.nan)
        pos = start[has] + p * (n[has] - 1)
        lo = np.floor(pos).astype(int); hi = np.ceil(pos).astype(int)
        out[has] = vs[lo] + (vs[hi] - vs[lo]) * (pos - lo)
        return out

    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(has, sums / np.maximum(n, 1), np.nan)
    return pd.DataFrame({"district_id": np.arange(1, 37), "mean": mean, "median": q(0.5), "p10": q(0.1),
                         "p90": q(0.9), "n_valid": n.astype("int32"), "n_total": n_total})


def zonal_masks(values: np.ndarray, labels: np.ndarray, masks: dict) -> pd.DataFrame:
    """Statistics per district for several pixel masks with ONE sort: filtering a sorted array keeps it sorted.

    values: float array, NaN = invalid. labels: district ids (0 = outside). masks: {name: bool array or None}.
    """
    inside = labels > 0
    lab = labels[inside]
    v = values[inside]
    ok = ~np.isnan(v)
    order = np.argsort(v[ok], kind="quicksort")
    order = order[np.argsort(lab[ok][order], kind="stable")]
    vs = v[ok][order].astype("float64"); ls = lab[ok][order]
    out = []
    for name, m in masks.items():
        if m is None:
            df = _stats_from_sorted(vs, ls, np.bincount(lab, minlength=37)[1:])
        else:
            mi = m[inside]
            keep = mi[ok][order]
            df = _stats_from_sorted(vs[keep], ls[keep], np.bincount(lab[mi], minlength=37)[1:])
        df["mask"] = name
        out.append(df)
    return pd.concat(out, ignore_index=True)


def zonal(values, labels, extra_mask=None):
    """Single-mask convenience wrapper."""
    m = None if extra_mask is None else extra_mask
    return zonal_masks(values, labels, {"x": m}).drop(columns="mask")


def zonal_all_and_cropland(values, crs_wkt, transform, shape, year):
    labels = label_raster(crs_wkt, transform, shape)
    frac = cropland_fraction(year, crs_wkt, transform, shape)
    return zonal_masks(values, labels, {"all": None, "cropland": np.nan_to_num(frac, nan=0) >= 0.5})
