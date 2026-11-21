"""Thin, faithful wrapper around the official FAO AquaCrop 7.3 Python engine.

We never modify the engine. For every simulation we create an isolated run folder:
    <run>/cwd/                      engine working directory (engine resolves files via "../testcase/")
    <run>/testcase/LIST/            <name>.PRO + ListProjects.txt
    <run>/testcase/SIMUL/           CO2 file, output-selection files
    <run>/testcase/DATA/            climate, crop, soil, irrigation, initial-condition files
    <run>/testcase/OUTP/            engine outputs (<name>PROseason.OUT, <name>PROday.OUT)
and run the engine in a separate Python process (the engine keeps module-level global state).
Directories inside the PRO file are RELATIVE to testcase/ (the engine concatenates them).

File formats follow the FAO AquaCrop 7.3 examples shipped in GUI_AC7.3/DATA.
"""
import math
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from geocrop.config import ROOT, SCRATCH

ENGINE_SRC = ROOT / "simulator/aquacrop/engine_patched/src"  # official v7.3 + documented fixes (PATCHES.md)
GUI_DATA = ROOT / "simulator/aquacrop/gui_ac73/GUI_AC7.3/DATA"
GUI_SIMUL = ROOT / "simulator/aquacrop/gui_ac73/GUI_AC7.3/SIMUL"
RUNS = SCRATCH.parent / "aquacrop_runs"
ELAPSED = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]

LAUNCHER = r'''import sys, time
sys.path.insert(0, r"{src}")
from modules.startunit import StartTheProgram
t = time.time(); StartTheProgram(); print("ENGINE_SECONDS", round(time.time() - t, 2))
'''


def day_nr(d: date) -> int:
    """AquaCrop day number (engine's DetermineDayNr: day 1 = 1 Jan 1901)."""
    return math.trunc((d.year - 1901) * 365.25 + ELAPSED[d.month - 1] + d.day + 0.05)


def from_day_nr(n: int) -> date:
    """Inverse of day_nr (search; cheap)."""
    y = 1901 + int((n - 1) / 365.25)
    for yy in (y - 1, y, y + 1):
        base = day_nr(date(yy, 1, 1))
        if 0 <= n - base < 366:
            return date.fromordinal(date(yy, 1, 1).toordinal() + n - base)
    raise ValueError(n)


# ------------------------------------------------------------------ writers
def _series_header(desc, start: date):
    return [desc, "     1  : Daily records (1=daily, 2=10-daily and 3=monthly data)", f"     {start.day}  : First day of record (1, 11 or 21 for 10-day or 1 for months)",  # daily data: the REAL first day
            f"    {start.month}  : First month of record", f"  {start.year}  : First year of record (1901 if not linked to a specific year)", ""]


def write_climate(folder: Path, name: str, weather: pd.DataFrame, desc: str):
    """weather: daily rows with date, tmin, tmax, eto, rain (no gaps). Writes <name>.CLI/.Tnx/.ETo/.PLU."""
    w = weather.sort_values("date").reset_index(drop=True)
    if w[["tmin", "tmax", "eto", "rain"]].isna().any().any():
        raise ValueError("climate has gaps - fill before writing")
    full = pd.date_range(w.date.iloc[0], w.date.iloc[-1], freq="D")
    if len(full) != len(w):
        raise ValueError("climate must be continuous daily")
    start = w.date.iloc[0].date()
    hdr = lambda: _series_header(desc, start)  # noqa: E731
    (folder / f"{name}.Tnx").write_text("\n".join(hdr() + ["  Tmin (C)   TMax (C)", "========================"] +
                                                  [f"{a:10.1f}{b:10.1f}" for a, b in zip(w.tmin, w.tmax)]) + "\n")
    (folder / f"{name}.ETo").write_text("\n".join(hdr() + ["  Average ETo (mm/day)", "======================="] + [f"{v:10.1f}" for v in w.eto]) + "\n")
    (folder / f"{name}.PLU").write_text("\n".join(hdr() + ["  Total Rain (mm)", "======================="] + [f"{v:10.1f}" for v in w.rain]) + "\n")
    (folder / f"{name}.CLI").write_text("\n".join([desc, " 7.3   : AquaCrop Version", f"{name}.Tnx", f"{name}.ETo", f"{name}.PLU", "MaunaLoa.CO2"]) + "\n")


@dataclass
class Horizon:
    thickness_m: float
    sat: float      # vol %
    fc: float       # vol %
    wp: float       # vol %
    ksat: float     # mm/day
    penetrability: int = 100
    gravel: int = 0
    description: str = "horizon"


