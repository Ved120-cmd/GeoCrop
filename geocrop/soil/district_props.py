"""District soil property summary from SoilGrids 2.0 (cropland mean, all-land fallback), 6 depths.

Values are converted to conventional units with the ISRIC conversion factors. These are GLOBAL MODEL
ESTIMATES at 250 m, not laboratory measurements, and are labelled so in the API.
Output: data/processed/soil/district_soilgrids.parquet (long format)
"""
import numpy as np
import pandas as pd
import rasterio

from geocrop.common.zonal import zonal_all_and_cropland
from geocrop.config import PROCESSED, RAW

SG2 = RAW / "soil/soilgrids/sg2"
DEPTHS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm"]
# property: (divisor to conventional unit, unit, label)
PROPS = {
    "clay": (10, "%", "Clay"), "sand": (10, "%", "Sand"), "silt": (10, "%", "Silt"),
    "phh2o": (10, "pH", "pH (water)"), "soc": (10, "g/kg", "Soil organic carbon"),
    "cec": (10, "cmol(c)/kg", "Cation exchange capacity"), "nitrogen": (100, "g/kg", "Total nitrogen"),
    "bdod": (100, "g/cm3", "Bulk density"), "cfvo": (10, "% vol", "Coarse fragments"), "ocd": (10, "kg/m3", "Organic carbon density"),
}
OUT = PROCESSED / "soil/district_soilgrids.parquet"


def build():
    rows = []
    for prop, (div, unit, label) in PROPS.items():
        for d in DEPTHS:
            with rasterio.open(SG2 / prop / f"{prop}_{d}_mean.tif") as src:
                a = src.read(1).astype("float32")
                a[a == src.nodata] = np.nan
                z = zonal_all_and_cropland(a / div, src.crs.to_wkt(), src.transform, (src.height, src.width), 2020)
            c = z[z["mask"] == "cropland"].set_index("district_id"); al = z[z["mask"] == "all"].set_index("district_id")
            use_c = c.n_valid >= 50
            for did in c.index:
                src_ = c if use_c[did] else al
                rows.append(dict(district_id=int(did), property=prop, label=label, unit=unit, depth=d,
                                 mean=float(src_.loc[did, "mean"]), p10=float(src_.loc[did, "p10"]), p90=float(src_.loc[did, "p90"]),
                                 mask_used="cropland" if use_c[did] else "all_land"))
        print(prop, "done", flush=True)
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    return df


def usda_texture(sand, clay):
    """USDA texture class from sand/clay % (silt = remainder)."""
    silt = 100 - sand - clay
    if clay >= 40 and silt < 40 and sand <= 45: return "Clay"
    if clay >= 40 and silt >= 40: return "Silty clay"
    if clay >= 35 and sand > 45: return "Sandy clay"
    if 27 <= clay < 40 and sand <= 20: return "Silty clay loam"
    if 27 <= clay < 40 and 20 < sand <= 45: return "Clay loam"
    if 20 <= clay < 35 and silt < 28 and sand > 45: return "Sandy clay loam"
    if silt >= 80 and clay < 12: return "Silt"
    if silt >= 50 and (12 <= clay < 27 or (silt < 80 and clay < 12)): return "Silt loam"
    if 7 <= clay < 27 and 28 <= silt < 50 and sand <= 52: return "Loam"
    if (silt + 1.5 * clay) < 15: return "Sand"
    if (silt + 1.5 * clay) >= 15 and (silt + 2 * clay) < 30: return "Loamy sand"
    return "Sandy loam"


if __name__ == "__main__":
    print(build().shape)
