"""Daily incremental update of GeoCrop Monitor.

Steps (each logged; a failing step does not stop the others):
  1. Satellite catch-up from Earth Engine: download only dates newer than the latest local file
     (MOD13Q1, MOD11A2, MOD16A2 [near-real-time ET, provisional], SMAP, IMERG).
  2. Provisional -> final: IMERG days older than 120 days still marked provisional are re-downloaded (Final Run)
     and their series rows replaced.
  3. NASA POWER: re-fetch the last 40 days for every MH cell (fills the ~10-day solar-radiation lag).
  4. ECMWF open-data forecast (latest IFS run).
  5. District series (incremental), weather tables, indices.
  6. Quality gate + freshness report -> reports/monitor_logs/update_<UTC timestamp>.json

Usage: python -m geocrop.monitor.update [--skip-gee] [--skip-power] [--skip-forecast]
"""
import argparse
import glob
import json
import subprocess
import sys
import time
import traceback
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests
from geocrop.common.safe_http import safe_get

from geocrop.config import GEE_PROJECT, RAW, ROOT, SERIES_DIR
from geocrop.monitor import build_series, indices, weather
from geocrop.monitor.products import PRODUCTS, file_date

LOGDIR = ROOT / "reports/monitor_logs"
LOGDIR.mkdir(parents=True, exist_ok=True)
GEE_PRODUCTS = ["MOD13Q1", "MOD11A2", "MOD16A2", "SMAP", "IMERG"]
POWER_VARS = "T2M,T2M_MAX,T2M_MIN,RH2M,PRECTOTCORR,WS2M,ALLSKY_SFC_SW_DWN"


def latest_local(product):
    rawdir, prefix, _ = PRODUCTS[product]
    fs = [f for f in glob.glob(str(RAW / rawdir / f"{prefix}_*.tif")) if ".part" not in f]
    return max((file_date(f) for f in fs), default=None)


def gee_catch_up(product, today):
    last = latest_local(product)
    if product == "MOD16A2" and last is None:  # start NRT ET right after the gap-filled archive
        last = latest_local("MOD16A2GF")
    start = (last + timedelta(days=1)) if last else date(2015, 1, 1)
    cmd = [sys.executable, "-u", str(ROOT / "scripts/gee/download_gee_direct.py"), "--project", GEE_PROJECT,
           "--product", product, "--start", str(start), "--end", str(today + timedelta(days=1)), "--workers", "4"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=6 * 3600)
    tail = (r.stdout + r.stderr).strip().splitlines()[-1:] if (r.stdout or r.stderr) else []
    if r.returncode != 0:
        raise RuntimeError(f"{product} downloader exited {r.returncode}: {tail}")
    return dict(product=product, from_date=str(start), latest_after=str(latest_local(product)), returncode=r.returncode, tail=tail)


def imerg_finalise(today):
    """Replace provisional IMERG days that are now old enough to exist as Final Run."""
    cutoff = today - timedelta(days=build_series.IMERG_FINAL_LAG_DAYS)
    redo = []
    for f in sorted((SERIES_DIR / "IMERG").glob("year=*.parquet")):
        df = pd.read_parquet(f)
        stale = df[(df.status == "provisional") & (df.date.dt.date < cutoff)].date.dt.date.unique()
        if len(stale):
            redo += list(stale)
            df[~df.date.dt.date.isin(stale)].to_parquet(f, index=False)
    for d in redo:
        p = RAW / f"weather/gpm/IMERG_{d:%Y_%m_%d}.tif"
        if p.exists():
            p.unlink()
    if redo:
        for d0 in sorted(set(redo)):
            subprocess.run([sys.executable, str(ROOT / "scripts/gee/download_gee_direct.py"), "--project", GEE_PROJECT, "--product", "IMERG",
                            "--start", str(d0), "--end", str(d0 + timedelta(days=1)), "--workers", "1"], capture_output=True, timeout=1800)
    return dict(imerg_days_finalised=len(redo))


