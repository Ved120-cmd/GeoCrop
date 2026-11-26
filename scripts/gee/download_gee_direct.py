"""Download Earth Engine products for Maharashtra directly to disk (no Google Drive), 2015-2025.

* Native projection and pixel grid: each image is requested with the product's own CRS and crs_transform,
  tiled into requests under the EE size limit, and the tiles merged locally (grids align exactly).
* Clipped to the Maharashtra polygon (buffered 2 km); outside/masked pixels are written as an explicit
  NODATA value (never 0), and recorded in the GeoTIFF tags.
* Raw integers are kept (no scale factors applied); scale/offset are written to tags.
* Resumable: dates whose output file exists are skipped. Scratch tiles go to D:\\geocrop_work\\tmp.

Usage:
  python scripts/gee/download_gee_direct.py --project YOUR_PROJECT --product MOD13Q1 --dry-run
  python scripts/gee/download_gee_direct.py --project YOUR_PROJECT --product MOD13Q1 [--start 2015-01-01 --end 2026-01-01] [--limit 2]
"""
import argparse, csv, hashlib, io, json, math, os, sys, time, zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # project root, for the geocrop package
from geocrop.common.safe_http import safe_get

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path(os.environ.get("GEOCROP_SCRATCH", r"D:\geocrop_work\tmp\gee_tiles"))
LOG = ROOT / "reports/download_logs/download_log.csv"
MAX_BYTES = 24_000_000  # stay well under EE's ~48 MB getDownloadURL limit

# product: collection, bands, cast, nodata, scale info, dest, aggregation
PRODUCTS = {
    "MOD13Q1": dict(col="MODIS/061/MOD13Q1", bands=["NDVI", "EVI", "SummaryQA", "DayOfYear"], cast="int16", nodata=-32768,
                    scale={"NDVI": 0.0001, "EVI": 0.0001}, dest="data/raw/modis/mod13q1",
                    note="DetailedQA omitted (uint16 bitfield; available on request); SummaryQA kept: 0 good,1 marginal,2 snow,3 cloudy"),
    "MOD11A2": dict(col="MODIS/061/MOD11A2", bands=["LST_Day_1km", "LST_Night_1km", "QC_Day", "QC_Night"], cast="uint16", nodata=65535,
                    scale={"LST_Day_1km": 0.02, "LST_Night_1km": 0.02}, dest="data/raw/modis/mod11a2",
                    note="LST in Kelvin after x0.02; subtract 273.15 for Celsius. 0 = no retrieval in source."),
    "MOD16A2GF": dict(col="MODIS/061/MOD16A2GF", bands=["ET", "PET", "ET_QC"], cast="int16", nodata=-32768,
                      scale={"ET": 0.1, "PET": 0.1}, dest="data/raw/modis/mod16a2gf",
                      note="kg/m2/8day after x0.1; source fill values 32761-32767 preserved as-is"),
    "MOD16A2": dict(col="MODIS/061/MOD16A2", bands=["ET", "PET", "ET_QC"], cast="int16", nodata=-32768,
                    scale={"ET": 0.1, "PET": 0.1}, dest="data/raw/modis/mod16a2",
                    note="NON-gap-filled 8-day ET (near real time). PROVISIONAL: replaced by MOD16A2GF once the yearly gap-filled product is released."),
    "MCD12Q1": dict(col="MODIS/061/MCD12Q1", bands=["LC_Type1", "LC_Type2", "QC", "LW"], cast="uint8", nodata=255,
                    scale={}, dest="data/raw/modis/mcd12q1", note="IGBP (Type1) and UMD (Type2) classes - broad land cover, NOT crop type"),
    "SMAP": dict(col="NASA/SMAP/SPL4SMGP/008", bands=["sm_surface", "sm_rootzone", "sm_profile"], cast="float32", nodata=-9999.0,
                 scale={}, dest="data/raw/soil/smap", agg="daily_mean",
                 note="Daily mean of 3-hourly SPL4SMGP v008 (m3/m3). Model-assimilated estimate; NOT ground-truth crop stress."),
    "IMERG": dict(col="NASA/GPM_L3/IMERG_V07", bands=["precipitation"], cast="float32", nodata=-9999.0,
                  scale={}, dest="data/raw/weather/gpm", agg="daily_sum_mmhr",
                  note="Daily total mm = mean of half-hourly mm/hr x 24 (UTC day). IMERG Final Run V07."),
}


def log(res, url, path, status, err="", lic="NASA EOSDIS open data via Google Earth Engine"):
    p = Path(path) if path else None
    size = p.stat().st_size if p and p.exists() else ""
    chk = hashlib.sha256(p.read_bytes()).hexdigest() if p and p.exists() else ""
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([res, url, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                str(p.relative_to(ROOT)) if p else "", size, chk, status, str(err)[:300], lic])


def mh_geometry(ee):
    import geopandas as gpd
    g = gpd.read_file(ROOT / "data/interim/boundaries/maharashtra_state.geojson").to_crs(4326)
    geom = g.geometry.union_all().simplify(0.005).buffer(0.02)
    return ee.Geometry(json.loads(gpd.GeoSeries([geom]).to_json())["features"][0]["geometry"]), geom.bounds


