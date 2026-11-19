"""Farm Simulator tests: AquaCrop wrapper formats and end-to-end behaviour on real district data."""
import shutil
from datetime import date, timedelta

import pytest

from geocrop.simulator import aquacrop as ac
from geocrop.simulator import scenario as sc


def test_day_nr_matches_engine_formula():
    # engine: DetermineDayNr = trunc((Y-1901)*365.25 + ElapsedDays[M-1] + D + 0.05)
    assert ac.day_nr(date(1901, 1, 1)) == 1
    assert ac.day_nr(date(1986, 5, 1)) == 31167
    # AquaCrop's formula has no 29 Feb (ElapsedDays is a non-leap table); consecutive days still increase by 1 elsewhere
    assert ac.day_nr(date(2025, 6, 26)) - ac.day_nr(date(2025, 6, 25)) == 1
    assert ac.from_day_nr(ac.day_nr(date(2025, 6, 25))) == date(2025, 6, 25)


def test_ksat_reasonable_for_clay_and_sand():
    clay = sc.saxton_rawls_ksat_mm_day(0.25, 0.38, 0.47)
    sand = sc.saxton_rawls_ksat_mm_day(0.05, 0.10, 0.43)
    assert 5 < clay < 200 and sand > clay


def test_smoke_engine_with_fao_example():
    r = ac.new_run_dir(); D = r / "testcase/DATA"
    for f in ["Cordoba.CLI", "Cordoba.Tnx", "Cordoba.ETo", "Cordoba.PLU", "Maize.CRO", "ClayLoam.SOL"]:
        shutil.copy(ac.GUI_DATA / f, D / f)
    sow = date(1986, 5, 1); end = sow + timedelta(days=131)
    files = dict(clim="Cordoba.CLI", tnx="Cordoba.Tnx", eto="Cordoba.ETo", plu="Cordoba.PLU", co2="MaunaLoa.CO2", cro="Maize.CRO", sol="ClayLoam.SOL")
    ac.write_irrigation_net(D, "Net", 50)
    ac.write_project(r / "testcase/LIST/Rf.PRO", "rainfed", sow, end, sow, end, files)
    ac.write_project(r / "testcase/LIST/Ir.PRO", "irrigated", sow, end, sow, end, files | {"irr": "Net.IRR"})
    res = ac.run_batch(r, ["Rf", "Ir"])
    rf, ir = res["Rf"].season.iloc[0], res["Ir"].season.iloc[0]
    assert rf["Irri"] == 0 and ir["Irri"] > 300               # dry Cordoba summer needs irrigation
    assert ir["Y(dry)"] > 3 * rf["Y(dry)"] > 0                 # and it pays off
    shutil.rmtree(r, ignore_errors=True)


@pytest.mark.parametrize("crop", ["soybean", "wheat"])
def test_irrigation_never_reduces_yield(crop):
    sow = (6, 25) if crop == "soybean" else (11, 10)
    years = [2016, 2018, 2019]
    rf = sc.simulate_years(17, crop, *sow, sc.Irrigation("rainfed"), years=years)
    ir = sc.simulate_years(17, crop, *sow, sc.Irrigation("net", 50), years=years)
    a = {r["year"]: r for r in rf["runs"]}; b = {r["year"]: r for r in ir["runs"]}
    assert set(a) == set(b) == set(years), (rf["errors"] + ir["errors"])[:1]
    for y in years:
        assert b[y]["yield_t_ha"] >= a[y]["yield_t_ha"] - 0.05
        assert a[y]["irrigation_mm"] == 0
    assert all(r["complete_observed_weather"] for r in rf["runs"])


def test_drought_year_is_worse_rainfed():
    out = sc.simulate_years(17, "soybean", 6, 25, sc.Irrigation("rainfed"), years=[2015, 2016])
    y = {r["year"]: r["yield_t_ha"] for r in out["runs"]}
    assert y[2015] < 0.5 * y[2016]  # 2015 Marathwada drought vs wet 2016
