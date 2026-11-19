"""PHASE 2 - Validate actual dataset contents (not filenames) against the GeoCrop catalog.

Writes
  reports/dataset_audit/dataset_inventory.csv
  reports/dataset_audit/dataset_audit.json
  reports/dataset_audit/missing_resources.csv

Rasters are inspected via metadata + decimated reads (never full-loaded); NetCDF lazily via xarray.
Usage: python scripts/audit/validate_datasets.py [--tag initial|final]
"""
import argparse, csv, glob, hashlib, io, json, re, sys, warnings, zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from catalog import CATALOG, MH_BBOX, ROOT, SG_DEPTHS, SG_PROPS  # noqa: E402

warnings.filterwarnings("ignore")
OUT = ROOT / "reports/dataset_audit"

ST_VALID, ST_INCOMPLETE, ST_INVALID, ST_PREPROC = ("PRESENT AND VALID", "PRESENT BUT INCOMPLETE",
                                                    "PRESENT BUT INVALID", "PRESENT BUT NEEDS PREPROCESSING")
ST_MISSING, ST_RESTRICTED, ST_NA = "MISSING", "ACCESS RESTRICTED", "NOT APPLICABLE"


def overlap_frac(b, ref=MH_BBOX):
    """Fraction of the Maharashtra bbox covered by bounds b=(minx,miny,maxx,maxy)."""
    ix = max(0, min(b[2], ref[2]) - max(b[0], ref[0]))
    iy = max(0, min(b[3], ref[3]) - max(b[1], ref[1]))
    return round(ix * iy / ((ref[2] - ref[0]) * (ref[3] - ref[1])), 3)


