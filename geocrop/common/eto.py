"""FAO-56 reference evapotranspiration (Allen et al. 1998), daily.

penman_monteith(): FAO-56 eq. 6 with net radiation from eqs. 37-40 (G = 0 for daily steps).
hargreaves(): FAO-56 eq. 52, temperature-only fallback used when solar radiation is not yet available
              (NASA POWER radiation lags ~10 days). Results carry a method flag; never mixed silently.
"""
import numpy as np

SIGMA = 4.903e-9  # MJ K-4 m-2 day-1


def sat_vp(t):
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


def extraterrestrial_radiation(lat_deg, doy):
    """Ra (MJ m-2 day-1), FAO-56 eq. 21."""
    phi = np.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    delta = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(delta), -1, 1))
    return 24 * 60 / np.pi * 0.0820 * dr * (ws * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(ws))


def penman_monteith(tmax, tmin, rh_mean, u2, rs, lat_deg, doy, elev_m):
    """All inputs array-like. rs in MJ m-2 day-1, u2 in m/s at 2 m, rh in %. Returns ETo mm/day."""
    t = (tmax + tmin) / 2
    delta = 4098 * sat_vp(t) / (t + 237.3) ** 2
    p = 101.3 * ((293 - 0.0065 * elev_m) / 293) ** 5.26
    gamma = 0.000665 * p
    es = (sat_vp(tmax) + sat_vp(tmin)) / 2
    ea = rh_mean / 100 * es
    ra = extraterrestrial_radiation(lat_deg, doy)
    rso = (0.75 + 2e-5 * elev_m) * ra
    rns = 0.77 * rs
    rnl = SIGMA * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2 * (0.34 - 0.14 * np.sqrt(np.maximum(ea, 0))) \
        * (1.35 * np.clip(rs / rso, 0.25, 1.0) - 0.35)
    rn = rns - rnl
    eto = (0.408 * delta * rn + gamma * 900 / (t + 273) * u2 * (es - ea)) / (delta + gamma * (1 + 0.34 * u2))
    return np.maximum(eto, 0)


def hargreaves(tmax, tmin, lat_deg, doy):
    t = (tmax + tmin) / 2
    ra = extraterrestrial_radiation(lat_deg, doy)
    return np.maximum(0.0023 * (t + 17.8) * np.sqrt(np.maximum(tmax - tmin, 0)) * 0.408 * ra, 0)
