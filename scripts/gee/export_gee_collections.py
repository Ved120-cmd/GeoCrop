"""Export GeoCrop Earth Engine datasets for Maharashtra (2015-2025) at NATIVE resolution/projection.

Why this exists: the earlier exports in datasets/out*.tif were produced without a `region`,
so Earth Engine exported a default 0-2 deg lon/lat tile in the Gulf of Guinea containing only zeros.

Prerequisites (one-time, done by YOU - requires your Google account):
    pip install earthengine-api
    earthengine authenticate
    # create / pick a Cloud project with the Earth Engine API enabled

Usage:
    python scripts/gee/export_gee_collections.py --project YOUR_GCP_PROJECT --dataset MOD13Q1 --dry-run
    python scripts/gee/export_gee_collections.py --project YOUR_GCP_PROJECT --dataset MOD13Q1
Exports go to Google Drive folder GeoCrop_<dataset>; download them into data/raw/... (see DEST) and re-run the audit.

Notes on science rules:
  * QA bands are exported together with the science bands (never pre-masked, never zero-filled).
  * Scale factors are NOT applied here (raw integers preserved); apply in preprocessing.
  * SMAP L4 is 3-hourly; exporting all 3-hourly steps for 11 years is ~32k images. Default here is daily mean
    of sm_surface / sm_rootzone (documented aggregation) - change --smap-native to export raw steps for a short window.
"""
import argparse

DATASETS = {
    # id: (collection, bands, native scale m, crs, dest)
    "MOD13Q1": ("MODIS/061/MOD13Q1", ["NDVI", "EVI", "SummaryQA", "DetailedQA", "DayOfYear"], 231.656358264, "SR-ORG:6974", "data/raw/modis/mod13q1"),
    "MOD11A2": ("MODIS/061/MOD11A2", ["LST_Day_1km", "LST_Night_1km", "QC_Day", "QC_Night"], 926.625433055, "SR-ORG:6974", "data/raw/modis/mod11a2"),
    "MOD16A2GF": ("MODIS/061/MOD16A2GF", ["ET", "PET", "LE", "PLE", "ET_QC"], 463.312716528, "SR-ORG:6974", "data/raw/modis/mod16a2gf"),
    "MCD12Q1": ("MODIS/061/MCD12Q1", ["LC_Type1", "LC_Type2", "QC", "LW"], 463.312716528, "SR-ORG:6974", "data/raw/modis/mcd12q1"),
    "SMAP": ("NASA/SMAP/SPL4SMGP/008", ["sm_surface", "sm_rootzone", "sm_profile"], 11000, "EPSG:6933", "data/raw/soil/smap"),
    "IMERG": ("NASA/GPM_L3/IMERG_V07", ["precipitation"], 11132, "EPSG:4326", "data/raw/weather/gpm"),
    "CHIRPS": ("UCSB-CHG/CHIRPS/DAILY", ["precipitation"], 5566, "EPSG:4326", "data/raw/weather/chirps/gee"),
}


def mh_region(ee):
    # FAO GAUL 2015 level-1 - state outline only (district configuration in GAUL is outdated; use geoBoundaries locally).
    return (ee.FeatureCollection("FAO/GAUL/2015/level1").filter(ee.Filter.eq("ADM1_NAME", "Maharashtra"))
            .geometry().bounds().buffer(5000))


def daily_mean(ee, col, bands, start, end):
    s, e = ee.Date(start), ee.Date(end)
    n = e.difference(s, "day").toInt()
    def f(i):
        d = s.advance(i, "day")
        return (col.filterDate(d, d.advance(1, "day")).select(bands).mean()
                .set("system:time_start", d.millis()).set("system:index", d.format("YYYYMMdd")))
    return ee.ImageCollection(ee.List.sequence(0, n.subtract(1)).map(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True); ap.add_argument("--dataset", required=True, choices=DATASETS)
    ap.add_argument("--start", default="2015-01-01"); ap.add_argument("--end", default="2026-01-01")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--smap-native", action="store_true")
    a = ap.parse_args()
    import ee
    ee.Initialize(project=a.project)
    cid, bands, scale, crs, dest = DATASETS[a.dataset]
    region = mh_region(ee)
    col = ee.ImageCollection(cid).filterDate(a.start, a.end).filterBounds(region)
    if a.dataset in ("SMAP", "IMERG") and not a.smap_native:
        col = daily_mean(ee, ee.ImageCollection(cid).filterBounds(region), bands, a.start, a.end)
    ids = col.aggregate_array("system:index").getInfo()
    print(f"{a.dataset}: {len(ids)} images {a.start}..{a.end}; bands {bands}; scale {scale} m; crs {crs}; local dest {dest}")
    if a.dry_run:
        print(ids[:5], "..."); return
    lst = col.toList(len(ids))
    for i, iid in enumerate(ids):
        img = ee.Image(lst.get(i)).select(bands)
        if a.dataset != "MCD12Q1":
            img = img.toFloat() if a.dataset in ("SMAP", "IMERG", "CHIRPS") else img.toInt32()
        t = ee.batch.Export.image.toDrive(image=img, description=f"{a.dataset}_{iid}".replace("/", "_")[:100],
                                          folder=f"GeoCrop_{a.dataset}", fileNamePrefix=f"{a.dataset}_{iid}".replace("/", "_"),
                                          region=region, scale=scale, crs=crs, maxPixels=1e10, fileFormat="GeoTIFF")
        t.start()
        if i % 25 == 0: print(f"  queued {i + 1}/{len(ids)}")
    print("All tasks queued - monitor at https://code.earthengine.google.com/tasks")


if __name__ == "__main__":
    main()
