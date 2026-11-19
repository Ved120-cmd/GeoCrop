"""PHASE 5-7 - Download missing *publicly accessible* GeoCrop resources from official sources.

Rules enforced here:
  * Reads reports/dataset_audit/dataset_audit.json; skips datasets already PRESENT AND VALID.
  * Never overwrites: existing files with matching size/checksum are skipped; partial files are resumed.
  * Only official / research-institution endpoints, no credentials, polite pacing, honours HTTP 429.
  * Maharashtra subsets wherever the service allows (SoilGrids windows, POWER grid cells, DEM tiles).
  * Every attempt is appended to reports/download_logs/download_log.csv.

Usage:
  python scripts/download/download_missing.py --list
  python scripts/download/download_missing.py --only E18a B5 B6
  python scripts/download/download_missing.py            # everything public_auto that is not valid
"""
import argparse, csv, hashlib, json, os, subprocess, sys, time, zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "audit"))
from catalog import CATALOG, MH_BBOX, ROOT, SG_DEPTHS, SG_PROPS  # noqa: E402

RAW = ROOT / "data/raw"
INTERIM = ROOT / "data/interim"
LOG = ROOT / "reports/download_logs/download_log.csv"
UA = {"User-Agent": "GeoCrop-data-audit/1.0 (research; python-requests)"}
S = requests.Session(); S.headers.update(UA)
LOG_COLS = ["Resource", "URL/source", "Retrieval date", "File path", "Size (bytes)", "Checksum (sha256)", "Download status", "Errors", "Licence notes"]


# ------------------------------------------------------------------ helpers
def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""): h.update(c)
    return h.hexdigest()


def log(res, url, path, status, err="", lic=""):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG.exists()
    p = Path(path) if path else None
    size = p.stat().st_size if p and p.exists() and p.is_file() else ""
    chk = sha256(p) if p and p.exists() and p.is_file() and size and size < 3e9 else ""
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new: w.writerow(LOG_COLS)
        w.writerow([res, url, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    str(p.relative_to(ROOT)) if p and p.is_absolute() and ROOT in p.parents else (str(p) if p else ""),
                    size, chk, status, str(err)[:300], lic])
    print(f"[{status}] {res} {p.name if p else ''} {err if err else ''}")


