"""Soil water-holding properties for the water balance.

theta_wp  = WWP          (vol. water content at wilting point, -1500 kPa)        SoilGrids250m 2017
theta_fc  = WWP + AWCh3  (AWCh3 = AVAILABLE water capacity with FC at pF 2.5 / -31.6 kPa)
theta_sat = AWCtS        (saturated water content)
at standard depths sl1..sl7 = 0, 5, 15, 30, 60, 100, 200 cm (values in % vol -> m3/m3).

TAW(Zr) = 1000 * integral_0^Zr (theta_fc - theta_wp) dz   [mm], trapezoidal over the depth points.
These are global-model estimates (not lab data) and are labelled as such everywhere they are used.
"""
from functools import lru_cache

import numpy as np
import pandas as pd
import rasterio

from geocrop.common.zonal import zonal_all_and_cropland
from geocrop.config import PROCESSED, RAW

SG17 = RAW / "soil/soilgrids/sg2017_water"
DEPTHS_M = np.array([0.0, 0.05, 0.15, 0.30, 0.60, 1.00, 2.00])
OUT = PROCESSED / "soil/district_soil_water.parquet"


def _crop_or_all(z, min_px=50):
    """Cropland mean per district; districts with < min_px cropland pixels (e.g. Mumbai City) fall back to all land."""
    c = z[z["mask"] == "cropland"].set_index("district_id")
    a = z[z["mask"] == "all"].set_index("district_id")
    use = c["n_valid"] >= min_px
    return c["mean"].where(use, a["mean"]), (~use)


def _path(var, sl):
    return SG17 / f"{var}_M_sl{sl}_250m_ll_MH.tif"


