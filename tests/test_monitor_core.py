"""Unit tests for the scientific core (synthetic inputs; no network, no large data)."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from geocrop.common.eto import extraterrestrial_radiation, hargreaves, penman_monteith
from geocrop.common.zonal import zonal_masks
from geocrop.monitor import soilwater
from geocrop.monitor.indices import _spi
from geocrop.monitor.products import decode_mod11a2, decode_mod13q1, decode_mod16a2gf


# ---------- reference ET (FAO-56 worked examples)
def test_ra_fao56_example8():
    # FAO-56 Example 8: 20 deg S, 3 Sept (DOY 246) -> Ra = 32.2 MJ m-2 day-1
    assert extraterrestrial_radiation(-20, 246) == pytest.approx(32.2, abs=0.2)


def test_penman_monteith_fao56_example18():
    # Uccle 6 July: ETo = 3.9 mm/day (FAO uses RHmax/RHmin; RHmean variant gives ~3.8)
    assert penman_monteith(21.5, 12.3, 73.5, 2.078, 22.07, 50.8, 187, 100) == pytest.approx(3.9, abs=0.2)


def test_hargreaves_positive_and_bounded():
    v = hargreaves(np.array([35.0, 25.0]), np.array([20.0, 25.0]), 19.0, 120)
    assert v[0] > 4 and v[1] == 0


# ---------- zonal statistics equal pandas
def test_zonal_matches_pandas():
    rng = np.random.default_rng(1)
    lab = rng.integers(0, 37, (200, 300)).astype("int16")
    v = rng.normal(size=lab.shape).astype("float32"); v[rng.random(v.shape) < 0.3] = np.nan
    crop = rng.random(v.shape) < 0.4
    z = zonal_masks(v, lab, {"all": None, "crop": crop})
    for name, mm in (("all", lab > 0), ("crop", (lab > 0) & crop)):
        m = mm & ~np.isnan(v)
        g = pd.Series(v[m].astype("float64")).groupby(lab[m])
        zz = z[z["mask"] == name].set_index("district_id")
        np.testing.assert_allclose(zz["median"].values, g.median().values, atol=1e-12)
        np.testing.assert_allclose(zz["p90"].values, g.quantile(0.9).values, atol=1e-12)
        assert (zz.n_total.values == np.bincount(lab[mm], minlength=37)[1:]).all()


# ---------- QA decoding never turns invalid data into numbers
class FakeSrc:
    def __init__(self, bands, nodata):
        self.descriptions = tuple(bands); self._b = bands; self.nodata = nodata

    def read(self, i):
        return list(self._b.values())[i - 1]


def test_mod13q1_cloudy_masked():
    ndvi = np.array([[5000, 5000, -32768]], "int16")
    qa = np.array([[0, 3, -32768]], "int16")
    src = FakeSrc({"NDVI": ndvi, "EVI": ndvi, "SummaryQA": qa, "DayOfYear": qa}, -32768)
    out = decode_mod13q1(src, date(2020, 1, 1))["ndvi"]
    assert out[0, 0] == pytest.approx(0.5) and np.isnan(out[0, 1]) and np.isnan(out[0, 2])


def test_mod11a2_qc_bits():
    lst = np.array([[15000, 15000, 15000, 0]], "uint16")
    qc = np.array([[0b00000000, 0b00000010, 0b11000001, 0]], "uint16")  # good | not produced | error>3K | lst=0
    src = FakeSrc({"LST_Day_1km": lst, "LST_Night_1km": lst, "QC_Day": qc, "QC_Night": qc}, 65535)
    out = decode_mod11a2(src, date(2020, 1, 1))["lst_day"]
    assert out[0, 0] == pytest.approx(15000 * 0.02 - 273.15)
    assert np.isnan(out[0, 1:]).all()


def test_mod16_fill_and_last_composite_length():
    et = np.array([[80, 32761]], "int16")
    src = FakeSrc({"ET": et, "PET": et, "ET_QC": et}, -32768)
    out = decode_mod16a2gf(src, date(2021, 12, 27))  # DOY 361 -> 5-day composite in a non-leap year
    assert out["et"][0, 0] == pytest.approx(8.0 / 5) and np.isnan(out["et"][0, 1])


# ---------- soil water
def test_taw_integration_uniform_profile():
    prof = {"theta_fc": np.full(7, 0.40), "theta_wp": np.full(7, 0.25)}
    assert soilwater.taw_mm(prof, 1.0) == pytest.approx(150.0)
    assert soilwater.taw_mm(prof, 0.5) == pytest.approx(75.0)


def test_saxton_rawls_clay_order():
    wp_c, fc_c, sat_c = soilwater.saxton_rawls(0.2, 0.5, 2.5)
    wp_s, fc_s, sat_s = soilwater.saxton_rawls(0.85, 0.05, 1.0)
    assert fc_c > wp_c > wp_s and fc_c - wp_c > 0.08 and sat_c > fc_c and sat_s > fc_s > wp_s


# ---------- SPI
def test_spi_standard_normal_on_gamma_data():
    rng = np.random.default_rng(3)
    x = pd.Series(rng.gamma(2.0, 30.0, 300))
    s = _spi(x, np.ones(300, bool))
    assert abs(np.nanmean(s)) < 0.1 and abs(np.nanstd(s) - 1) < 0.1
