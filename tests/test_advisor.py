"""Crop Advisor: ranking logic and API on the precomputed AquaCrop seasons."""
import pytest

from geocrop.advisor.precompute import OUT, SEASONS

pytestmark = pytest.mark.skipif(not any(OUT.glob("d*.parquet")), reason="run geocrop.advisor.precompute first")


def _a_district():
    return int(sorted(OUT.glob("d*.parquet"))[0].stem[1:])


def test_only_complete_observed_seasons_are_used():
    from geocrop.advisor import rank
    assert rank.runs().complete_observed_weather.all()


def test_recommendations_are_ranked_and_classed():
    from geocrop.advisor import rank
    did = _a_district()
    for season in SEASONS:
        for water in ("rainfed", "irrigated"):
            recs, _ = rank.recommend(did, season, water)
            assert recs, (season, water)
            assert {r["crop"] for r in recs} <= set(SEASONS[season]["crops"])
            order = [(next(i for i, c in enumerate(rank.CLASSES) if c[1] == r["suitability_class"]), -r["bad_year_relative"]) for r in recs]
            assert order == sorted(order) and all(0 <= r["relative_yield"] <= 1 for r in recs)
            for r in recs:
                lo = next(c[0] for c in rank.CLASSES if c[1] == r["suitability_class"])
                assert r["relative_yield"] >= lo
                assert r["p10_t_ha"] <= r["median_t_ha"] + 1e-9 and r["n_seasons"] >= rank.MIN_SEASONS
                assert r["best_sow"] in r["median_by_sow_date"]
                if water == "rainfed":
                    assert r["irrigation_mm"] == 0


def test_irrigation_never_hurts_median_yield():
    from geocrop.advisor import rank
    did = _a_district()
    for season in SEASONS:
        for r in rank.recommend(did, season, "irrigated")[0]:
            if "rainfed_median_t_ha" in r:
                assert r["median_t_ha"] >= r["rainfed_median_t_ha"] - 0.05 * max(r["median_t_ha"], 1)


def test_advisor_api():
    from fastapi.testclient import TestClient
    from geocrop.api.main import app
    c = TestClient(app)
    did = _a_district()
    r = c.get(f"/advisor/district/{did}", params={"season": "rabi", "water": "irrigated"}).json()
    assert r["recommendations"] and "ATTAINABLE" in r["value_type"].upper()
    assert c.get(f"/advisor/district/{did}", params={"season": "summer"}).status_code == 422
    assert c.get("/advisor/district/999").status_code == 404
    pdf = c.get("/advisor/ipm/wheat")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content[:4] == b"%PDF"
    assert c.get("/advisor/ipm/banana").status_code == 404


def test_rabi_vegetables_not_ranked_rainfed_and_notes_present():
    from geocrop.advisor import rank
    recs, excluded = rank.recommend(_a_district(), "rabi", "rainfed")
    assert not {"potato", "tomato"} & {r["crop"] for r in recs}
    assert {e["crop"] for e in excluded} == {"potato", "tomato"}
    irr, _ = rank.recommend(_a_district(), "rabi", "irrigated")
    pot = next(r for r in irr if r["crop"] == "potato")
    assert "model_note" in pot
    wheat = next(r for r in irr if r["crop"] == "wheat")
    assert wheat["phenology"]["fao56_days"] == 120


def test_konkan_and_urban_warnings():
    from geocrop.advisor import rank
    assert len(rank.warnings_for(18)) == 2          # Mumbai City: urban + Konkan
    assert len(rank.warnings_for(31)) == 1          # Sindhudurg: Konkan
    assert rank.warnings_for(1) == []               # Ahilyanagar
