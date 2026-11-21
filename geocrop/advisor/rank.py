"""Crop Advisor ranking from simulated past seasons (no invented agronomic rules).

For a district, season and water situation, every candidate crop is scored on:
  * relative yield RY = district median attainable yield (best tested sowing date) / that crop's reference yield,
    where the reference is the 95th percentile, across all 36 districts, of the median yield at the best sowing date
    under the SAME water regime (rainfed vs irrigated are separate land-utilisation types in the FAO framework).
    -> classes after the FAO (1976) land-evaluation framework with the commonly used yield thresholds
       (Sys, Van Ranst & Debaveye 1993): S1 >= 80 %, S2 40-80 %, S3 20-40 %, N < 20 %.
  * risk: share of past seasons with yield below half of the district's median for that crop (instability),
    and the bad-year (10th percentile) yield;
  * irrigation water needed (irrigated case) and sowing-date sensitivity.
Only seasons whose whole crop cycle had observed weather are used. Rainfed seasons with no completed crop cycle count
as failed (yield 0); irrigated ones are engine anomalies and are excluded (rate reported by coverage()).
"""
from functools import lru_cache

import numpy as np
import pandas as pd

from geocrop.advisor.precompute import OUT, SEASONS
from geocrop.config import RAW

T_HA_TO_Q_ACRE = 10 / 2.47105
CLASSES = [(0.8, "S1", "Highly suitable", "अतिशय योग्य"), (0.4, "S2", "Moderately suitable", "मध्यम योग्य"),
           (0.2, "S3", "Marginally suitable", "किरकोळ योग्य"), (0.0, "N", "Not suitable", "योग्य नाही")]
CROP_MR = {"soybean": "सोयाबीन", "cotton": "कापूस", "maize": "मका", "sorghum": "ज्वारी", "sunflower": "सूर्यफूल",
           "wheat": "गहू", "potato": "बटाटा", "tomato": "टोमॅटो"}
IPM_DIR = RAW / "plant_health/ipm_references/ipm"
IPM_FILE = {"soybean": "NIPHM_IPM_Soyabean.pdf", "cotton": "NIPHM_IPM_Cotton.pdf", "maize": "NIPHM_IPM_Maize.pdf",
            "sorghum": "NIPHM_IPM_Sorghum.pdf", "sunflower": "NIPHM_IPM_Sunflower.pdf", "wheat": "NIPHM_IPM_Wheat.pdf",
            "potato": "NIPHM_IPM_Potato.pdf", "tomato": "NIPHM_IPM_Tomato.pdf"}
MIN_SEASONS = 5
# Vegetables are grown with irrigation in rabi; a rain-only ranking of them would not describe a real farming system.
RAINFED_EXCLUDED = {("rabi", "potato"): "grown with irrigation in rabi", ("rabi", "tomato"): "grown with irrigation in rabi"}
# Known limits of the FAO crop files used (shown on the crop card)
CROP_NOTES = {
    "potato": ("The FAO potato file (calibrated in Peru) matures in about 60 days in Maharashtra's warm winter, much faster than local "
               "varieties (about 90-110 days), so water need is underestimated.",
               "FAO बटाटा फाइल येथे ~६० दिवसांत तयार होते, स्थानिक वाणांपेक्षा खूप लवकर; पाण्याची गरज कमी दिसते."),
    "sorghum": ("Crop file calibrated for a US grain hybrid (Texas): attainable yields are far above local jowar varieties; compare classes, not tonnes.",
                "पीक फाइल अमेरिकन संकरित वाणाची: उत्पादन स्थानिक ज्वारीपेक्षा खूप जास्त; वर्गांची तुलना करा."),
    "cotton": ("FAO cotton file calibrated in Cordoba (Spain), not on Bt hybrids grown here; Vidarbha's cotton belt may rank cotton "
               "lower than local experience suggests.",
               "कापूस फाइल स्पेनची, येथील बीटी संकरित वाणांवर नाही; विदर्भात कापसाची क्रमवारी कमी दिसू शकते."),
    "maize": ("Crop file calibrated in California: attainable yields are well above typical Maharashtra yields.",
              "पीक फाइल कॅलिफोर्नियाची: उत्पादन महाराष्ट्रातील सरासरीपेक्षा जास्त."),
}
FAO56_KEY = {("kharif", "maize"): "maize_kharif", ("rabi", "maize"): "maize_rabi", "cotton": "cotton", "soybean": "soybean",
             "sorghum": "sorghum", "wheat": "wheat", "tomato": "tomato"}


@lru_cache(maxsize=1)
def fao56_lengths():
    from geocrop.config import REFERENCE
    t = pd.read_csv(REFERENCE / "fao56_crop_params.csv")
    return dict(zip(t.crop, t.l_total))


