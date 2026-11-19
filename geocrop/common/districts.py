"""District registry and district-label rasters on any product grid.

District ids are stable integers 1..36 (sorted by current official name). Names come from the crosswalk so
geoBoundaries (2021 names), DES (current names) and the UI all agree.
"""
import hashlib
from functools import lru_cache

import numpy as np
import pandas as pd

from geocrop.config import CROSSWALK, DISTRICT_FILE, LABEL_CACHE


@lru_cache(maxsize=1)
def districts():
    """GeoDataFrame: district_id, district (current name), gb_name, geometry (EPSG:4326)."""
    import geopandas as gpd
    g = gpd.read_file(DISTRICT_FILE)
    cw = pd.read_csv(CROSSWALK)
    g = g.merge(cw[["geoboundaries_name", "current_official_name"]], left_on="district", right_on="geoboundaries_name", how="left")
    if g.current_official_name.isna().any():
        raise ValueError(f"crosswalk missing: {g[g.current_official_name.isna()].district.tolist()}")
    g = g.rename(columns={"district": "gb_name", "current_official_name": "district"})
    g = g.sort_values("district").reset_index(drop=True)
    g["district_id"] = np.arange(1, len(g) + 1, dtype="int16")
    return g[["district_id", "district", "gb_name", "geometry"]]


def district_table():
    return districts().drop(columns="geometry")


def label_raster(crs_wkt: str, transform, shape):
    """int16 array with district_id per pixel (0 = outside Maharashtra), cached on disk per grid."""
    from rasterio.features import rasterize
    key = hashlib.sha1(f"{crs_wkt}|{tuple(transform)[:6]}|{shape}".encode()).hexdigest()[:16]
    f = LABEL_CACHE / f"districts_{key}.npy"
    if f.exists():
        return np.load(f)
    g = districts().to_crs(crs_wkt)
    lab = rasterize(((geom, int(i)) for geom, i in zip(g.geometry, g.district_id)), out_shape=shape,
                    transform=transform, fill=0, dtype="int16", all_touched=False)
    np.save(f, lab)
    return lab