def capillary_rise_params(sat, fc, wp, ksat):
    """CRa/CRb as in AquaCrop (Raes et al., AquaCrop reference manual ch.3, soil classes by texture):
    class decided from SAT/FC/WP; coefficients from Ksat (mm/day)."""
    # soil class (1 sandy, 2 loamy, 3 sandy clayey, 4 silty clayey) - AquaCrop's NumberSoilClass rules
    if sat <= 55:
        if wp >= 20:
            cls = 3 if (sat >= 49 and fc >= 40) is False else 4
            if fc < 40 or sat < 49:
                cls = 3
        elif fc < 23:
            cls = 1
        else:
            cls = 2
    else:
        cls = 4
    k = max(ksat, 1e-3)
    if cls == 1:
        a, b = -0.3112 - k * 1e-5, -1.4936 + 0.2416 * math.log(k)
    elif cls == 2:
        a, b = -0.4986 + 9e-5 * k, -2.1320 + 0.4778 * math.log(k)
    elif cls == 3:
        a, b = -0.5677 - 4e-5 * k, -3.7189 + 0.5922 * math.log(k)
    else:
        a, b = -0.6366 + 8e-4 * k, -1.9165 + 0.7063 * math.log(k)
    return a, b


def curve_number(ksat_top):
    """AquaCrop default CN from topsoil Ksat (reference manual, Table 3.x)."""
    if ksat_top > 864: return 46
    if ksat_top >= 347: return 61
    if ksat_top >= 36: return 72
    return 77


def rew_mm(fc, wp, ze=0.04):
    """Readily evaporable water (mm) from top layer, AquaCrop default REW = 10*(FC - WP/2)*Ze, bounded 0..15."""
    return int(round(min(15, max(0, 10 * (fc - wp / 2) * ze * 100 / 10))))


def write_soil(folder: Path, name: str, horizons: list[Horizon], desc: str):
    top = horizons[0]
    lines = [desc, "        7.3                 : AquaCrop Version", f"       {curve_number(top.ksat)}                   : CN (Curve Number)",
             f"       {rew_mm(top.fc, top.wp)}                   : Readily evaporable water from top layer (mm)",
             f"        {len(horizons)}                   : number of soil horizons", "       -9                   : variable no longer applicable",
             "  Thickness  Sat   FC    WP     Ksat   Penetrability  Gravel  CRa       CRb           description",
             "  ---(m)-   ----(vol %)-----  (mm/day)      (%)        (%)    -----------------------------------------"]
    for h in horizons:
        a, b = capillary_rise_params(h.sat, h.fc, h.wp, h.ksat)
        lines.append(f"    {h.thickness_m:4.2f}    {h.sat:4.1f}  {h.fc:4.1f}  {h.wp:4.1f}  {h.ksat:7.1f}        {h.penetrability:3d}         {h.gravel:2d}     {a:9.6f} {b:9.6f}           {h.description}")
    (folder / f"{name}.SOL").write_text("\n".join(lines) + "\n")


def write_irrigation_net(folder: Path, name: str, allowable_depletion_raw_pct: int, method: int = 1, wetted_pct: int = 100):
    """Irrigate whenever depletion exceeds the given % of RAW (net irrigation requirement mode)."""
    (folder / f"{name}.IRR").write_text("\n".join([f"Net irrigation: refill when depletion > {allowable_depletion_raw_pct}% of RAW", "   7.3   : AquaCrop Version",
                                                   f"   {method}     : irrigation method (1 sprinkler, 3 drip, 4 furrow, 5 basin, 6 border)",
                                                   f" {wetted_pct}     : Percentage of soil surface wetted by irrigation", "   3     : Determination of Net Irrigation requirement",
                                                   f"  {allowable_depletion_raw_pct}     : Allowable depletion of RAW (%)"]) + "\n")


def write_irrigation_schedule(folder: Path, name: str, events: list[tuple[int, float]], method: int = 1, wetted_pct: int = 100, ecw: float = 0.5):
    """Fixed schedule: events = [(day after sowing, depth mm)]. Day 1 = sowing day."""
    rows = [f"  {d:5d}     {mm:6.0f}          {ecw:.1f}" for d, mm in events]
    (folder / f"{name}.IRR").write_text("\n".join(["Irrigation schedule", "   7.3   : AquaCrop Version",
                                                   f"   {method}     : irrigation method", f" {wetted_pct}     : Percentage of soil surface wetted by irrigation",
                                                   "   1     : Irrigation schedule", "", "   Day    Depth (mm)   ECw (dS/m)",
                                                   "===================================="] + rows) + "\n")