def phenology_check(season, crop, median_cycle):
    """Simulated season length vs the FAO-56 Table 11 total length for the crop (flag if < 70 % or > 140 %)."""
    key = FAO56_KEY.get((season, crop), FAO56_KEY.get(crop))
    ref = fao56_lengths().get(key) if key else None
    if not ref or not median_cycle:
        return None
    ratio = median_cycle / ref
    return dict(simulated_days=int(median_cycle), fao56_days=int(ref), ratio=round(ratio, 2), plausible=bool(0.7 <= ratio <= 1.4))


@lru_cache(maxsize=1)
def runs() -> pd.DataFrame:
    files = sorted(OUT.glob("d*.parquet"))
    if not files:
        raise FileNotFoundError("no advisor simulations yet (run geocrop.advisor.precompute)")
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df = df[df.complete_observed_weather].copy()
    # A season with no completed crop cycle: under RAINFED conditions this is treated as a failed season (the crop did
    # not establish or died of drought -> yield 0, the conservative choice); under IRRIGATION it is an engine anomaly
    # and excluded (an irrigated crop dying in the monsoon is not a credible outcome).
    df.loc[df.engine_failed & (df.water == "rainfed"), "yield_t_ha"] = 0.0
    return df[~(df.engine_failed & (df.water == "irrigated"))]


@lru_cache(maxsize=1)
def engine_failure_rate() -> float:
    df = pd.concat([pd.read_parquet(f, columns=["engine_failed", "complete_observed_weather", "water"]) for f in sorted(OUT.glob("d*.parquet"))])
    df = df[df.complete_observed_weather & (df.water == "irrigated")]
    return round(float(df.engine_failed.mean()), 4)  # irrigated anomalies only (rainfed ones count as failures)


def _stats(df):
    g = df.groupby(["district_id", "season", "crop", "water", "sow_mmdd"])
    s = g.yield_t_ha.agg(n="size", median="median", p10=lambda x: np.percentile(x, 10), mean="mean").reset_index()
    s["irrigation_mm"] = g.irrigation_mm.median().values
    s["rain_mm"] = g.rain_mm.median().values
    # instability: share of seasons below half the median of that same group
    s["poor_season_share"] = g.yield_t_ha.apply(lambda x: float((x < 0.5 * x.median()).mean()) if x.median() > 0 else 1.0).values
    return s[s.n >= MIN_SEASONS]


@lru_cache(maxsize=1)
def table() -> pd.DataFrame:
    """One row per district x season x crop x water at its best sowing date, with RY, class and risk."""
    s = _stats(runs())
    best = s.loc[s.groupby(["district_id", "season", "crop", "water"])["median"].idxmax()].copy()
    # FAO land evaluation treats rainfed and irrigated farming as different land-utilisation types, so each crop is
    # compared with the best districts UNDER THE SAME WATER REGIME (95th percentile of district medians)
    ref = best.groupby(["season", "crop", "water"])["median"].quantile(0.95).rename("reference_t_ha").reset_index()
    best = best.merge(ref, on=["season", "crop", "water"], how="left")
    best["relative_yield"] = (best["median"] / best.reference_t_ha).clip(0, 1)
    best["class"] = best.relative_yield.map(lambda r: next(c[1] for c in CLASSES if r >= c[0]))
    # sowing-date sensitivity: median at every tested date, relative to the best
    sens = s.pivot_table(index=["district_id", "season", "crop", "water"], columns="sow_mmdd", values="median")
    best = best.merge(sens.apply(lambda r: {k: round(float(v), 2) for k, v in r.dropna().items()}, axis=1).rename("median_by_sow_date").reset_index(),
                      on=["district_id", "season", "crop", "water"])
    return best.rename(columns={"sow_mmdd": "best_sow_mmdd", "median": "median_t_ha", "p10": "p10_t_ha", "n": "n_seasons"})