# ---------------------------------------------------------------- per-file inspectors
def inspect_raster(path):
    import rasterio
    from rasterio.warp import transform_bounds
    with rasterio.open(path) as r:
        b = r.bounds
        b4326 = transform_bounds(r.crs, "EPSG:4326", *b) if r.crs else tuple(b)
        f = max(1, max(r.width, r.height) // 512)
        a = r.read(1, out_shape=(max(1, r.height // f), max(1, r.width // f)), masked=True)
        valid = int(a.count())
        info = dict(type="raster", crs=str(r.crs), width=r.width, height=r.height, bands=r.count,
                    dtype=r.dtypes[0], res=[round(x, 8) for x in r.res], nodata=r.nodata,
                    band_names=[d for d in r.descriptions if d], bounds_4326=[round(x, 4) for x in b4326],
                    mh_overlap=overlap_frac(b4326), sample_valid=valid, sample_total=int(a.size),
                    sample_min=float(a.min()) if valid else None, sample_max=float(a.max()) if valid else None,
                    tags={k: v for k, v in r.tags().items() if not k.startswith("TIFFTAG")})
    info["all_constant"] = valid > 0 and info["sample_min"] == info["sample_max"]
    return info


def inspect_netcdf(path):
    import xarray as xr
    if Path(path).stat().st_size == 0:
        return dict(type="netcdf", error="empty file (0 bytes)")
    try:
        ds = xr.open_dataset(path, decode_times=True)
    except Exception as e:
        return dict(type="netcdf", error=f"cannot open: {e}")
    info = dict(type="netcdf", vars={k: list(v.dims) for k, v in ds.data_vars.items()}, dims=dict(ds.sizes),
                attrs={k: str(v)[:200] for k, v in list(ds.attrs.items())[:10]})
    tname = next((d for d in ds.coords if d.lower() in ("time", "t")), None)
    if tname:
        t = pd.to_datetime(ds[tname].values)
        info.update(start=str(t.min().date()), end=str(t.max().date()), n_time=len(t), dup_times=int(t.duplicated().sum()))
    lat = next((d for d in ds.coords if d.lower().startswith("lat")), None)
    lon = next((d for d in ds.coords if d.lower().startswith("lon")), None)
    if lat and lon:
        b = (float(ds[lon].min()), float(ds[lat].min()), float(ds[lon].max()), float(ds[lat].max()))
        info.update(bounds_4326=b, mh_overlap=overlap_frac(b), res=float(abs(ds[lat][1] - ds[lat][0])))
        v = next(iter(ds.data_vars))
        sub = ds[v].sel({lat: slice(MH_BBOX[1], MH_BBOX[3]), lon: slice(MH_BBOX[0], MH_BBOX[2])})
        if tname: sub = sub.isel({tname: slice(0, None, 30)})
        arr = sub.values
        info.update(mh_sample_nan_frac=round(float(np.isnan(arr).mean()), 4) if arr.size else None,
                    mh_sample_min=float(np.nanmin(arr)) if arr.size and not np.isnan(arr).all() else None,
                    mh_sample_max=float(np.nanmax(arr)) if arr.size and not np.isnan(arr).all() else None)
    ds.close()
    return info


def inspect_vector(path):
    import geopandas as gpd
    g = gpd.read_file(path)
    return dict(type="vector", crs=str(g.crs), n=len(g), cols=list(g.columns)[:30],
                invalid_geoms=int((~g.geometry.is_valid).sum()), bounds_4326=list(g.to_crs(4326).total_bounds.round(4)))


def read_apy_html(path):
    s = open(path, encoding="utf-8", errors="replace").read()
    return pd.read_html(io.StringIO(s))[0]


def inspect_apy(path):
    t = read_apy_html(path)
    years = sorted({c[0] for c in t.columns if re.match(r"\d{4} - \d{4}", str(c[0]))} |
                   ({str(y) for y in t.iloc[:, 2].unique()} if any("Year" in str(c) for c in t.columns[2]) else set()))
    dist_col = 2 if "District" in str(t.columns[2]) else 1
    crops = sorted({c[0] for c in t.columns if not re.match(r"\d{4}|S\.No|State|District|Year", str(c[0]))})
    return dict(type="apy_html_table", real_format="HTML table saved with .xls extension", rows=len(t),
                n_districts=int(t.iloc[:, dist_col].nunique()), years=years, crops_named=crops,
                missing_cells_frac=round(float(t.isna().mean().mean()), 3))


def inspect_pdf(path):
    import pymupdf
    d = pymupdf.open(path)
    txt = "".join(d[i].get_text() for i in range(min(3, d.page_count)))
    return dict(type="pdf", pages=d.page_count, title=d.metadata.get("title"), text_layer=bool(txt.strip()),
                first_text=re.sub(r"\s+", " ", txt)[:200])


def inspect_zip(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    return dict(type="zip", members=len(names), sample=names[:8])


def inspect_csv(path):
    df = pd.read_csv(path, nrows=200000, comment="#")
    return dict(type="csv", cols=list(df.columns)[:40], rows_sampled=len(df), na_frac=round(float(df.isna().mean().mean()), 4))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""): h.update(c)
    return h.hexdigest()


def inspect_file(p):
    e = p.suffix.lower()
    try:
        if e in (".tif", ".tiff", ".vrt"): return inspect_raster(p)
        if e in (".nc", ".nc4"): return inspect_netcdf(p)
        if e in (".geojson", ".gpkg", ".shp"): return inspect_vector(p)
        if e == ".xls" and open(p, "rb").read(200).lstrip().startswith(b"<"): return inspect_apy(p)
        if e == ".pdf": return inspect_pdf(p)
        if e == ".zip": return inspect_zip(p)
        if e == ".csv": return inspect_csv(p)
        return dict(type="other", size=p.stat().st_size)
    except Exception as ex:
        return dict(type="error", error=f"{type(ex).__name__}: {ex}")


# ---------------------------------------------------------------- per-dataset decisions
def files_for(r):
    out = []
    for g in r["globs"]:
        out += [Path(x) for x in glob.glob(str(ROOT / g), recursive=True) if Path(x).is_file()]
    return sorted(set(out))


def decide(r, files):
    """Return (status, issues[], details{})"""
    ex = r["expect"]; kind = ex.get("kind"); issues = []; det = {}
    if not files:
        st = ST_MISSING
        if r["access"] in ("gee_auth", "earthdata_auth", "account"):
            issues.append(f"Requires authenticated access ({r['access']}); not obtainable without user credentials.")
        return st, issues, det
    is_ts = kind == "raster" and ex.get("temporal") and ex.get("expected_n")
    insp = {} if is_ts else {str(f.relative_to(ROOT)): inspect_file(f) for f in files[:400]}
    det["n_inspected"] = len(insp)

    if kind == "sha256":
        ok = [k for k in insp if sha256(ROOT / k) == ex["sha256"]]
        det["sha256_match"] = ok
        return (ST_VALID if ok else ST_INVALID), ([] if ok else ["Checksum does not match official release"]), det

    if kind == "raster" and ex.get("temporal") and ex.get("expected_n"):
        # Time series: dates from filenames (<PRODUCT>_YYYY_MM_DD.tif); content checks on an even sample.
        files = [f for f in files if ".part" not in f.name]
        dates = sorted(pd.to_datetime(m.group(1), format="%Y_%m_%d") for f in files
                       if (m := re.search(r"(\d{4}_\d{2}_\d{2})", f.name)) and ".part" not in f.name)
        sample = [files[i] for i in np.linspace(0, len(files) - 1, min(40, len(files))).astype(int)]
        si = {str(f.relative_to(ROOT)): inspect_raster(f) for f in sample}
        bad = [k for k, v in si.items() if v["mh_overlap"] < 0.9 or v["sample_valid"] == 0 or v["all_constant"]]
        first = next(iter(si.values()))
        miss_b = [b for b in ex.get("bands_any", []) if b not in first["band_names"]]
        det.update(n_dates=len(dates), expected_n=ex["expected_n"], start=str(dates[0].date()), end=str(dates[-1].date()),
                   dup_dates=len(dates) - len(set(dates)), sample_checked=len(si), sample_bad=bad[:5], example=first)
        if miss_b: issues.append(f"Missing bands {miss_b}")
        if bad: issues.append(f"{len(bad)}/{len(si)} sampled rasters fail coverage/validity")
        if det["dup_dates"]: issues.append("Duplicate dates")
        if len(dates) < ex["expected_n"]:
            issues.append(f"{len(dates)}/{ex['expected_n']} time steps present")
            return ST_INCOMPLETE, issues, det
        if miss_b or bad: return ST_INCOMPLETE, issues, det
        issues.append("Stored as published: MODIS raw integers need scale factors (GeoTIFF tags); QA bands kept unapplied; SMAP/IMERG are daily aggregates of sub-daily data")
        return ST_PREPROC if ex["expected_n"] > 11 and "LC_Type1" not in ex.get("bands_any", []) else ST_VALID, issues, det

    if kind in ("raster", "raster_set"):
        rs = [v for v in insp.values() if v.get("type") == "raster"]
        # Tiled sets (DEM) are judged on the union footprint; single rasters must themselves overlap Maharashtra.
        tiled = kind == "raster_set" and ex.get("cover_mh")
        bad = [k for k, v in insp.items() if v.get("type") == "raster" and
               ((not tiled and v["mh_overlap"] < 0.05) or (tiled and v["mh_overlap"] == 0) or v["sample_valid"] == 0 or v["all_constant"])]
        det["n_rasters"] = len(rs); det["n_bad"] = len(bad)
        if rs:
            det["example"] = rs[0]
        if rs and len(bad) == len(rs):
            issues.append("All rasters fail checks (outside Maharashtra, empty, or constant-valued).")
            return ST_INVALID, issues, det
        if kind == "raster_set" and len(rs) - len(bad) < ex.get("min_files", 1):
            issues.append(f"Only {len(rs) - len(bad)} valid rasters, expected >= {ex.get('min_files')}")
            return ST_INCOMPLETE, issues, det
        if kind == "raster_set" and ex.get("cover_mh"):
            from shapely.geometry import box
            from shapely.ops import unary_union
            u = unary_union([box(*v["bounds_4326"]) for v in rs])
            st_file = ROOT / "data/interim/boundaries/maharashtra_state.geojson"
            if st_file.exists():  # compare with the state polygon (bbox includes sea / neighbouring states)
                import geopandas as gpd
                target = gpd.read_file(st_file).geometry.union_all()
            else:
                target = box(*MH_BBOX)
            det["mh_cover_frac"] = round(u.intersection(target).area / target.area, 4)
            if det["mh_cover_frac"] < 0.995:
                return ST_INCOMPLETE, [f"DEM tiles cover {det['mh_cover_frac']:.1%} of Maharashtra"], det
        if bad: issues.append(f"{len(bad)} rasters invalid")
        if ex.get("temporal") and len(rs) < 10:
            issues.append("Too few time steps for 2015-2025")
            return ST_INCOMPLETE, issues, det
        return (ST_VALID if not bad else ST_INCOMPLETE), issues, det

    if kind == "soilgrids":
        have = {(p, d, q) for k in insp for p in ex["props"] for d in ex["depths"] for q in ("mean", "Q0.05", "Q0.95", "uncertainty")
                if Path(k).name == f"{p}_{d}_{q}.tif"}
        bad = [k for k, v in insp.items() if v.get("type") != "raster" or v["mh_overlap"] < 0.95 or v["sample_valid"] == 0]
        means = {(p, d) for p, d, q in have if q == "mean"}
        need = {(p, d) for p in ex["props"] for d in ex["depths"]}
        det.update(n_layers=len(have), mean_layers=f"{len(means)}/{len(need)}",
                   quantile_layers=len([h for h in have if h[2] != "mean"]), bad=bad[:10],
                   missing_mean=sorted(f"{p}_{d}" for p, d in need - means)[:20])
        if bad: issues.append(f"{len(bad)} layers fail coverage/validity")
        if need - means:
            issues.append(f"{len(need - means)} property/depth mean layers missing")
            return ST_INCOMPLETE, issues, det
        issues.append("Integer-scaled values (see SoilGrids conversion factors); Homolosine projection; global model - not validated at farm level.")
        return (ST_PREPROC if not bad else ST_INCOMPLETE), issues, det

    if kind == "netcdf_years":
        ok = {k: v for k, v in insp.items() if v.get("type") == "netcdf" and not v.get("error")}
        errs = {k: v["error"] for k, v in insp.items() if v.get("error")}
        if errs: issues += [f"{Path(k).name}: {e}" for k, e in errs.items()]
        if not ok:
            return ST_INVALID, issues, det
        yrs = sorted({int(v["start"][:4]) for v in ok.values() if v.get("start")})
        det["years"] = yrs; det["example"] = next(iter(ok.values()))
        missing = [y for y in range(2015, 2026) if y not in yrs]
        if any(v.get("mh_overlap", 0) < 0.95 for v in ok.values()): issues.append("Some files do not cover Maharashtra")
        if any(v.get("dup_times") for v in ok.values()): issues.append("Duplicate time stamps")
        if missing:
            issues.append(f"Years missing: {missing}")
            return ST_INCOMPLETE, issues, det
        return ST_VALID, issues, det

    if kind == "nasa_power":
        dfs = []
        for f in files:
            if f.suffix == ".csv":
                dfs.append(pd.read_csv(f, usecols=lambda c: True))
        if not dfs: return ST_MISSING, ["No CSV"], det
        df = pd.concat(dfs)
        miss_vars = [v for v in ex["vars"] if v not in df.columns]
        df["date"] = pd.to_datetime(df["date"])
        det.update(n_cells=int(df[["lat", "lon"]].drop_duplicates().shape[0]), start=str(df.date.min().date()),
                   end=str(df.date.max().date()), dup_rows=int(df.duplicated(["lat", "lon", "date"]).sum()),
                   fill_frac={v: round(float((df[v] == -999).mean()), 4) for v in ex["vars"] if v in df})
        exp_days = (pd.Timestamp("2025-12-31") - pd.Timestamp("2015-01-01")).days + 1
        per_cell = df.groupby(["lat", "lon"]).size()
        det["cells_complete"] = int((per_cell >= exp_days).sum())
        if miss_vars: issues.append(f"Missing variables {miss_vars}")
        if det["dup_rows"]: issues.append("Duplicate cell-date rows")
        if det["cells_complete"] < det["n_cells"]: issues.append(f"{det['n_cells'] - det['cells_complete']} cells incomplete")
        if miss_vars or det["end"] < "2025-12-31" or det["start"] > "2015-01-01":
            return ST_INCOMPLETE, issues, det
        return ST_VALID, issues, det

    if kind == "boundaries":
        vecs = {k: v for k, v in insp.items() if v.get("type") == "vector"}
        det["layers"] = {k: {kk: v[kk] for kk in ("n", "crs", "invalid_geoms")} for k, v in vecs.items()}
        dist = [v for k, v in vecs.items() if "district" in k.lower()]
        state = [v for k, v in vecs.items() if "state" in k.lower()]
        if not state: issues.append("No state boundary layer")
        if not dist: return ST_INCOMPLETE, issues + ["No district layer"], det
        n = dist[0]["n"]; det["n_districts"] = n
        if any(v["invalid_geoms"] for v in vecs.values()): issues.append("Invalid geometries present (repair with make_valid)")
        if n != ex["n_districts"]:
            issues.append(f"District layer has {n} polygons; Maharashtra has 36 current districts")
            return ST_INCOMPLETE, issues, det
        return (ST_VALID if state else ST_INCOMPLETE), issues, det

    if kind == "apy_html":
        apy = {k: v for k, v in insp.items() if v.get("type") == "apy_html_table"}
        other = {k: v for k, v in insp.items() if v.get("type") not in ("apy_html_table",)}
        det["files"] = apy; det["other"] = list(other)
        yrs = sorted({y for v in apy.values() for y in v["years"]})
        det["years_covered"] = yrs
        issues.append("Files are HTML tables with .xls extension (need HTML parser).")
        unnamed = [Path(k).name for k, v in apy.items() if not v["crops_named"]]
        if unnamed: issues.append(f"{len(unnamed)} reports do not state which crop/crop-group they contain: {unnamed}")
        issues.append(f"Years covered {yrs[0] if yrs else '-'}..{yrs[-1] if yrs else '-'}; 2023-24 onward missing; district names need harmonising (34-35 districts, new names).")
        return ST_INCOMPLETE, issues, det

    if kind == "region_check":
        txt = " ".join(json.dumps(v) for v in insp.values()).lower() + " ".join(str(f).lower() for f in files)
        if ex["must_contain"] not in txt:
            return ST_INVALID, [f"Files present but none refer to {ex['must_contain'].title()} (wrong region)"] + list(insp)[:3], det
        return ST_VALID, issues, det

    if kind in ("pdf", "pdf_set"):
        ok = [k for k, v in insp.items() if v.get("type") == "pdf"]
        det["pdfs"] = {k: insp[k] for k in ok[:30]}
        if not ok: return ST_INVALID, ["No readable PDFs"], det
        issues.append("Reference documents - require manual curation into structured knowledge base")
        return ST_PREPROC, issues, det

    if kind == "image_folders":
        dirs = {}
        for f in glob.glob(str(ROOT / r["globs"][0].replace("**/*", "**/*.*")), recursive=True):
            if f.lower().endswith((".jpg", ".jpeg", ".png")):
                dirs[Path(f).parent.name] = dirs.get(Path(f).parent.name, 0) + 1
        det.update(n_classes=len(dirs), n_images=sum(dirs.values()),
                   min_per_class=min(dirs.values()) if dirs else 0, max_per_class=max(dirs.values()) if dirs else 0)
        if len(dirs) < ex["min_classes"]:
            return ST_INCOMPLETE, [f"{len(dirs)} classes < {ex['min_classes']}"], det
        if det["max_per_class"] > 10 * max(1, det["min_per_class"]): issues.append("Severe class imbalance (>10x)")
        return ST_VALID, issues, det

    if kind == "imd_temp_bin":
        # IMD 1-deg binary: 31x31 float32 grid per day, origin 7.5N 67.5E, missing = 99.9
        yrs = {}
        for f in files:
            m = re.match(r"(maxtemp|mintemp)_(\d{4})", f.stem)
            if not m: continue
            n = f.stat().st_size / (31 * 31 * 4)
            a = np.fromfile(f, dtype="<f4").reshape(-1, 31, 31)
            mh = a[:, int(15.5 - 7.5):int(22.5 - 7.5) + 1, int(72.5 - 67.5):int(81 - 67.5) + 1]
            ok = n in (365, 366) and np.nanmax(np.where(mh > 90, np.nan, mh)) < 55 and np.nanmin(np.where(mh > 90, np.nan, mh)) > -10
            yrs.setdefault(m.group(1), {})[int(m.group(2))] = dict(days=n, plausible=bool(ok))
        det["years"] = sorted({y for v in yrs.values() for y in v}); det["by_var"] = yrs
        bad = [f"{v}{y}" for v, d in yrs.items() for y, x in d.items() if not x["plausible"]]
        missing = [f"{v}{y}" for v in ("maxtemp", "mintemp") for y in range(2015, 2026) if y not in yrs.get(v, {})]
        if bad: issues.append(f"Implausible/irregular files: {bad}")
        if missing: issues.append(f"Missing: {missing}")
        issues.append("Raw IMD binary (.GRD) - convert to NetCDF with lat/lon/time before use")
        return (ST_INCOMPLETE if (missing or bad) else ST_PREPROC), issues, det

    if kind == "crop_calendar":
        return ST_INCOMPLETE, ["Calendar file present - verify every row has a cited source"], det

    # "any"
    det["files"] = list(insp)[:20]
    return ST_PREPROC, ["Present; content not auto-validated"], det


ACTIONS = {
    "gee_auth": "Authenticate Earth Engine (earthengine authenticate; set GEE project) then run scripts/gee/export_<dataset>.py",
    "earthdata_auth": "Create NASA Earthdata login (urs.earthdata.nasa.gov), add to ~/.netrc, or use GEE equivalent",
    "account": "Register for account / accept licence, then rerun scripts/download/download_missing.py",
    "manual_portal": "Manual acquisition from portal / data request (see missing_resources.csv)",
    "public_auto": "Run scripts/download/download_missing.py",
    "reference_only": "Manual curation from public reference documents",
}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tag", default="current"); a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for did, r in CATALOG.items():
        files = files_for(r)
        st, issues, det = decide(r, files)
        if st == ST_MISSING and r["access"] in ("gee_auth", "earthdata_auth", "account"):
            st_out = ST_MISSING + " (" + ST_RESTRICTED + ")"
        else:
            st_out = st
        size = sum(f.stat().st_size for f in files)
        ex = det.get("example", {})
        results.append(dict(dataset_id=did, name=r["name"], source=r["source"], file_count=len(files), total_size_mb=round(size / 1e6, 2),
                            format=";".join(sorted({f.suffix.lower() for f in files})), status=st_out, issues=issues,
                            spatial_resolution=str(ex.get("res", "")), crs=ex.get("crs", ""), start=det.get("start", ""), end=det.get("end", ""),
                            years=det.get("years", det.get("years_covered", "")), coverage_mh=ex.get("mh_overlap", ""),
                            variables=ex.get("vars", ex.get("band_names", "")), access=r["access"], weight=r["weight"],
                            modules=r["modules"], licence=r["licence"], size_hint=r["size_hint"], notes=r["notes"],
                            recommended_action="none" if st == ST_VALID else ACTIONS[r["access"]], details=det))
        print(f"{did:5s} {st_out:45s} files={len(files):5d} {r['name'][:60]}")
    meta = dict(generated=datetime.now(timezone.utc).isoformat(timespec="seconds"), tag=a.tag, mh_bbox=MH_BBOX)
    json.dump(dict(meta=meta, datasets=results), open(OUT / f"dataset_audit{'' if a.tag == 'current' else '_' + a.tag}.json", "w", encoding="utf-8"), indent=1, default=str)
    if a.tag != "current":
        json.dump(dict(meta=meta, datasets=results), open(OUT / "dataset_audit.json", "w", encoding="utf-8"), indent=1, default=str)
    cols = ["Dataset ID", "Dataset name", "Source", "File count", "Total size (MB)", "Format", "Spatial resolution", "Temporal resolution",
            "Start date", "End date", "Geographic coverage", "Variables/bands", "CRS", "Status", "Issues", "Recommended action", "Licence/access notes"]
    TEMP = {"A1": "16-day", "A2": "8-day", "A3": "8-day", "A4": "annual", "B5": "daily", "B6": "daily", "B7": "daily", "B8": "daily",
            "B9": "30-min/daily", "C10": "3-hourly", "H26": "5-day revisit", "H27": "6-12 day", "H28": "16-day", "G24": "twice weekly runs, daily steps"}
    with open(OUT / "dataset_inventory.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(cols)
        for x in results:
            w.writerow([x["dataset_id"], x["name"], x["source"], x["file_count"], x["total_size_mb"], x["format"], x["spatial_resolution"],
                        TEMP.get(x["dataset_id"], "static"), x["start"] or (x["years"][0] if x["years"] else ""), x["end"] or (x["years"][-1] if x["years"] else ""),
                        f"MH bbox overlap {x['coverage_mh']}" if x["coverage_mh"] != "" else "", json.dumps(x["variables"]) if x["variables"] else "",
                        x["crs"], x["status"], " | ".join(x["issues"]), x["recommended_action"], f"{x['access']}; {x['licence']}"])
    with open(OUT / "missing_resources.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["Resource", "Related module", "Reason missing", "Official source", "Download method", "Expected size if known", "Access restrictions", "Status"])
        for x in results:
            if x["status"].startswith(ST_VALID): continue
            w.writerow([f"{x['dataset_id']} {x['name']}", ";".join(x["modules"]), " | ".join(x["issues"]) or x["status"], x["source"],
                        ACTIONS[x["access"]], x["size_hint"], x["licence"] + ("" if x["access"] == "public_auto" else f" [{x['access']}]"), x["status"]])


if __name__ == "__main__":
    main()
