# Sources for `fao56_crop_params.csv`

Allen, R.G., Pereira, L.S., Raes, D., Smith, M. (1998). *Crop evapotranspiration: guidelines for computing crop water requirements*. FAO Irrigation and Drainage Paper 56, FAO, Rome.

| Table | Gives | Page |
|---|---|---|
| Table 11 | stage lengths | https://www.fao.org/4/x0490e/x0490e0b.htm |
| Table 12 | Kc mid, Kc end, maximum height | https://www.fao.org/4/x0490e/x0490e0b.htm |
| Table 22 | maximum root depth range, depletion fraction p at ETc ≈ 5 mm/day | https://www.fao.org/4/x0490e/x0490e0e.htm |

Extracted 2026-11-13. Every value was transcribed from the printed tables; none was estimated.

## Notes and caveats

* **Kc ini.** The per-crop column of Table 12 is an image on the web page, so the crop-group value (bold group row) is used. FAO-56 says that value "is considered to be representative of the whole group". Where a crop shows its own value in the text (sugar cane, rice), that value is used. FAO-56 also allows Kc ini to be refined from wetting frequency; that refinement is not yet applied.
* **Ranges.** Where FAO gives a range (e.g. Kc end 0.70–0.50), the midpoint is used and the note column says so.
* **Stage lengths.** FAO-56 has no Maharashtra-specific rows. The row closest in region and season was chosen (Central India for wheat, India dry/cool for rabi maize, otherwise tropical, arid or Pakistan rows). These must be replaced with SAU (MPKV, VNMKV, PDKV, DBSKKV) variety data before results are presented as locally calibrated.
* **Excluded from the nowcast.**
  * Rice: FAO defines p for rice relative to saturation; paddy needs a ponded-water balance, not this one.
  * Chick pea: FAO-56 Table 11 has no stage lengths for it.
  * Pigeon pea: not listed in FAO-56 Tables 11, 12 or 22.
* **Adjustments.** p is adjusted daily with the FAO-56 Table 22 footnote: p = p_table + 0.04 (5 − ETc), limited to 0.1–0.8.