def recommend(district_id: int, season: str, water: str):
    if season not in SEASONS or water not in ("rainfed", "irrigated"):
        raise ValueError("season must be kharif|rabi and water rainfed|irrigated")
    t = table()
    d = t[(t.district_id == district_id) & (t.season == season) & (t.water == water)].copy()
    if d.empty:
        return []
    excluded = []
    if water == "rainfed":
        excluded = [dict(crop=c, reason=why) for (se, c), why in RAINFED_EXCLUDED.items() if se == season and c in set(d.crop)]
        d = d[~d.crop.isin([e["crop"] for e in excluded])]
    # Order: FAO class first; within a class, by bad-year reliability (10th-percentile yield / reference), because
    # simulated differences between districts are small and the median alone barely separates crops.
    d["class_rank"] = d["class"].map({c[1]: i for i, c in enumerate(CLASSES)})
    d["bad_year_relative"] = (d.p10_t_ha / d.reference_t_ha).clip(0, 1)
    d = d.sort_values(["class_rank", "bad_year_relative", "poor_season_share"], ascending=[True, False, True])
    rf = t[(t.district_id == district_id) & (t.season == season) & (t.water == "rainfed")].set_index("crop")
    yearly = runs()
    out = []
    for rank, r in enumerate(d.itertuples(), 1):
        cl = next(c for c in CLASSES if c[1] == r[d.columns.get_loc("class") + 1])
        yrs = yearly[(yearly.district_id == district_id) & (yearly.season == season) & (yearly.crop == r.crop)
                     & (yearly.water == water) & (yearly.sow_mmdd == r.best_sow_mmdd)].sort_values("season_year")
        item = dict(rank=rank, crop=r.crop, crop_mr=CROP_MR[r.crop], yield_type=yrs.yield_type.iloc[0] if len(yrs) else None,
                    suitability_class=cl[1], suitability=cl[2], suitability_mr=cl[3], relative_yield=round(float(r.relative_yield), 3),
                    best_sow=r.best_sow_mmdd, median_by_sow_date=r.median_by_sow_date,
                    median_t_ha=round(float(r.median_t_ha), 2), p10_t_ha=round(float(r.p10_t_ha), 2),
                    median_q_acre=round(float(r.median_t_ha) * T_HA_TO_Q_ACRE, 1), p10_q_acre=round(float(r.p10_t_ha) * T_HA_TO_Q_ACRE, 1),
                    reference_t_ha=round(float(r.reference_t_ha), 2), poor_season_share=round(float(r.poor_season_share), 2),
                    bad_year_relative=round(float(r.bad_year_relative), 3),
                    irrigation_mm=round(float(r.irrigation_mm)), rain_mm=round(float(r.rain_mm)), n_seasons=int(r.n_seasons),
                    yearly=[dict(year=int(y.season_year), yield_t_ha=float(y.yield_t_ha), irrigation_mm=float(y.irrigation_mm), failed=bool(y.engine_failed)) for y in yrs.itertuples()],
                    ipm_package=IPM_FILE.get(r.crop) if (IPM_DIR / IPM_FILE.get(r.crop, "-")).exists() else None)
        sows_tested = [f"{m:02d}-{dd:02d}" for m, dd in SEASONS[season]["sow"]]
        item["best_is_latest_tested"] = r.best_sow_mmdd == sows_tested[-1]
        item["best_is_earliest_tested"] = r.best_sow_mmdd == sows_tested[0]
        item["phenology"] = phenology_check(season, r.crop, float(yrs[yrs.cycle_days > 0].cycle_days.median()) if len(yrs) else None)
        if r.crop in CROP_NOTES:
            item["model_note"], item["model_note_mr"] = CROP_NOTES[r.crop]
        if water == "rainfed":  # absolute check: rainfed yield as a share of the crop's IRRIGATED reference
            ir = t[(t.season == season) & (t.crop == r.crop) & (t.water == "irrigated")]
            if len(ir):
                item["share_of_irrigated_potential"] = round(float(r.median_t_ha / ir.reference_t_ha.iloc[0]), 3)
        if water == "irrigated" and r.crop in rf.index:  # how much irrigation adds over rainfed
            item["rainfed_median_t_ha"] = round(float(rf.loc[r.crop, "median_t_ha"]), 2)
        out.append(item)
    return out, excluded


# Districts where the simulated crops do not represent local farming (shown as a warning)
REGION_WARNINGS = {
    "Konkan": ("Konkan farming is rice-based under a very heavy monsoon (often over 2,500 mm). Rice is not simulated and AquaCrop "
               "does not represent waterlogging, so these rankings are not a good guide here.",
               "कोकणातील शेती भातावर आधारित; भात व पाणी साचणे सिम्युलेट केलेले नाही, त्यामुळे ही क्रमवारी येथे विश्वासार्ह नाही."),
}
URBAN = {18: ("Mumbai City is almost entirely urban; results are shown for completeness only.", "मुंबई शहर जवळजवळ पूर्ण शहरी आहे."),
         19: ("Mumbai Suburban is almost entirely urban; results are shown for completeness only.", "मुंबई उपनगर जवळजवळ पूर्ण शहरी आहे.")}


def warnings_for(district_id: int):
    from geocrop.common.districts import district_table
    from geocrop.config import REFERENCE
    name = district_table().set_index("district_id").loc[district_id, "district"]
    reg = pd.read_csv(REFERENCE / "regions.csv").set_index("district").region
    region = reg.get(name)
    out = [dict(en=URBAN[district_id][0], mr=URBAN[district_id][1])] if district_id in URBAN else []
    if region in REGION_WARNINGS:
        out.append(dict(en=REGION_WARNINGS[region][0], mr=REGION_WARNINGS[region][1]))
    return out


def coverage():
    t = table()
    return dict(districts=int(t.district_id.nunique()), seasons_simulated=int(len(runs())), engine_failure_rate=engine_failure_rate(),
                years=f"{int(runs().season_year.min())}-{int(runs().season_year.max())}")