def build_district_table():
    rows = []
    for var, name in (("AWCh3", "awc"), ("WWP", "theta_wp"), ("AWCtS", "theta_sat")):
        for sl in range(1, 8):
            with rasterio.open(_path(var, sl)) as src:
                a = src.read(1).astype("float32")
                a[(a == src.nodata) | (a > 100)] = np.nan
                z = zonal_all_and_cropland(a / 100.0, src.crs.to_wkt(), src.transform, (src.height, src.width), 2020)
            m, fb = _crop_or_all(z)
            rows.append(m.rename(f"{name}_sl{sl}"))
    df = pd.concat(rows, axis=1)
    df["mask_used"] = np.where(fb, "all_land", "cropland")
    df = df.reset_index()
    for i in range(1, 8):
        df[f"theta_fc_sl{i}"] = df[f"theta_wp_sl{i}"] + df[f"awc_sl{i}"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    return df


@lru_cache(maxsize=1)
def district_table():
    return pd.read_parquet(OUT) if OUT.exists() else build_district_table()


def point_profile(lat, lon):
    """theta profiles at a point (nearest 250 m pixel)."""
    prof = {}
    for var, name in (("AWCh3", "awc"), ("WWP", "theta_wp"), ("AWCtS", "theta_sat")):
        vals = []
        for sl in range(1, 8):
            with rasterio.open(_path(var, sl)) as src:
                v = next(src.sample([(lon, lat)]))[0]
                vals.append(np.nan if v == src.nodata or v > 100 else v / 100.0)
        prof[name] = np.array(vals)
    prof["theta_fc"] = prof["theta_wp"] + prof["awc"]
    return prof


def profile_for_district(district_id):
    r = district_table().set_index("district_id").loc[district_id]
    return {n: np.array([r[f"{n}_sl{i}"] for i in range(1, 8)]) for n in ("theta_fc", "theta_wp", "theta_sat")}


# ---------------------------------------------------------------- Saxton & Rawls (2006) pedotransfer cross-check
SG2 = RAW / "soil/soilgrids/sg2"
SG2_DEPTHS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm"]
SG2_MID_M = np.array([0.025, 0.10, 0.225, 0.45, 0.80, 1.50])
OUT_SR = PROCESSED / "soil/district_soil_water_saxton_rawls.parquet"


def saxton_rawls(sand_frac, clay_frac, om_pct):
    """Saxton, K.E. & Rawls, W.J. (2006) SSSAJ 70:1569-1578, Table 1 eqs. 1-3, 5. Returns theta_wp, theta_fc, theta_sat."""
    S, C, OM = sand_frac, clay_frac, om_pct
    t1500 = -0.024 * S + 0.487 * C + 0.006 * OM + 0.005 * S * OM - 0.013 * C * OM + 0.068 * S * C + 0.031
    wp = t1500 + (0.14 * t1500 - 0.02)
    t33 = -0.251 * S + 0.195 * C + 0.011 * OM + 0.006 * S * OM - 0.027 * C * OM + 0.452 * S * C + 0.299
    fc = t33 + (1.283 * t33 ** 2 - 0.374 * t33 - 0.015)
    ts33 = 0.278 * S + 0.034 * C + 0.022 * OM - 0.018 * S * OM - 0.027 * C * OM - 0.584 * S * C + 0.078
    s33 = ts33 + (0.636 * ts33 - 0.107)
    sat = fc + s33 - 0.097 * S + 0.043
    return wp, fc, sat


def build_saxton_rawls_table():
    """District (cropland) theta profiles from SoilGrids 2.0 sand/clay/SOC via Saxton-Rawls, at SG2 depth midpoints."""
    vals = {}
    for prop, scale in (("sand", 10.0), ("clay", 10.0), ("soc", 10.0)):  # g/kg -> %, dg/kg -> g/kg
        for d in SG2_DEPTHS:
            with rasterio.open(SG2 / prop / f"{prop}_{d}_mean.tif") as src:
                a = src.read(1).astype("float32")
                a[a == src.nodata] = np.nan
                z = zonal_all_and_cropland(a / scale, src.crs.to_wkt(), src.transform, (src.height, src.width), 2020)
            vals[(prop, d)], fb = _crop_or_all(z)
    out = pd.DataFrame(index=vals[("sand", SG2_DEPTHS[0])].index)
    for i, d in enumerate(SG2_DEPTHS, 1):
        S = vals[("sand", d)] / 100; C = vals[("clay", d)] / 100
        OM = vals[("soc", d)] / 10 * 1.724  # SOC g/kg -> % ; OM = 1.724 * SOC (van Bemmelen factor)
        wp, fc, sat = saxton_rawls(S, C, OM)
        out[f"theta_wp_d{i}"], out[f"theta_fc_d{i}"], out[f"theta_sat_d{i}"] = wp, fc, sat
        out[f"sand_d{i}"], out[f"clay_d{i}"], out[f"om_d{i}"] = S * 100, C * 100, OM
    out["mask_used"] = np.where(fb, "all_land", "cropland")
    out = out.reset_index()
    out.to_parquet(OUT_SR, index=False)
    return out


def profile_for_district_sr(district_id):
    t = pd.read_parquet(OUT_SR) if OUT_SR.exists() else build_saxton_rawls_table()
    r = t.set_index("district_id").loc[district_id]
    return {n: np.array([r[f"{n}_d{i}"] for i in range(1, 7)]) for n in ("theta_fc", "theta_wp", "theta_sat")} | {"depths": SG2_MID_M}


def integrate(theta, zr, depths=None):
    """Depth integral (m of water per m2) of theta from 0 to zr metres, trapezoidal with interpolation at zr."""
    dp = DEPTHS_M if depths is None else depths
    z = np.concatenate(([0.0], dp[(dp > 0) & (dp < zr)], [zr]))
    t = np.interp(z, dp, theta)  # constant extrapolation above the shallowest / below the deepest point
    return float(np.trapezoid(t, z))


def taw_mm(profile, zr):
    d = profile.get("depths")
    return 1000 * (integrate(profile["theta_fc"], zr, d) - integrate(profile["theta_wp"], zr, d))