def fetch(url, dest: Path, res, lic="", expect_sha=None, method="GET", data=None, retries=4, timeout=300, min_bytes=1):
    """Resumable, retrying download. Returns path or None."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size >= min_bytes and (not expect_sha or sha256(dest) == expect_sha):
        log(res, url, dest, "SKIPPED_EXISTS", lic=lic); return dest
    part = dest.with_suffix(dest.suffix + ".part")
    for i in range(retries):
        try:
            hdr = {}
            if method == "GET" and part.exists():
                hdr["Range"] = f"bytes={part.stat().st_size}-"
            r = S.request(method, url, data=data, headers=hdr, stream=True, timeout=timeout)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 60 * (i + 1)))
                print(f"  429 rate-limited; waiting {wait}s"); time.sleep(wait); continue
            if r.status_code == 404:
                log(res, url, None, "NOT_AVAILABLE", "HTTP 404", lic); return None
            r.raise_for_status()
            mode = "ab" if r.status_code == 206 else "wb"
            with open(part, mode) as f:
                for c in r.iter_content(1 << 20): f.write(c)
            if part.stat().st_size < min_bytes:
                raise IOError(f"too small ({part.stat().st_size} bytes)")
            if expect_sha and sha256(part) != expect_sha:
                part.unlink(); raise IOError("checksum mismatch")
            os.replace(part, dest)
            log(res, url, dest, "OK" + (" (sha256 verified)" if expect_sha else ""), lic=lic); return dest
        except Exception as e:
            err = e; time.sleep(5 * (i + 1))
    log(res, url, None, "FAILED", err, lic); return None


# ------------------------------------------------------------------ E18a boundaries
def dl_boundaries():
    import geopandas as gpd
    lic = "geoBoundaries gbOpen, ODbL 1.0 (source: lgdirectory.gov.in / Pathways Data)"
    out = RAW / "boundaries/geoboundaries"
    paths = {}
    for lvl in ("ADM1", "ADM2"):
        meta = S.get(f"https://www.geoboundaries.org/api/current/gbOpen/IND/{lvl}/", timeout=60).json()
        json.dump(meta, open(out.mkdir(parents=True, exist_ok=True) or out / f"IND_{lvl}_metadata.json", "w"), indent=1)
        paths[lvl] = fetch(meta["gjDownloadURL"], out / f"geoBoundaries-IND-{lvl}.geojson", f"E18a geoBoundaries IND {lvl} ({meta['boundaryYearRepresented']})", lic, min_bytes=10000)
    if not all(paths.values()): return
    a1 = gpd.read_file(paths["ADM1"]); a2 = gpd.read_file(paths["ADM2"])
    import unicodedata
    norm = lambda s: unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    mh = a1[a1.shapeName.map(norm).str.contains("maharashtra")].copy()  # names carry diacritics ("Mahārāshtra")
    mh["geometry"] = mh.geometry.make_valid()
    pts = a2.copy(); pts["geometry"] = a2.geometry.make_valid().representative_point()
    inside = gpd.sjoin(pts, mh[["geometry"]], predicate="within").index
    d = a2.loc[inside].copy(); d["geometry"] = d.geometry.make_valid()
    d = d.rename(columns={"shapeName": "district"})[["district", "shapeID", "shapeISO", "geometry"]]
    io = INTERIM / "boundaries"; io.mkdir(parents=True, exist_ok=True)
    mh.to_file(io / "maharashtra_state.geojson", driver="GeoJSON")
    d.to_file(io / "maharashtra_districts.geojson", driver="GeoJSON")
    log("E18a Maharashtra state (derived)", "derived from ADM1", io / "maharashtra_state.geojson", "DERIVED", lic=lic)
    log("E18a Maharashtra districts (derived)", "derived from ADM2 (representative point within MH)", io / "maharashtra_districts.geojson",
        "DERIVED", f"{len(d)} districts", lic)


def mh_geom():
    import geopandas as gpd
    p = INTERIM / "boundaries/maharashtra_state.geojson"
    return gpd.read_file(p).geometry.union_all() if p.exists() else None


# ------------------------------------------------------------------ B5 NASA POWER
POWER_VARS = ["T2M", "T2M_MAX", "T2M_MIN", "RH2M", "PRECTOTCORR", "WS2M", "ALLSKY_SFC_SW_DWN"]


def dl_power(start="20150101", end="20251231"):
    import numpy as np, pandas as pd
    from shapely.geometry import box
    lic = "NASA POWER (LaRC) open data; cite POWER Project, MERRA-2 / CERES sources"
    g = mh_geom()
    if g is None: print("need boundaries first (E18a)"); return
    g = g.buffer(0.1)
    cells = []
    for lat in np.arange(15.5, 22.51, 0.5):
        for lon in np.arange(72.5, 81.26, 0.625):
            if box(lon - 0.3125, lat - 0.25, lon + 0.3125, lat + 0.25).intersects(g):
                cells.append((round(lat, 3), round(lon, 4)))
    print(f"POWER: {len(cells)} MERRA-2 cells intersect Maharashtra")
    cdir = RAW / "weather/nasa_power/cells"; cdir.mkdir(parents=True, exist_ok=True)
    for lat, lon in cells:
        f = cdir / f"power_{lat:.3f}_{lon:.4f}.json"
        url = (f"https://power.larc.nasa.gov/api/temporal/daily/point?parameters={','.join(POWER_VARS)}&community=AG"
               f"&longitude={lon}&latitude={lat}&start={start}&end={end}&format=JSON&time-standard=LST")
        fetch(url, f, f"B5 NASA POWER cell {lat},{lon}", lic, min_bytes=100000, timeout=600)
        time.sleep(1.0)  # polite pacing
    frames = []
    for f in sorted(cdir.glob("*.json")):
        j = json.load(open(f)); p = j["properties"]["parameter"]
        df = pd.DataFrame(p); df.index.name = "date"; df = df.reset_index()
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
        lon, lat, elev = j["geometry"]["coordinates"]
        df.insert(1, "lat", lat); df.insert(2, "lon", lon); df.insert(3, "elev_m", elev)
        frames.append(df)
    if frames:
        out = RAW / "weather/nasa_power/power_daily_mh_2015_2025.csv"
        all_ = pd.concat(frames).replace(-999.0, np.nan)
        all_.to_csv(out, index=False)
        units = {v: json.load(open(next(cdir.glob('*.json'))))["parameters"][v]["units"] for v in POWER_VARS}
        json.dump(dict(units=units, fill_value_replaced=-999, grid="MERRA-2 0.5 x 0.625 deg (solar: CERES 1 deg)", time_standard="LST",
                       n_cells=len(frames)), open(out.with_suffix(".meta.json"), "w"), indent=1)
        log("B5 NASA POWER combined CSV", "derived from per-cell JSON", out, "DERIVED", f"{len(frames)} cells", lic)


# ------------------------------------------------------------------ B6 / B7 IMD
def dl_imd(years=range(2015, 2026)):
    lic = "IMD Pune gridded data, free for research; cite Pai et al. (2014) Mausam 65(1)"
    for y in years:
        fetch("https://imdpune.gov.in/cmpg/Griddata/RF25.php", RAW / f"weather/imd/rain_0p25/ind{y}_rfp25.nc", f"B6 IMD rainfall 0.25 {y}",
              lic, method="POST", data={"RF25": str(y)}, min_bytes=1_000_000)
        time.sleep(2)
    for var, page in (("maxtemp", "maxtemp.php"), ("mintemp", "mintemp.php")):
        for y in years:
            fetch(f"https://imdpune.gov.in/cmpg/Griddata/{page}", RAW / f"weather/imd/temp_1deg/{var}_{y}.GRD", f"B7 IMD {var} 1deg {y}",
                  lic, method="POST", data={var: str(y)}, min_bytes=31 * 31 * 4 * 300)
            time.sleep(2)


# ------------------------------------------------------------------ B8 CHIRPS
def dl_chirps(years=range(2015, 2026)):
    lic = "CHIRPS v2.0, CC BY 4.0 - Funk et al. (2015) Sci. Data"
    for y in years:
        r = fetch(f"https://data.chc.ucsb.edu/products/CHIRPS/v2.0/global_daily/netcdf/p25/chirps-v2.0.{y}.days_p25.nc",
                  RAW / f"weather/chirps/global_daily_p25/chirps-v2.0.{y}.days_p25.nc", f"B8 CHIRPS p25 {y}", lic, min_bytes=10_000_000, timeout=900)
        if r is None:
            print("CHIRPS stopped (unavailable / rate-limited) - not retrying aggressively"); return
        time.sleep(20)


# ------------------------------------------------------------------ D14 SoilGrids 2.0 / D14b 2017 water
def _gdal_env():
    import rasterio
    return rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="10",
                        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".vrt,.tif,.ovr", VSI_CACHE="TRUE", VSI_CACHE_SIZE="16000000", GDAL_CACHEMAX=64, GDAL_HTTP_MULTIRANGE="YES", GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES")


def crop_remote(url, dest: Path, res, lic):
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds
    if dest.exists() and dest.stat().st_size > 1000:
        log(res, url, dest, "SKIPPED_EXISTS", lic=lic); return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            with _gdal_env(), rasterio.open("/vsicurl/" + url) as src:
                b = transform_bounds("EPSG:4326", src.crs, *MH_BBOX, densify_pts=50)
                win = from_bounds(*b, transform=src.transform).round_offsets().round_lengths()
                arr = src.read(1, window=win)
                prof = src.profile.copy()
                prof.update(driver="GTiff", width=win.width, height=win.height, transform=src.window_transform(win),
                            compress="deflate", predictor=2, tiled=True, blockxsize=256, blockysize=256, BIGTIFF="NO")
                tmp = dest.with_suffix(".part.tif")
                with rasterio.open(tmp, "w", **prof) as dst:
                    dst.write(arr, 1)
                    dst.update_tags(source_url=url, retrieved=datetime.now(timezone.utc).isoformat(), subset="Maharashtra bbox " + str(MH_BBOX),
                                    note="native projection/resolution preserved; values are integer-scaled as published")
            os.replace(tmp, dest)
            log(res, url, dest, "OK (MH window)", lic=lic); return dest
        except Exception as e:
            err = e; time.sleep(30 * (attempt + 1))
    log(res, url, None, "FAILED", err, lic)


def dl_soilgrids(quantities=("mean",), workers=1):
    from concurrent.futures import ThreadPoolExecutor
    lic = "SoilGrids 2.0, CC BY 4.0 - Poggio et al. (2021) SOIL 7:217"
    jobs = []
    for p in SG_PROPS:
        for d in SG_DEPTHS:
            for q in quantities:
                url = f"https://files.isric.org/soilgrids/latest/data/{p}/{p}_{d}_{q}.vrt"
                jobs.append((url, RAW / f"soil/soilgrids/sg2/{p}/{p}_{d}_{q}.tif", f"D14 SoilGrids {p} {d} {q}", lic))
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(lambda j: crop_remote(*j), jobs))
    # conversion factors for downstream use
    json.dump({"bdod": "cg/cm3 -> /100 = kg/dm3", "cec": "mmol(c)/kg -> /10 = cmol(c)/kg", "cfvo": "cm3/dm3 (vol per mille) -> /10 = vol%",
               "clay": "g/kg -> /10 = %", "sand": "g/kg -> /10 = %", "silt": "g/kg -> /10 = %", "nitrogen": "cg/kg -> /100 = g/kg",
               "phh2o": "pH*10 -> /10 = pH", "soc": "dg/kg -> /10 = g/kg", "ocd": "hg/m3 -> /10 = kg/m3",
               "source": "https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html"},
              open(RAW / "soil/soilgrids/sg2/CONVERSION_FACTORS.json", "w"), indent=1)


def dl_soilgrids2017(workers=1):
    from concurrent.futures import ThreadPoolExecutor
    lic = "SoilGrids250m 2017-03-10 release (ISRIC), ODbL / CC BY 4.0 - Hengl et al. (2017) PLoS ONE"
    jobs = []
    for v in ("AWCh1", "AWCh2", "AWCh3", "WWP", "AWCtS"):
        for sl in range(1, 8):
            url = f"https://files.isric.org/soilgrids/former/2017-03-10/data/{v}_M_sl{sl}_250m_ll.tif"
            jobs.append((url, RAW / f"soil/soilgrids/sg2017_water/{v}_M_sl{sl}_250m_ll_MH.tif", f"D14b SoilGrids2017 {v} sl{sl}", lic))
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(lambda j: crop_remote(*j), jobs))
    json.dump({"AWCh1": "AVAILABLE water capacity (% vol) with FC at pF 2.0 (-10 kPa) = theta_FC - theta_WP", "AWCh2": "available water capacity, FC at pF 2.3 (-20 kPa)", "AWCh3": "available water capacity, FC at pF 2.5 (-31.6 kPa)", "WWP": "water content (% vol) at wilting point (-1500 kPa)",
               "AWCtS": "saturated water content (%)", "sl1..sl7": "0,5,15,30,60,100,200 cm depth points",
               "doc": "https://files.isric.org/soilgrids/former/2017-03-10/docs/"},
              open(RAW / "soil/soilgrids/sg2017_water/LAYERS.json", "w"), indent=1)


# ------------------------------------------------------------------ E17 DEM
def dl_dem():
    lic = "Copernicus DEM GLO-90 (c) DLR/Airbus, provided under COPERNICUS by the EU and ESA; free licence with attribution"
    g = mh_geom()
    from shapely.geometry import box
    for lat in range(15, 23):
        for lon in range(72, 81):
            if g is not None and not box(lon, lat, lon + 1, lat + 1).intersects(g.buffer(0.05)):
                continue
            n = f"Copernicus_DSM_COG_30_N{lat:02d}_00_E{lon:03d}_00_DEM"
            fetch(f"https://copernicus-dem-90m.s3.amazonaws.com/{n}/{n}.tif", RAW / f"terrain/copernicus_glo90/{n}.tif", f"E17 GLO-90 N{lat}E{lon}", lic, min_bytes=10000)


# ------------------------------------------------------------------ S35 AquaCrop
def dl_aquacrop():
    lic = "(c) FAO 2026 - all rights reserved; non-commercial use authorised free on request (copyright@fao.org)"
    rel = S.get("https://api.github.com/repos/un-fao/fao-AquaCrop/releases/tags/v7.3", timeout=60).json()
    out = RAW / "simulation/aquacrop"
    json.dump(rel, open(out / "github_release_v7.3.json", "w"), indent=1)
    for a in rel["assets"]:
        if a["name"] in ("GUI_AC7.3.zip", "ReleaseNoteAquaCropV73July2026.pdf", "python.source.code.zip"):
            sha = (a.get("digest") or "").replace("sha256:", "") or None
            fetch(a["browser_download_url"], out / a["name"], f"S35 AquaCrop {a['name']}", lic, expect_sha=sha)
    # extraction (originals untouched): separate directories
    for z, d in (("python.source.code.zip", ROOT / "simulator/aquacrop/official_src"), ("GUI_AC7.3.zip", ROOT / "simulator/aquacrop/gui_ac73")):
        if (out / z).exists() and not d.exists():
            with zipfile.ZipFile(out / z) as zf:
                zf.extractall(d)
            log(f"S35 extracted {z}", str(out / z), d, "EXTRACTED", lic=lic)


# ------------------------------------------------------------------ P29 / P30 image datasets
def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def dl_plantvillage():
    lic = "PlantVillage (Hughes & Salathe 2015; Mohanty et al. 2016) - CC BY-SA 3.0"
    d = RAW / "plant_health/plantvillage/PlantVillage-Dataset"
    url = "https://github.com/spMohanty/PlantVillage-Dataset.git"
    if not d.exists():
        r = git("clone", "--depth", "1", "--filter=blob:none", "--sparse", url, str(d))
        if r.returncode: log("P29 PlantVillage", url, None, "FAILED", r.stderr, lic); return
    r = git("sparse-checkout", "set", "raw/color", "leaf_grouping", cwd=d)
    head = git("rev-parse", "HEAD", cwd=d).stdout.strip()
    log("P29 PlantVillage raw/color (git sparse, commit " + head[:10] + ")", url, d, "OK" if not r.returncode else "FAILED", r.stderr, lic)
    for f in ("splits/color_train.txt", "splits/color_test.txt", "leaf_grouping/leaf-map.json"):
        fetch(f"https://huggingface.co/datasets/mohanty/PlantVillage/resolve/main/{f}", RAW / "plant_health/plantvillage/hf_splits" / f,
              f"P29 PlantVillage leaf-grouped split {f}", lic)


def dl_plantdoc():
    lic = "PlantDoc (Singh et al. 2020) - CC BY 4.0"
    # git checkout fails on Windows: some filenames contain '?' (illegal on NTFS). Use the official archive and
    # sanitise names on extraction ('?' -> '_'); renames are recorded in RENAMED_FILES.csv. The archive is kept unmodified.
    base = RAW / "plant_health/plantdoc"
    url = "https://codeload.github.com/pratikkayal/PlantDoc-Dataset/zip/refs/heads/master"
    z = fetch(url, base / "PlantDoc-Dataset-master.zip", "P30 PlantDoc archive (master)", lic, min_bytes=100_000_000, timeout=3600)
    if not z: return
    d = base / "PlantDoc-Dataset"
    if (d / "RENAMED_FILES.csv").exists():
        log("P30 PlantDoc extracted", url, d, "SKIPPED_EXISTS", lic=lic); return
    bad = '?<>:"|*'
    renamed = []
    with zipfile.ZipFile(z) as zf:
        for m in zf.infolist():
            if m.is_dir(): continue
            parts = m.filename.split("/")[1:]  # drop top-level folder
            clean = ["".join("_" if c in bad else c for c in p).rstrip(" .") for p in parts]
            out = d.joinpath(*clean)
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(m) as src, open(out, "wb") as dst:
                dst.write(src.read())
            if clean != parts: renamed.append(("/".join(parts), "/".join(clean)))
    with open(d / "RENAMED_FILES.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("original", "sanitised")] + renamed)
    log("P30 PlantDoc extracted", url, d, "EXTRACTED", f"{len(renamed)} filenames sanitised", lic)


# ------------------------------------------------------------------ P32 / P33 references
NIPHM_MH = ["Cotton", "Soyabean", "Rice", "Sugarcane", "Wheat", "Maize", "Sorghum", "Pearlmillet", "Redgram", "Chickpea",
            "BlackgramandGreengram", "Groundnut", "Sunflower", "Safflower", "Sesame", "Onion", "Tomato", "Brinjal", "Chilli", "Okra",
            "CabbageandCauliflower", "Grapes", "Pomegranate", "Banana", "Mango", "Citrus", "Guava", "Cashew", "Turmeric", "Garlic",
            "Potato", "CustardApple", "Sapota", "Coconut", "Ber", "Drumstick", "CucurbitaceousVegetable", "Ginger", "Papaya"]
PPQS_MUP = ["MUP%20%28insecticide%29%20%2030.09.2026.pdf", "Fungicide%20MUP%20%20as%20on%2030.09.2026.pdf",
            "3.%20bio%20fungicides%20MUP%20as%20on%2030.09.2026.pdf", "4.%20Herbicides%20MUP%20as%20on%2030.09.2026.pdf",
            "5.%20PGR%20MUP%20as%20on%2030.09.2026.pdf", "MUP%20%28bio%20insecticide%29%2030.09.2026.pdf"]


def dl_references():
    from urllib.parse import unquote
    lic_n = "NIPHM / DPPQ&S AESA-based IPM packages - Government of India publication, reference use with citation"
    for c in NIPHM_MH:
        fetch(f"https://niphm.gov.in/IPMPackages/{c}.pdf", RAW / f"plant_health/ipm_references/ipm/NIPHM_IPM_{c}.pdf", f"P32 IPM package {c}", lic_n, min_bytes=20000)
        time.sleep(1)
    lic_c = "CIB&RC Major Uses of Pesticides (as on 30.09.2026) - official label-claim compilation; guidance, not legal document"
    for f in PPQS_MUP:
        name = unquote(f).replace(" ", "_").replace("(", "").replace(")", "")
        fetch(f"https://ppqs.gov.in/sites/default/files/{f}", RAW / f"plant_health/ipm_references/cibrc/{name}", f"P33 CIB&RC {unquote(f)}", lic_c, min_bytes=20000)
        time.sleep(1)


TASKS = {"E18a": dl_boundaries, "B5": dl_power, "B6": dl_imd, "B7": dl_imd, "B8": dl_chirps, "D14": dl_soilgrids,
         "D14b": dl_soilgrids2017, "E17": dl_dem, "S35b": dl_aquacrop, "P29": dl_plantvillage, "P30": dl_plantdoc,
         "P32": dl_references, "P33": dl_references}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*"); ap.add_argument("--list", action="store_true")
    ap.add_argument("--sg-quantities", nargs="*", default=["mean"])
    a = ap.parse_args()
    audit = ROOT / "reports/dataset_audit/dataset_audit.json"
    status = {d["dataset_id"]: d["status"] for d in json.load(open(audit))["datasets"]} if audit.exists() else {}
    todo = a.only or [k for k in TASKS if not status.get(k, "").startswith("PRESENT AND VALID") and CATALOG[k]["access"] == "public_auto"]
    if a.list:
        for k in TASKS: print(k, status.get(k, "?"), CATALOG[k]["name"], "|", CATALOG[k]["size_hint"])
        return
    done = set()
    for k in todo:
        fn = TASKS[k]
        if fn in done: continue
        done.add(fn)
        print(f"===== {k}: {CATALOG[k]['name']}")
        try:
            fn(quantities=tuple(a.sg_quantities)) if fn is dl_soilgrids else fn()
        except Exception as e:
            log(k, CATALOG[k]["source"], None, "FAILED", f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