def power_recent(today, days=40):
    """Fetch POWER from the end of the 2015-2025 archive (or today-days, whichever is earlier) to today, so the
    rolling 'recent' file always joins the archive without a gap; the last weeks are re-fetched to fill the
    solar-radiation lag."""
    arch = pd.read_csv(RAW / "weather/nasa_power/power_daily_mh_2015_2025.csv", usecols=["date", "lat", "lon"])
    cells = arch[["lat", "lon"]].drop_duplicates()
    arch_end = pd.to_datetime(arch.date).max().date()
    start, end = min(today - timedelta(days=days), arch_end + timedelta(days=1)), today
    frames, fails = [], 0
    for lat, lon in cells.itertuples(index=False):
        url = (f"https://power.larc.nasa.gov/api/temporal/daily/point?parameters={POWER_VARS}&community=AG&longitude={lon}"
               f"&latitude={lat}&start={start:%Y%m%d}&end={end:%Y%m%d}&format=JSON&time-standard=LST")
        for attempt in range(3):
            try:
                j = safe_get(url, timeout=120).json()
                p = pd.DataFrame(j["properties"]["parameter"]); p.index.name = "date"; p = p.reset_index()
                p["date"] = pd.to_datetime(p.date, format="%Y%m%d")
                p.insert(1, "lat", lat); p.insert(2, "lon", lon); p.insert(3, "elev_m", j["geometry"]["coordinates"][2])
                frames.append(p); break
            except Exception:
                time.sleep(10 * (attempt + 1))
        else:
            fails += 1
        time.sleep(0.5)
    if frames:
        out = pd.concat(frames, ignore_index=True)
        out.to_csv(RAW / "weather/nasa_power/power_daily_mh_recent.csv", index=False)
        last_complete = out.dropna().query("T2M != -999").date.max()
        last_rad = out[out.ALLSKY_SFC_SW_DWN != -999].date.max()
        return dict(cells_ok=len(frames), cells_failed=fails, last_met=str(last_complete.date()), last_radiation=str(last_rad.date()))
    return dict(cells_ok=0, cells_failed=fails)


def freshness():
    out = {}
    for p in ("MOD13Q1", "MOD11A2", "MOD16A2", "MOD16A2GF", "SMAP", "IMERG"):
        d = SERIES_DIR / p
        if d.exists():
            s = pd.read_parquet(d, columns=["date", "status", "valid_frac", "mask"])
            last = s.date.max()
            q = s[(s.date == last) & (s["mask"] == "all")].valid_frac.median()
            out[p] = dict(latest=str(last.date()), status_latest=s[s.date == last].status.iloc[0], median_valid_frac_latest=round(float(q), 3))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-gee", action="store_true"); ap.add_argument("--skip-power", action="store_true")
    ap.add_argument("--skip-forecast", action="store_true")
    a = ap.parse_args(argv)
    today = date.today()
    log = dict(started=datetime.now(timezone.utc).isoformat(timespec="seconds"), today=str(today), steps={})

    def step(name, fn):
        t = time.time()
        try:
            log["steps"][name] = dict(ok=True, result=fn())
        except Exception as e:
            log["steps"][name] = dict(ok=False, error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-1500:])
        log["steps"][name]["seconds"] = round(time.time() - t, 1)
        print(name, "ok" if log["steps"][name]["ok"] else "FAILED", log["steps"][name].get("result", log["steps"][name].get("error")), flush=True)

    if not a.skip_gee:
        for p in GEE_PRODUCTS:
            step(f"gee_{p}", lambda p=p: gee_catch_up(p, today))
        step("imerg_finalise", lambda: imerg_finalise(today))
    if not a.skip_power:
        step("power_recent", lambda: power_recent(today))
    if not a.skip_forecast:
        from geocrop.monitor import forecast_ecmwf
        step("ecmwf_forecast", lambda: (lambda d: dict(run=str(d.run.iloc[0]), days=int(d.date.nunique())))(forecast_ecmwf.build()))
    for p in ("MOD13Q1", "MOD11A2", "MOD16A2", "SMAP", "IMERG"):
        step(f"series_{p}", lambda p=p: dict(new_dates=build_series.build(p, verbose=False)))
    step("weather_power", lambda: dict(rows=len(weather.power())))
    step("indices", lambda: (indices.build_all(), "rebuilt")[1])
    from geocrop.monitor import nowcast as _nc
    step("district_nowcast", lambda: _nc.precompute_district_today(today).stress.value_counts().to_dict())
    from geocrop.predict import infer as _pred
    step("predict_forecast", lambda: _pred.run().groupby("lead_days").dry_risk.value_counts().to_dict().__str__())
    log["freshness"] = freshness()
    log["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log["all_ok"] = all(s["ok"] for s in log["steps"].values())
    f = LOGDIR / f"update_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    f.write_text(json.dumps(log, indent=1, default=str))
    print("log:", f)
    return 0 if log["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