def write_initial_conditions(folder: Path, name: str, depths_m: list[float], water_vol_pct: list[float], desc="initial soil water"):
    # Version >= 4.1 layout (engine LoadInitialConditions): CCini, Bini, Zrini, bund storage, EC of bund water,
    # "at depths" flag, number of depths, 3 header lines, rows of depth / water (vol%) / ECe (dS/m).
    rows = [f"      {d:4.2f}                    {w:5.2f}                 0.00" for d, w in zip(depths_m, water_vol_pct)]
    (folder / f"{name}.SW0").write_text("\n".join([
        desc, "    7.3   : AquaCrop Version",
        "   -9.00  : initial canopy cover (%) - default (reachable without water stress)",
        "    0.000 : biomass (ton/ha) produced before the start of the simulation period",
        "   -9.00  : initial effective rooting depth (m) - default",
        "    0.0   : water layer (mm) stored between soil bunds (if present)",
        "    0.00  : electrical conductivity (dS/m) of water layer stored between soil bunds (if present)",
        "    1     : soil water content specified at particular depths", f"    {len(rows)}     : number of soil depths considered",
        "", "  Soil depth (m)     Soil water content (vol%)     ECe (dS/m)",
        "=============================================================="] + rows) + "\n")


def write_project(path: Path, desc: str, sim_start: date, sim_end: date, crop_start: date, crop_end: date, files: dict):
    """files: keys clim, tnx, eto, plu, co2, cal, cro, irr, man, sol, gwt, sw0, off, obs -> filename (in DATA/, co2 in SIMUL/) or None."""
    def blk(info, key):
        fn = files.get(key)
        d = "SIMUL/" if key == "co2" else "DATA/"
        return [info, fn or "(None)", d if fn else "(None)"]
    L = [desc, "      7.3       : AquaCrop Version", "      1         : Year number of cultivation (Seeding/planting year)",
         f"  {day_nr(sim_start)}         : First day of simulation period - {sim_start:%d %b %Y}",
         f"  {day_nr(sim_end)}         : Last day of simulation period - {sim_end:%d %b %Y}",
         f"  {day_nr(crop_start)}         : First day of cropping period - {crop_start:%d %b %Y}",
         f"  {day_nr(crop_end)}         : Last day of cropping period - {crop_end:%d %b %Y}"]
    for info, key in (("-- 1. Climate (CLI) file", "clim"), ("   1.1 Temperature (Tnx or TMP) file", "tnx"), ("   1.2 Reference ET (ETo) file", "eto"),
                      ("   1.3 Rain (PLU) file", "plu"), ("   1.4 Atmospheric CO2 concentration (CO2) file", "co2"), ("-- 2. Calendar (CAL) file", "cal"),
                      ("-- 3. Crop (CRO) file", "cro"), ("-- 4. Irrigation management (IRR) file", "irr"), ("-- 5. Field management (MAN) file", "man"),
                      ("-- 6. Soil profile (SOL) file", "sol"), ("-- 7. Groundwater table (GWT) file", "gwt"), ("-- 8. Initial conditions (SW0) file", "sw0"),
                      ("-- 9. Off-season conditions (OFF) file", "off"), ("-- 10. Field data (OBS) file", "obs")):
        L += blk(info, key)
    path.write_text("\n".join(L) + "\n")


# ------------------------------------------------------------------ run + parse
@dataclass
class RunResult:
    run_dir: Path
    season: pd.DataFrame
    daily: pd.DataFrame
    seconds: float
    log: str = ""
    meta: dict = field(default_factory=dict)


def new_run_dir() -> Path:
    r = RUNS / uuid.uuid4().hex[:12]
    for sub in ("cwd", "testcase/LIST", "testcase/SIMUL", "testcase/OUTP", "testcase/PARAM", "testcase/DATA"):
        (r / sub).mkdir(parents=True, exist_ok=True)
    shutil.copy(GUI_SIMUL / "MaunaLoa.CO2", r / "testcase/SIMUL/MaunaLoa.CO2")
    (r / "testcase/SIMUL/AggregationResults.SIM").write_text("0 : Time aggregation for intermediate results\n")
    (r / "testcase/SIMUL/DailyResults.SIM").write_text(" 1 : Various parameters of the soil water balance\n 2 : Crop development and production\n"
                                                       " 3 : Soil water content in the soil profile and root zone\n")
    return r


