# Crop Advisor: which crop suits this district, season and water situation?

Crop Advisor does **not** use invented agronomic rules. It ranks crops by how each would have performed in this district's **real past seasons**, simulated with the Farm Simulator: FAO AquaCrop 7.3 on district weather, soil and SMAP initial soil water.

## Evidence base (`geocrop/advisor/precompute.py`)

**Seasons and sowing dates:**

| Season | Crops | Sowing dates tested |
|---|---|---|
| Kharif | soybean, cotton, maize, sorghum, sunflower | 15 Jun, 1 Jul, 15 Jul |
| Rabi | wheat, sorghum (rabi jowar), sunflower, maize, potato, tomato | 1 Oct, 15 Oct, 1 Nov, 15 Nov |

1 October was added because rainfed rabi is sown on moisture stored after the monsoon.

**Each combination is run** for:
- **2 water regimes:** rainfed, or irrigated (AquaCrop net irrigation, refilling at 50% of readily available water, furrow method, unlimited supply);
- **every past season 2015–2025** whose whole crop cycle has observed weather;
- **all 36 districts.**

That is 30,731 usable simulated seasons, stored as `data/processed/advisor/runs/d{id}.parquet`. Runs are resumable and incremental: new sowing dates are added to existing files.

**Seasons with no completed crop cycle** (cycle −9):
- **Rainfed:** counted as a failed season (yield 0). The crop didn't establish, which is the conservative reading.
- **Irrigated:** treated as an engine anomaly and excluded. The rate is reported.

## Ranking (`geocrop/advisor/rank.py`)

**Relative yield (RY):** the district's median attainable yield at its best tested sowing date, divided by the crop's reference yield. The reference is the 95th percentile of district medians **under the same water regime**; in FAO land evaluation, rainfed and irrigated farming are different land-utilisation types.

**Suitability classes:** following the FAO (1976) framework with the commonly used yield thresholds (Sys et al. 1993).

| Class | Relative yield |
|---|---|
| S1 | ≥ 80% |
| S2 | 40–80% |
| S3 | 20–40% |
| N | < 20% |

**Order:** crops are sorted by FAO class first. Within a class they are sorted by **bad-year reliability**: the 10th-percentile yield divided by the reference.
* Simulated differences between districts are small, so in kharif almost every crop is S1 in almost every district, and the median alone barely separates crops.
* What does differ, and what matters most to a farmer, is how bad the bad years are. For example, Solapur's bad-year rainfed kharif yield is 0 for every crop.

**Also shown for each crop:**
- typical and bad-year (10th percentile) yield;
- share of poor seasons (below half the district median);
- irrigation needed;
- yield at every tested sowing date;
- every past season;
- for rainfed crops, the yield as a share of the irrigated potential, as an absolute check;
- the official **NIPHM IPM package** (PDF, served from `data/raw/plant_health/ipm_references/ipm`).

**Honesty checks shown on the crop card:**
- **Not ranked rain-only:** potato and tomato in rabi, which are irrigated crops in practice. The page says so.
- **Crop-file notes:**
  - *Potato* (Peru file) matures in about 60 days here, against about 90–110 for local varieties, so its water need is underestimated.
  - *Sorghum* is calibrated on a Texas hybrid and *maize* on Californian conditions, so their attainable yields are well above local ones.
- **Season length check:** simulated season length is compared with FAO-56 Table 11 (`data/reference/fao56_crop_params.csv`) and flagged if outside 70–140%.
- **Edge of the sowing window:** flagged when the best date is the first or last one tested.
- **This season so far:** the latest SMAP root-zone percentile and the Predict 16/32-day dry-soil risk.

## What the full run shows (2026-11-21)

**Engine anomalies:** 0.5% of irrigated seasons.

**Classes:**
* **Kharif:** nearly every crop is S1 everywhere, both rainfed and irrigated; the reliability order does the work.
* **Rabi rainfed:** sorghum is mostly S2 and wheat is split between S1 and S2. All rain-only rabi crops reach well below their irrigated potential, and the page shows that share.

**Sowing dates:**
* **Kharif:** the best date is the latest tested (15 Jul) in 170 of 180 crop–district cases. The model favours sowing after the monsoon is established. Later dates were not simulated, and the card flags it.
* **Rabi rainfed:** the best date is 1 Oct (the earliest) in 143 of 144 cases, in line with sowing on stored moisture as early as possible.

**Known mismatches with local practice:**
* **Vidarbha cotton:** the cotton belt ranks cotton low. The crop file is a Spanish variety, not a Bt hybrid; this is flagged on the card.
* **Rabi rainfed maize** often ranks first. That comes from the high-yield Californian maize file.
* **Konkan:** rice-based and waterlogged farming isn't represented. All Konkan districts carry a warning; Mumbai City and Mumbai Suburban are also flagged as urban.

## API and page
- `GET /advisor/options`
- `GET /advisor/district/{id}?season=kharif|rabi&water=rainfed|irrigated`
- `GET /advisor/ipm/{crop}` (PDF)
- Page: `frontend/src/pages/AdvisorPage.tsx` at `/crop-advisor`. It defaults to the farm profile's district and water source, and to the current season.

## Limits
- **Attainable yields:** no pests, ample nutrients. Use them to compare crops, not as yield promises.
- **Uncalibrated crop files:** they come from outside Maharashtra and haven't been calibrated here (see `docs/SIMULATOR.md`). District-average soil and weather.
- **Only 8 crops:** pulses (tur, gram, moong), onion, sugarcane, rice, cotton varieties and fruit crops are missing, and these are major in Maharashtra.
- **No economics:** prices, costs, labour, markets and local practice aren't included. The page tells farmers to discuss choices with their KVK.

## Run

```bash
.venv/Scripts/python -m geocrop.advisor.precompute   # ~3 min per district (one process, 10 engine processes); incremental
```
