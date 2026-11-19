"""Decoding of each raw product into physical units with quality masking (invalid -> NaN, never 0).

Every decoder takes an open rasterio dataset and returns {variable: float32 array}. Scale factors and
QA rules follow the product user guides:
  MOD13Q1 v061 (NDVI/EVI x0.0001; SummaryQA 0 good, 1 marginal, 2 snow/ice, 3 cloudy)
  MOD11A2 v061 (LST x0.02 K; QC bits0-1 mandatory QA, bits6-7 LST error)
  MOD16A2GF v061 (ET/PET x0.1 kg/m2 per composite; >32700 are fill classes)
  SMAP L4 SPL4SMGP v008 (m3/m3), IMERG V07 Final (mm/day, our daily total)
"""
import re
from datetime import date

import numpy as np

PRODUCTS = {
    # id: (raw dir, file prefix, variables, units)
    "MOD13Q1": ("modis/mod13q1", "MOD13Q1", {"ndvi": "-", "evi": "-"}),
    "MOD11A2": ("modis/mod11a2", "MOD11A2", {"lst_day": "degC", "lst_night": "degC"}),
    "MOD16A2GF": ("modis/mod16a2gf", "MOD16A2GF", {"et": "mm/day", "pet": "mm/day", "et_pet_ratio": "-"}),
    # near-real-time, non-gap-filled ET: provisional until the yearly MOD16A2GF release covers the date
    "MOD16A2": ("modis/mod16a2", "MOD16A2", {"et": "mm/day", "pet": "mm/day", "et_pet_ratio": "-"}),
    "SMAP": ("soil/smap", "SMAP", {"sm_surface": "m3/m3", "sm_rootzone": "m3/m3"}),
    "IMERG": ("weather/gpm", "IMERG", {"precip_imerg": "mm/day"}),
}


def file_date(path) -> date:
    y, m, d = map(int, re.search(r"(\d{4})_(\d{2})_(\d{2})", str(path)).groups())
    return date(y, m, d)


def _band(src, name):
    i = list(src.descriptions).index(name) + 1
    a = src.read(i)
    return a, (a == src.nodata) if src.nodata is not None else np.zeros(a.shape, bool)


def decode_mod13q1(src, d):
    qa, nd = _band(src, "SummaryQA")
    good = (~nd) & np.isin(qa, (0, 1))
    out = {}
    for b, v in (("NDVI", "ndvi"), ("EVI", "evi")):
        a, n = _band(src, b)
        ok = good & ~n & (a >= -2000) & (a <= 10000)
        out[v] = np.where(ok, a * 1e-4, np.nan).astype("float32")
    return out


def decode_mod11a2(src, d):
    out = {}
    for b, q, v in (("LST_Day_1km", "QC_Day", "lst_day"), ("LST_Night_1km", "QC_Night", "lst_night")):
        a, n = _band(src, b)
        qc, nq = _band(src, q)
        mand = qc & 0b11
        err = (qc >> 6) & 0b11
        ok = ~n & ~nq & (a > 0) & np.isin(mand, (0, 1)) & (err <= 1)  # produced, LST error <= 2 K
        out[v] = np.where(ok, a * 0.02 - 273.15, np.nan).astype("float32")
    return out


def decode_mod16a2gf(src, d):
    # Composites are 8 days, except the last of each year (from DOY 361) which runs to 31 Dec.
    start = d
    ndays = 8 if d.timetuple().tm_yday < 361 else (date(d.year, 12, 31) - start).days + 1
    out = {}
    for b, v in (("ET", "et"), ("PET", "pet")):
        a, n = _band(src, b)
        ok = ~n & (a >= 0) & (a <= 32700)
        out[v] = np.where(ok, a * 0.1 / ndays, np.nan).astype("float32")
    with np.errstate(invalid="ignore", divide="ignore"):
        r = out["et"] / out["pet"]
    out["et_pet_ratio"] = np.where(out["pet"] > 0.1, np.clip(r, 0, 1.5), np.nan).astype("float32")
    return out


def decode_smap(src, d):
    out = {}
    for b, v in (("sm_surface", "sm_surface"), ("sm_rootzone", "sm_rootzone")):
        a, n = _band(src, b)
        ok = ~n & np.isfinite(a) & (a >= 0) & (a <= 1)
        out[v] = np.where(ok, a, np.nan).astype("float32")
    return out


def decode_imerg(src, d):
    a, n = _band(src, "precipitation")
    ok = ~n & np.isfinite(a) & (a >= 0)
    return {"precip_imerg": np.where(ok, a, np.nan).astype("float32")}


DECODERS = {"MOD13Q1": decode_mod13q1, "MOD11A2": decode_mod11a2, "MOD16A2GF": decode_mod16a2gf, "MOD16A2": decode_mod16a2gf,
            "SMAP": decode_smap, "IMERG": decode_imerg}
