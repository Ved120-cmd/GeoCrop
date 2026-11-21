"""Crop Advisor evidence base: AquaCrop runs for every district x season x crop x sowing date x water mode x past year.

Each run is a real past season (district weather + soil + SMAP initial water). Only seasons whose whole crop cycle
had observed weather are used later. Output: data/processed/advisor/runs/d{district_id}.parquet (resumable).

Run:  python -m geocrop.advisor.precompute        (~3 h for 36 districts: one process, 10 engine processes; more processes thrash memory on 16 GB)
"""
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta

import pandas as pd

from geocrop.config import PROCESSED

OUT = PROCESSED / "advisor" / "runs"

# Season -> candidate sowing dates (month, day) and crops available in the simulator.
# Windows are the standard Indian kharif (monsoon) and rabi (post-monsoon) seasons; the dates span early/normal/late.
SEASONS = {
    "kharif": dict(sow=[(6, 15), (7, 1), (7, 15)], crops=["soybean", "cotton", "maize", "sorghum", "sunflower"]),
    # 1 Oct added: rainfed rabi (jowar) is sown on moisture stored after the monsoon, from late September
    "rabi": dict(sow=[(10, 1), (10, 15), (11, 1), (11, 15)], crops=["wheat", "sorghum", "sunflower", "maize", "potato", "tomato"]),
}
WATER = ("rainfed", "irrigated")
FIRST_YEAR = 2015


def _irrigation(water):
    from geocrop.simulator.scenario import Irrigation
    # irrigated = AquaCrop net irrigation: refill whenever depletion passes 50% of readily available water (no water limit)
    return Irrigation("rainfed") if water == "rainfed" else Irrigation("net", allowable_depletion_raw_pct=50, method=4)


def district(did: int, parallel: int = 10) -> str:
    from geocrop.simulator import scenario as sc
    f = OUT / f"d{did:02d}.parquet"
    old = pd.read_parquet(f) if f.exists() else None
    done = set() if old is None else set(zip(old.season, old.crop, old.water, old.sow_mmdd))
    t0, rows, nerr = time.time(), [], 0
    last = sc.last_weather_date(did)
    for season, cfg in SEASONS.items():
        for crop in cfg["crops"]:
            maxdays = sc.CROPS[crop][4]
            for water in WATER:
                sows = [date(y, m, d) for y in range(FIRST_YEAR, last.year + 1) for (m, d) in cfg["sow"]
                        if (season, crop, water, f"{m:02d}-{d:02d}") not in done
                        and date(y, m, d) >= date(FIRST_YEAR, 4, 1) and date(y, m, d) + timedelta(days=maxdays + sc.CLIM_MARGIN) <= last]
                if not sows:
                    continue
                try:
                    res, err = sc.run_seasons(did, crop, sows, _irrigation(water), parallel=parallel)
                except Exception as e:  # e.g. engine timeout after the laptop slept: skip; the next run fills the gap
                    print(f"d{did} {season} {crop} {water}: skipped ({type(e).__name__})", flush=True)
                    nerr += len(sows); continue
                nerr += len(err)
                for r in res:
                    sow = date.fromisoformat(r["sow_date"])
                    rows.append(dict(district_id=did, season=season, crop=crop, water=water, sow_mmdd=f"{sow.month:02d}-{sow.day:02d}",
                                     season_year=sow.year, **{k: r[k] for k in (
                                         "yield_t_ha", "yield_type", "biomass_t_ha", "cycle_days", "rain_mm", "irrigation_mm", "eto_mm",
                                         "transpiration_mm", "water_stress_stomata_pct", "temperature_stress_pct", "water_productivity_kg_m3",
                                         "complete_observed_weather", "initial_water", "engine_failed")}))
    if not rows:
        return f"d{did}: up to date"
    OUT.mkdir(parents=True, exist_ok=True)
    new = pd.DataFrame(rows)
    (new if old is None else pd.concat([old, new], ignore_index=True)).to_parquet(f, index=False)
    return f"d{did}: {len(rows)} seasons, {nerr} errors, {(time.time() - t0) / 60:.1f} min"


def main(processes=1):
    from geocrop.common.districts import district_table
    ids = [int(i) for i in district_table().district_id]  # existing files are topped up with missing combinations only
    print(f"{len(ids)} districts to simulate with {processes} processes", flush=True)
    with ProcessPoolExecutor(processes) as ex:
        futs = {ex.submit(district, i): i for i in ids}
        for f in futs:  # in submission order; one failed district must not cancel the others
            try:
                print(f.result(), flush=True)
            except Exception as e:
                print(f"d{futs[f]}: FAILED {type(e).__name__}: {str(e)[:200]}", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
