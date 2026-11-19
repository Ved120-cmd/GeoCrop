"""Write models/water_stress/model_card.md from metrics.json (so the card always matches the deployed models)."""
import json

from geocrop.config import ROOT

M = ROOT / "models/water_stress"


def fmt_reg(r):
    rows = ["| Method | MAE (pct points) | RMSE | Skill vs persistence |", "|---|---|---|---|"]
    for k, v in r.items():
        rows.append(f"| {k} | {v['mae']} | {v['rmse']} | {v.get('skill_vs_persistence', '—')} |")
    return "\n".join(rows)


def fmt_cls(r):
    rows = ["| Method | Brier | Brier skill vs climatology | AUC | Precision | Recall |", "|---|---|---|---|---|---|"]
    for k, v in r.items():
        rows.append(f"| {k} | {v['brier']} | {v['brier_skill_vs_climatology']} | {v['auc']} | {v['precision']} | {v['recall']} |")
    return "\n".join(rows)


def main():
    m = json.loads((M / "metrics.json").read_text())
    meta = m["meta"]
    parts = [
        "# Model card: GeoCrop water-stress forecasts (16 and 32 days)", "",
        f"*Generated from `metrics.json`; trained {meta['trained_at']}; training-data hash `{meta['training_data_hash']}`.*", "",
        "## What it predicts",
        f"* **Target (proxy):** {meta['target']}.",
        f"* **Nature:** {meta['target_type']}.",
        f"* **Dry:** percentile ≤ {meta['dry_threshold_pct']}. Outputs are the median, the 10–90% range, and the probability of dry conditions.",
        "* **Unit:** district (36 districts of Maharashtra). These are not field-level forecasts.", "",
        "## Inputs and leakage control",
        f"* {meta['no_future_weather']}",
        "* **Publication delays (days) applied at every issue date:** " + ", ".join(f"{k} {v}" for k, v in meta["leakage_rules"].items()) + ".",
        "* **Climatology known in advance:** normal rain for the coming window and the time of year. Static inputs: district soil water capacity and region.",
        "* **Time split:** train 2015–2021, validation 2022–2023 (model choice and early stopping), test 2024–2026, used once. The deployed models were trained on 2015–2023 and are exactly the ones evaluated.", "",
        "## Models",
        "* **LightGBM point forecast:** the formulation was chosen on validation years only (L2, L1, or L1 on change-from-today).",
        "* **Range and dry risk:** LightGBM quantile models (p10, p90) and a LightGBM dry classifier.",
        "* **XGBoost:** the same formulation, kept as a required baseline. Explanations are TreeSHAP from LightGBM's native `pred_contrib`.",
        f"* **Library versions:** {meta['versions']}.", "",
    ]
    for L in (16, 32):
        r = m[f"lead{L}"]
        parts += [f"## {L}-day forecast: held-out test results (2024–2026, n = {r['n']['test']})",
                  f"Chosen on validation: **{r['model_selection_on_validation']['chosen']}** (validation MAE {r['model_selection_on_validation']['val_mae']}).", "",
                  "### Where will the percentile be? (point forecast)", fmt_reg(r["test_regression"]), "",
                  f"**10–90% range:** coverage {r['test_interval_10_90']['coverage']} (nominal 0.80), mean width {r['test_interval_10_90']['mean_width']} percentile points.", "",
                  "### Will it be dry? (≤ 20th percentile)", fmt_cls(r["test_dry_classification"]), "",
                  "### By season (LightGBM vs persistence MAE)",
                  "\n".join(f"* {k}: {v['lightgbm']['mae']} vs {v['persistence']['mae']} (n = {v['n']})" for k, v in r["test_by_season"].items()), "",
                  "### By year (LightGBM vs persistence MAE)",
                  "\n".join(f"* {k}: {v['lightgbm_mae']} vs {v['persistence_mae']} (n = {v['n']})" for k, v in r["test_by_year"].items()), "",
                  "### Most influential inputs (mean |SHAP| on the test years)",
                  ", ".join(f"{k} ({v})" for k, v in list(r["shap_mean_abs_test"].items())[:8]), ""]
    parts += ["## Honest assessment",
              "* **Dry-risk probability is the useful product.** It beats both persistence and climatology clearly at 16 days, and less so at 32 days.",
              "* **Point forecasts are only slightly better than assuming no change.** At 32 days, simple damped persistence is competitive. In the persistent 2026 drought the models expected some recovery that did not happen, and were worse than persistence.",
              "* **Skill is limited without forecasts.** No weather forecasts are used, so rain in the coming weeks cannot be anticipated. ECMWF reforecasts would be needed to add forecast weather without leakage.",
              "* **The target is a proxy.** SMAP soil moisture is a model-assimilated satellite product at about 9 km. It is not measured crop stress.",
              "* **Effective sample size is smaller than the row count.** Issue dates every 3 days are autocorrelated, and neighbouring districts are spatially correlated.", "",
              "## Intended use",
              "Early warning of dry soil conditions at district level, to prompt checking fields and planning irrigation. It is not a yield forecast, and it is not for field-level decisions on its own."]
    (M / "model_card.md").write_text("\n".join(parts) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