def _read_out(path: Path) -> pd.DataFrame:
    """Parse an AquaCrop .OUT table: header line with names, units line, then whitespace-separated rows."""
    if not path.exists():
        return pd.DataFrame()
    lines = path.read_text(errors="ignore").splitlines()
    # find header: the line containing 'Day' & 'Month' column names
    hi = next((i for i, l in enumerate(lines) if l.strip().startswith(("Day", "RunNr"))), None)
    if hi is None:
        return pd.DataFrame()
    raw = lines[hi].split()
    names, seen = [], {}
    for n in raw:  # daily output repeats some names across sections (Trx, Tr, Z, WC...) -> make unique
        seen[n] = seen.get(n, 0) + 1
        names.append(n if seen[n] == 1 else f"{n}_{seen[n]}")
    rows = []
    for l in lines[hi + 2:]:
        parts = l.split()
        if not parts or not (parts[0].lstrip("-").replace(".", "").isdigit() or parts[0].startswith("Tot(")):
            continue
        rows.append(parts[: len(names)])
    df = pd.DataFrame(rows, columns=names[: len(rows[0])] if rows else names)
    for c in df.columns:
        conv = pd.to_numeric(df[c], errors="coerce")
        if conv.notna().all():
            df[c] = conv
    return df


def run(run_dir: Path, project_name: str, timeout_s: int = 900) -> RunResult:
    (run_dir / "testcase/LIST/ListProjects.txt").write_text(f"{project_name}.PRO\n")
    launcher = run_dir / "launch.py"
    launcher.write_text(LAUNCHER.format(src=str(ENGINE_SRC)))
    p = subprocess.run([sys.executable, str(launcher)], cwd=run_dir / "cwd", capture_output=True, text=True, timeout=timeout_s)
    secs = next((float(l.split()[1]) for l in p.stdout.splitlines() if l.startswith("ENGINE_SECONDS")), float("nan"))
    out = run_dir / "testcase/OUTP"
    season = _read_out(out / f"{project_name}PROseason.OUT")
    daily = _read_out(out / f"{project_name}PROday.OUT")
    log = (p.stdout + p.stderr)[-3000:]
    if p.returncode != 0 or season.empty:
        raise RuntimeError(f"AquaCrop run failed (code {p.returncode}): {log[-1200:]}")
    return RunResult(run_dir, season, daily, secs, log)


def run_batch(run_dir: Path, project_names: list[str], timeout_s: int = 1800) -> dict:
    """Run several projects in ONE engine process (the engine loops over ListProjects.txt).
    Returns {name: RunResult or Exception}. One failing project does not hide the others' results."""
    (run_dir / "testcase/LIST/ListProjects.txt").write_text("".join(f"{n}.PRO\n" for n in project_names))
    launcher = run_dir / "launch.py"
    launcher.write_text(LAUNCHER.format(src=str(ENGINE_SRC)))
    p = subprocess.run([sys.executable, str(launcher)], cwd=run_dir / "cwd", capture_output=True, text=True, timeout=timeout_s)
    secs = next((float(l.split()[1]) for l in p.stdout.splitlines() if l.startswith("ENGINE_SECONDS")), float("nan"))
    log = (p.stdout + p.stderr)[-3000:]
    out, res = run_dir / "testcase/OUTP", {}
    for n in project_names:
        season = _read_out(out / f"{n}PROseason.OUT")
        if season.empty:
            res[n] = RuntimeError(f"no season output (engine code {p.returncode}): {log[-600:]}")
        else:
            res[n] = RunResult(run_dir, season, _read_out(out / f"{n}PROday.OUT"), secs, log)
    return res


def write_field_management(folder: Path, name: str, fertility_stress_pct: int = 0, mulch_pct: int = 0, bund_height_m: float = 0.0):
    """Field management (.MAN). fertility_stress_pct: degree of soil fertility stress (0 = non-limiting). The FAO crop
    files carry a calibrated response to fertility stress (see their 'Considered soil fertility stress' line)."""
    (folder / f"{name}.MAN").write_text("\n".join([
        f"GeoCrop field management: fertility stress {fertility_stress_pct}%", "     7.3       : AquaCrop Version",
        f"   {mulch_pct}         : percentage (%) of ground surface covered by mulches IN growing period",
        "    50         : effect (%) of mulches on reduction of soil evaporation",
        f"   {fertility_stress_pct}         : Degree of soil fertility stress (%) - Effect is crop specific",
        f"     {bund_height_m:.2f}      : height (m) of soil bunds", "     0         : surface runoff NOT affected by field surface practices",
        "     0         : N/A (surface runoff is not affected or completely prevented)",
        "     0         : relative cover of weeds at canopy closure (%)", "     0         : increase of relative cover of weeds in mid-season (+%)",
        "    -0.01      : shape factor of the CC expansion function in a weed infested field"]) + "\n")
