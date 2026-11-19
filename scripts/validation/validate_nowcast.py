"""Backtest of the water-balance nowcast against SMAP (consistency check, NOT ground truth).

Design: a reference surface (Kc = 1.0, fixed 1.0 m root zone, no irrigation) per district.
For many start dates t0 (Jun-Feb seasons 2016-2024): initialise depletion from SMAP on t0, run the FAO-56
balance with OBSERVED weather (IMD rain, POWER ETo) to t0+L, and compare the predicted relative depletion
with the SMAP-implied relative depletion on t0+L. Baseline = persistence (depletion unchanged).
Skill = 1 - MAE_model / MAE_persistence. Leads L = 3, 7, 14 days.

Writes reports/monitor_validation/nowcast_backtest.csv and prints a summary.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from geocrop.monitor import nowcast as nc  # noqa: E402
from geocrop.monitor import soilwater  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "reports/monitor_validation"
OUT.mkdir(parents=True, exist_ok=True)
LEADS = (3, 7, 14)
ZR = 1.0


def simulate(dr0_frac, w, taw, p_tab=0.5, kc=None):
    dr = dr0_frac * taw
    out = []
    kc = np.ones(len(w)) if kc is None else kc
    for p_mm, eto, k in zip(w.rain_mm.values, w.eto_mm.values, kc):
        etc = k * eto
        p = float(np.clip(p_tab + 0.04 * (5 - etc), 0.1, 0.8))
        raw = p * taw
        ks = 1.0 if dr <= raw else max(0.0, (taw - dr) / ((1 - p) * taw))
        dr = float(np.clip(dr - p_mm + ks * etc, 0, taw))
        out.append(dr / taw)
    return np.array(out)


def landscape_kc(did):
    """Daily landscape coefficient = MODIS MOD16A2GF ET/PET (cropland mask) for the composite covering each day."""
    from geocrop.config import SERIES_DIR
    r = pd.read_parquet(SERIES_DIR / "MOD16A2GF", filters=[("district_id", "==", did), ("variable", "==", "et_pet_ratio"), ("mask", "==", "cropland")])
    r = r.set_index(pd.to_datetime(r.date))["mean"].sort_index()
    return r.resample("D").ffill().clip(0.05, 1.2)


def main(n_starts=40, seed=0, kc_mode="unit"):
    rng = np.random.default_rng(seed)
    rows = []
    for did in range(1, 37):
        kcs = landscape_kc(did) if kc_mode == "landscape" else None
        smap, _ = nc.smap_relative_wetness(did)
        smap = smap.dropna(subset=["rel_wetness"])
        taw = soilwater.taw_mm(nc.soil_profile(did), ZR)
        w = nc.weather_for_district(did, "2016-01-01", "2025-03-01").set_index("date")
        cands = smap.index[(smap.index.year >= 2016) & (smap.index.year <= 2024) & smap.index.month.isin([6, 7, 8, 9, 10, 11, 12, 1, 2])]
        for t0 in rng.choice(cands, size=min(n_starts, len(cands)), replace=False):
            t0 = pd.Timestamp(t0)
            ww = w.loc[t0 + pd.Timedelta(days=1): t0 + pd.Timedelta(days=max(LEADS))]
            if len(ww) < max(LEADS) or ww[["rain_mm", "eto_mm"]].isna().any().any():
                continue
            dr0 = 1 - smap.loc[t0, "rel_wetness"]
            kc = None if kcs is None else kcs.reindex(ww.index).ffill().fillna(1.0).values
            traj = simulate(dr0, ww, taw, kc=kc)
            for L in LEADS:
                tl = t0 + pd.Timedelta(days=L)
                if tl not in smap.index:
                    continue
                rows.append(dict(district_id=did, t0=t0.date(), lead=L, month=t0.month, obs=1 - smap.loc[tl, "rel_wetness"],
                                 model=traj[L - 1], persistence=dr0, rain_mm=ww.rain_mm.iloc[:L].sum()))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / f"nowcast_backtest_{kc_mode}.csv", index=False)
    summ = []
    for L, g in df.groupby("lead"):
        mae_m = (g.model - g.obs).abs().mean(); mae_p = (g.persistence - g.obs).abs().mean()
        summ.append(dict(lead_days=L, n=len(g), r_model=round(g.model.corr(g.obs), 3), r_persistence=round(g.persistence.corr(g.obs), 3),
                         mae_model=round(mae_m, 3), mae_persistence=round(mae_p, 3), skill_vs_persistence=round(1 - mae_m / mae_p, 3),
                         bias_model=round((g.model - g.obs).mean(), 3)))
    s = pd.DataFrame(summ)
    s.insert(0, "kc_mode", kc_mode)
    s.to_csv(OUT / f"nowcast_backtest_summary_{kc_mode}.csv", index=False)
    wet = df[df.rain_mm > 20]; dry = df[df.rain_mm < 2]
    print(s.to_string(index=False))
    for name, g in (("rainy windows (>20 mm)", wet), ("dry windows (<2 mm)", dry)):
        g = g[g.lead == 7]
        print(name, "lead 7: MAE model", round((g.model - g.obs).abs().mean(), 3), "persistence", round((g.persistence - g.obs).abs().mean(), 3), "n", len(g))
    return s


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "unit"
    main(kc_mode=mode)