def build_collection(ee, spec, start, end, region):
    col = ee.ImageCollection(spec["col"])
    agg = spec.get("agg")
    if not agg:
        c = col.filterDate(start, end).filterBounds(region).select(spec["bands"])
        # projection from the full collection: the filtered one may be empty (nothing new yet)
        return c, col.first().select(spec["bands"][0]).projection()
    proj = col.first().select(spec["bands"][0]).projection()
    s = ee.Date(start)
    n = ee.Date(end).difference(s, "day").toInt()

    def day(i):
        d = s.advance(i, "day")
        sub = col.filterDate(d, d.advance(1, "day")).select(spec["bands"])
        img = sub.mean()
        if agg == "daily_sum_mmhr":
            img = img.multiply(24)
        return (img.set("system:time_start", d.millis()).set("system:index", d.format("YYYY_MM_dd"))
                .set("n_obs", sub.size()))
    c = ee.ImageCollection(ee.List.sequence(0, n.subtract(1)).map(day)).filter(ee.Filter.gt("n_obs", 0))
    return c, proj


def cast(img, t):
    return {"int16": img.toInt16, "uint16": img.toUint16, "uint8": img.toUint8, "float32": img.toFloat}[t]()


def tiles_for(bounds, transform, nbands, bpp):
    """Split lon/lat bounds into tiles whose pixel payload stays below MAX_BYTES."""
    import pyproj
    minx, miny, maxx, maxy = bounds
    # approximate pixel size in degrees from the projection's scale
    px_m = abs(transform[0])
    deg = px_m / 111_320 if px_m > 1 else px_m
    w, h = (maxx - minx) / deg, (maxy - miny) / deg
    total = w * h * nbands * bpp * 1.3
    n = max(1, math.ceil(math.sqrt(total / MAX_BYTES)))
    xs = [minx + (maxx - minx) * i / n for i in range(n + 1)]
    ys = [miny + (maxy - miny) * j / n for j in range(n + 1)]
    return [(xs[i], ys[j], xs[i + 1], ys[j + 1]) for i in range(n) for j in range(n)]


def fetch_tile(url, dest, retries=5):
    for i in range(retries):
        try:
            r = safe_get(url, timeout=300)
            if r.status_code == 429:
                time.sleep(30 * (i + 1)); continue
            r.raise_for_status()
            data = r.content
            if data[:2] == b"PK":  # zipped GeoTIFF
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    data = z.read([n for n in z.namelist() if n.endswith(".tif")][0])
            dest.write_bytes(data); return dest
        except Exception as e:
            err = e; time.sleep(10 * (i + 1))
    raise RuntimeError(f"tile failed: {err}")


