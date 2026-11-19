"""Area weights of regular lat/lon grid cells within each district.

Coarse grids (IMD 0.25 deg, CHIRPS 0.25 deg, POWER 0.5 x 0.625 deg, IMD temp 1 deg) are larger than small
districts (Mumbai City ~ 70 km2), so cell-centre assignment would leave districts empty. Instead each cell is
super-sampled (default 20 x 20) and the fraction falling in each district becomes its weight.
"""
import hashlib

import numpy as np
from rasterio.features import rasterize
from rasterio.transform import from_origin

from geocrop.common.districts import districts
from geocrop.config import LABEL_CACHE


def grid_weights(lat, lon, ss=20):
    """Return W (n_district=36, n_lat, n_lon) of area fractions; lat/lon are cell-centre 1-D arrays (any order)."""
    lat = np.asarray(lat, float); lon = np.asarray(lon, float)
    key = hashlib.sha1(f"{lat.round(4).tobytes()}|{lon.round(4).tobytes()}|{ss}".encode()).hexdigest()[:16]
    f = LABEL_CACHE / f"gridw_{key}.npy"
    if f.exists():
        return np.load(f)
    dy, dx = abs(lat[1] - lat[0]), abs(lon[1] - lon[0])
    north = lat.max() + dy / 2; west = lon.min() - dx / 2
    ny, nx = len(lat), len(lon)
    tr = from_origin(west, north, dx / ss, dy / ss)
    g = districts()
    lab = rasterize(((geom, int(i)) for geom, i in zip(g.geometry, g.district_id)), out_shape=(ny * ss, nx * ss),
                    transform=tr, fill=0, dtype="int16")
    W = np.zeros((36, ny, nx), dtype="float32")
    blocks = lab.reshape(ny, ss, nx, ss)
    for i in range(1, 37):
        W[i - 1] = (blocks == i).sum(axis=(1, 3)) / ss ** 2   # rows ordered north -> south
    if lat[0] < lat[-1]:  # caller's lat ascending -> flip rows to match
        W = W[:, ::-1, :]
    np.save(f, W)
    return W


def district_means(field, W):
    """field (..., n_lat, n_lon) with NaN; returns (..., 36) area-weighted means over valid cells."""
    valid = np.isfinite(field)
    f0 = np.where(valid, field, 0.0)
    num = np.einsum("...yx,dyx->...d", f0, W)
    den = np.einsum("...yx,dyx->...d", valid.astype("float32"), W)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan), den