def process(ee, spec, prod, img_id, img, proj_info, tiles, out):
    import rasterio
    from rasterio.merge import merge
    if out.exists():
        return "skip"
    tdir = SCRATCH / prod / img_id; tdir.mkdir(parents=True, exist_ok=True)
    paths = []
    for k, (x0, y0, x1, y1) in enumerate(tiles):
        rect = ee.Geometry.Rectangle([x0, y0, x1, y1], "EPSG:4326", False)
        url = img.getDownloadURL(dict(bands=spec["bands"], region=rect, crs=proj_info["crs"],
                                      crs_transform=proj_info["transform"], format="GEO_TIFF", filePerBand=False))
        paths.append(fetch_tile(url, tdir / f"t{k}.tif"))
    # Exact merge on the shared native grid. Raw values are copied as-is: EE tiles may declare nodata=0 for
    # unsigned types, and a mask-aware merge would then destroy valid zeros (e.g. QC=0 'good quality').
    import numpy as np
    from rasterio.transform import Affine
    srcs = [rasterio.open(p) for p in paths]
    t0 = srcs[0].transform
    px, py = t0.a, t0.e
    x0 = min(s.transform.c for s in srcs); y0 = max(s.transform.f for s in srcs)
    x1 = max(s.transform.c + s.width * px for s in srcs); y1 = min(s.transform.f + s.height * py for s in srcs)
    W, H = int(round((x1 - x0) / px)), int(round((y1 - y0) / py))
    arr = np.full((srcs[0].count, H, W), spec["nodata"], dtype=srcs[0].dtypes[0])
    for s in srcs:
        c = int(round((s.transform.c - x0) / px)); r = int(round((s.transform.f - y0) / py))
        arr[:, r:r + s.height, c:c + s.width] = s.read(masked=False)
    tr = Affine(px, 0, x0, 0, py, y0)
    # Outside Maharashtra -> NODATA, decided locally on the native grid (EE fills outside-footprint pixels
    # with 0 / -inf depending on dtype, which would be indistinguishable from real zeros).
    import geopandas as gpd
    from rasterio.features import geometry_mask
    shp = gpd.GeoSeries([MH_SHAPE], crs=4326).to_crs(srcs[0].crs.to_wkt())
    outside = geometry_mask(list(shp.geometry), out_shape=(H, W), transform=tr, all_touched=True)
    arr[:, outside] = spec["nodata"]
    prof = srcs[0].profile.copy()
    for s in srcs: s.close()
    prof.update(driver="GTiff", height=arr.shape[1], width=arr.shape[2], transform=tr, nodata=spec["nodata"], count=arr.shape[0],
                compress="deflate", predictor=2 if spec["cast"] != "float32" else 3, tiled=True, blockxsize=256, blockysize=256)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part.tif")
    with rasterio.open(tmp, "w", **prof) as dst:
        dst.write(arr)
        for i, b in enumerate(spec["bands"], 1):
            dst.set_band_description(i, b)
        dst.update_tags(source=f"Google Earth Engine {spec['col']}", image_id=img_id, retrieved=datetime.now(timezone.utc).isoformat(),
                        scale_factors=json.dumps(spec["scale"]), nodata_meaning="outside Maharashtra or masked in source (never zero-filled)",
                        note=spec["note"], value_type="satellite-derived estimate (raw integers, unscaled)" if spec["cast"] != "float32" else "model/estimate")
    os.replace(tmp, out)
    for p in paths: p.unlink()
    tdir.rmdir()
    return "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True); ap.add_argument("--product", required=True, choices=PRODUCTS)
    ap.add_argument("--start", default="2015-01-01"); ap.add_argument("--end", default="2026-01-01")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--limit", type=int); ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    import ee
    ee.Initialize(project=a.project)
    ee.data.setDeadline(180_000)  # a stalled EE call fails (and is retried) instead of hanging forever
    spec = PRODUCTS[a.product]
    region, bounds = mh_geometry(ee)
    global MH_SHAPE
    import geopandas as gpd
    MH_SHAPE = gpd.read_file(ROOT / "data/interim/boundaries/maharashtra_state.geojson").to_crs(4326).geometry.union_all().buffer(0.02)
    col, proj = build_collection(ee, spec, a.start, a.end, region)
    pinfo = proj.getInfo()
    pinfo.setdefault("transform", [abs(proj.nominalScale().getInfo()), 0, 0, 0, -abs(proj.nominalScale().getInfo()), 0])
    agg = spec.get("agg")
    if agg:  # daily products: enumerate dates client-side, build each day's image on demand (avoids EE memory limit)
        import pandas as pd
        first = ee.Date(ee.ImageCollection(spec["col"]).first().get("system:time_start")).format("YYYY-MM-dd").getInfo()
        s0 = max(pd.Timestamp(a.start), pd.Timestamp(first))
        ids = [d.strftime("%Y_%m_%d") for d in pd.date_range(s0, pd.Timestamp(a.end) - pd.Timedelta(days=1))]
    else:
        ids = col.aggregate_array("system:index").getInfo()
    if a.limit: ids = ids[: a.limit]
    if not ids:
        print(f"{a.product}: no new images between {a.start} and {a.end}"); print("done {'ok': 0, 'skip': 0, 'fail': 0}"); return
    bpp = {"int16": 2, "uint16": 2, "uint8": 1, "float32": 4}[spec["cast"]]
    tiles = tiles_for(bounds, pinfo["transform"], len(spec["bands"]), bpp)
    print(f"{a.product}: {len(ids)} images | crs {pinfo['crs']} | pixel {pinfo['transform'][0]:.6g} | {len(tiles)} tiles/image | dest {spec['dest']}")
    if a.dry_run:
        print("first ids:", ids[:3], "last:", ids[-2:]); return
    lst = None if agg else col.toList(len(ids) if not a.limit else a.limit)

    def day_image(iid):
        d = ee.Date(iid.replace("_", "-"))
        sub = ee.ImageCollection(spec["col"]).filterDate(d, d.advance(1, "day")).select(spec["bands"])
        img = sub.mean()
        return img.multiply(24) if agg == "daily_sum_mmhr" else img
    dest = ROOT / spec["dest"]

    def job(i):
        iid = ids[i]
        out = dest / f"{a.product}_{iid}.tif"
        try:
            base = day_image(iid) if agg else ee.Image(lst.get(i))
            img = cast(base.clip(region).unmask(spec["nodata"], False), spec["cast"])  # sameFootprint=False: fill outside clip too
            st = process(ee, spec, a.product, iid, img, pinfo, tiles, out)
            if st == "ok": log(f"GEE {a.product} {iid}", spec["col"], out, "OK (MH clip, native grid)")
            return st
        except Exception as e:
            if "has no bands" in str(e):  # no source images for this day yet (near-real-time lag) - not a failure
                log(f"GEE {a.product} {iid}", spec["col"], None, "NOT_YET_AVAILABLE", "no source images for this date"); return "skip"
            log(f"GEE {a.product} {iid}", spec["col"], None, "FAILED", e); return "fail"

    res = {"ok": 0, "skip": 0, "fail": 0}
    with ThreadPoolExecutor(a.workers) as ex:
        for k, st in enumerate(ex.map(job, range(len(ids)))):
            res[st] += 1
            if k % 20 == 0: print(f"  {k + 1}/{len(ids)} {res}", flush=True)
    print("done", res)


if __name__ == "__main__":
    main()
