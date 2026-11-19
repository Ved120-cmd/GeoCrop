"""Train and evaluate the 16/32-day water-stress models (proxy target: SMAP root-zone percentile).

Split by YEAR (no shuffling - forecasts must be tested on unseen seasons):
  train 2015-2021 | validation 2022-2023 (early stopping, model choice) | test 2024-2026 (held out, used once)
Models per lead: LightGBM point (chosen on validation among L2 / L1 / L1-on-change), quantiles (p10/p90),
LightGBM "dry" classifier (pct <= 20),
XGBoost point (baseline required by the spec). Baselines: persistence, climatology (50th pct), damped persistence.
The DEPLOYED model is exactly the one evaluated (trained on 2015-2023); metrics in metrics.json describe it.

Usage: python -m geocrop.predict.train
"""
import hashlib
import json
from datetime import datetime, timezone

import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.linear_model import LinearRegression
from sklearn.metrics import brier_score_loss, mean_absolute_error, mean_squared_error, roc_auc_score

from geocrop.config import PROCESSED, ROOT
from geocrop.predict import features as F

OUT = ROOT / "models/water_stress"
DRY = 20.0
SPLITS = {"train": (2015, 2021), "val": (2022, 2023), "test": (2024, 2026)}
LGB_PARAMS = dict(learning_rate=0.03, num_leaves=31, min_data_in_leaf=60, feature_fraction=0.8, bagging_fraction=0.8,
                  bagging_freq=1, lambda_l2=1.0, verbose=-1, seed=42, num_threads=4)


def _split(df, name):
    a, b = SPLITS[name]
    return df[(df.issue_date.dt.year >= a) & (df.issue_date.dt.year <= b)]


def _season(m):
    return np.select([m.isin([6, 7, 8, 9]), m.isin([10, 11, 12, 1])], ["monsoon (Jun-Sep)", "post-monsoon (Oct-Jan)"], "dry season (Feb-May)")


def _reg_metrics(y, p, base_mae=None):
    mae = mean_absolute_error(y, p)
    out = dict(mae=round(mae, 2), rmse=round(float(np.sqrt(mean_squared_error(y, p))), 2), r2=round(float(1 - np.sum((y - p) ** 2) / np.sum((y - y.mean()) ** 2)), 3))
    if base_mae:
        out["skill_vs_persistence"] = round(1 - mae / base_mae, 3)
    return out


def _cls_metrics(ydry, prob, clim_rate):
    brier = brier_score_loss(ydry, prob)
    brier_clim = brier_score_loss(ydry, np.full(len(ydry), clim_rate))
    pred = prob >= 0.5
    tp = int((pred & ydry).sum()); fp = int((pred & ~ydry).sum()); fn = int((~pred & ydry).sum())
    return dict(brier=round(brier, 4), brier_skill_vs_climatology=round(1 - brier / brier_clim, 3),
                auc=round(float(roc_auc_score(ydry, prob)), 3) if 0 < ydry.mean() < 1 else None,
                precision=round(tp / max(tp + fp, 1), 3), recall=round(tp / max(tp + fn, 1), 3), base_rate=round(float(ydry.mean()), 3))


def train_lead(df, L):
    feats = F.features_for(L)
    y = f"y_pct_{L}"
    d = df.dropna(subset=[y, "sm_pct_now"]).copy()
    tr, va, te = _split(d, "train"), _split(d, "val"), _split(d, "test")
    trva = pd.concat([tr, va])
    res = dict(lead_days=L, n=dict(train=len(tr), val=len(va), test=len(te)),
               periods={k: f"{a}-{b}" for k, (a, b) in SPLITS.items()}, features=feats)

    # ---- candidate point models, chosen on VALIDATION years only (test years untouched until the end)
    #      "delta_*" models predict the change from today's percentile and add it back.
    cands = {"lgbm_l2": ("regression", False), "lgbm_l1": ("l1", False), "lgbm_delta_l1": ("l1", True)}
    val_mae, iters = {}, {}
    for name, (obj, delta) in cands.items():
        ytr = tr[y] - tr.sm_pct_now if delta else tr[y]
        yva = va[y] - va.sm_pct_now if delta else va[y]
        m0 = lgb.train(LGB_PARAMS | {"objective": obj}, lgb.Dataset(tr[feats], ytr), 3000, valid_sets=[lgb.Dataset(va[feats], yva)],
                       callbacks=[lgb.early_stopping(150, verbose=False)])
        iters[name] = max(m0.best_iteration, 50)
        pv = m0.predict(va[feats], num_iteration=iters[name]) + (va.sm_pct_now.values if delta else 0)
        val_mae[name] = round(mean_absolute_error(va[y], np.clip(pv, 0, 100)), 3)
    val_mae["persistence"] = round(mean_absolute_error(va[y], va.sm_pct_now), 3)
    chosen = min(cands, key=lambda k: val_mae[k])
    obj, delta = cands[chosen]
    n_iter = iters[chosen]
    res["model_selection_on_validation"] = dict(val_mae=val_mae, chosen=chosen)
    yy = (trva[y] - trva.sm_pct_now) if delta else trva[y]
    point = lgb.train(LGB_PARAMS | {"objective": obj}, lgb.Dataset(trva[feats], yy), n_iter)
    q = {a: lgb.train(LGB_PARAMS | {"objective": "quantile", "alpha": a}, lgb.Dataset(trva[feats], yy), n_iter) for a in (0.1, 0.9)}
    dry = lgb.train(LGB_PARAMS | {"objective": "binary"}, lgb.Dataset(trva[feats], (trva[y] <= DRY).astype(int)), n_iter)
    offset = (lambda frame: frame.sm_pct_now.values) if delta else (lambda frame: 0.0)
    # ---- XGBoost baseline on the same target formulation (absolute-error objective)
    ytr_x = (tr[y] - tr.sm_pct_now) if delta else tr[y]
    yva_x = (va[y] - va.sm_pct_now) if delta else va[y]
    xp = dict(learning_rate=0.03, max_depth=6, subsample=0.8, colsample_bytree=0.8, min_child_weight=20, reg_lambda=1.0, n_jobs=4,
              random_state=42, objective="reg:absoluteerror")
    xm = xgb.XGBRegressor(n_estimators=3000, early_stopping_rounds=150, **xp).fit(tr[feats], ytr_x, eval_set=[(va[feats], yva_x)], verbose=False)
    xbest = max(xm.best_iteration, 50)
    xfinal = xgb.XGBRegressor(n_estimators=xbest, **xp).fit(trva[feats], yy)
    damped = LinearRegression().fit(trva[["sm_pct_now"]], trva[y])

    # ---- evaluation on the held-out TEST years
    yt = te[y].values
    preds = {"persistence": te.sm_pct_now.values, "climatology": np.full(len(te), 50.0),
             "damped_persistence": damped.predict(te[["sm_pct_now"]]), "xgboost": xfinal.predict(te[feats]) + offset(te),
             "lightgbm": point.predict(te[feats]) + offset(te)}
    base = mean_absolute_error(yt, preds["persistence"])
    res["test_regression"] = {k: _reg_metrics(yt, np.clip(v, 0, 100), base) for k, v in preds.items()}
    lo, hi = np.clip(q[0.1].predict(te[feats]) + offset(te), 0, 100), np.clip(q[0.9].predict(te[feats]) + offset(te), 0, 100)
    res["test_interval_10_90"] = dict(coverage=round(float(((yt >= lo) & (yt <= hi)).mean()), 3), mean_width=round(float(np.mean(hi - lo)), 1))
    ydry = yt <= DRY
    clim_rate = float((trva[y] <= DRY).mean())
    res["test_dry_classification"] = {"lightgbm": _cls_metrics(ydry, dry.predict(te[feats]), clim_rate),
                                      "persistence (dry now -> dry later)": _cls_metrics(ydry, (te.sm_pct_now.values <= DRY).astype(float) * 0.98 + 0.01, clim_rate),
                                      "climatology": _cls_metrics(ydry, np.full(len(te), clim_rate), clim_rate)}
    by = {}
    seas = _season(te.issue_date.dt.month)
    for sname in np.unique(seas):
        mk = seas == sname
        b = mean_absolute_error(yt[mk], preds["persistence"][mk])
        by[sname] = {"n": int(mk.sum()), "lightgbm": _reg_metrics(yt[mk], np.clip(preds["lightgbm"][mk], 0, 100), b),
                     "persistence": _reg_metrics(yt[mk], preds["persistence"][mk])}
    res["test_by_season"] = by
    res["test_by_year"] = {int(yy): {"n": int((te.issue_date.dt.year == yy).sum()),
                                     "lightgbm_mae": round(mean_absolute_error(yt[te.issue_date.dt.year == yy], np.clip(preds["lightgbm"][te.issue_date.dt.year == yy], 0, 100)), 2),
                                     "persistence_mae": round(mean_absolute_error(yt[te.issue_date.dt.year == yy], preds["persistence"][te.issue_date.dt.year == yy]), 2)}
                           for yy in sorted(te.issue_date.dt.year.unique())}

    # ---- global explanation: mean |SHAP| on the test set (TreeSHAP via LightGBM pred_contrib)
    contrib = point.predict(te[feats], pred_contrib=True)[:, :-1]
    imp = pd.Series(np.abs(contrib).mean(0), index=feats).sort_values(ascending=False)
    res["shap_mean_abs_test"] = {k: round(float(v), 3) for k, v in imp.items()}
    res["best_iterations"] = dict(lightgbm=int(n_iter), xgboost=int(xbest))
    res["target_formulation"] = "change from today's percentile (added back)" if delta else "percentile"
    res["predict_delta"] = bool(delta)

    d_out = OUT / f"lead{L}"
    d_out.mkdir(parents=True, exist_ok=True)
    point.save_model(str(d_out / "lgbm_point.txt")); q[0.1].save_model(str(d_out / "lgbm_q10.txt")); q[0.9].save_model(str(d_out / "lgbm_q90.txt"))
    dry.save_model(str(d_out / "lgbm_dry.txt")); xfinal.save_model(str(d_out / "xgb_point.json"))
    return res


def main():
    df = pd.read_parquet(PROCESSED / "predict_features.parquet")
    df["issue_date"] = pd.to_datetime(df.issue_date)
    h = hashlib.sha256(pd.util.hash_pandas_object(df[["issue_date", "district_id", "y_pct_16", "y_pct_32"]], index=False).values.tobytes()).hexdigest()[:16]
    meta = dict(trained_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), training_data="data/processed/predict_features.parquet",
                training_data_hash=h, target="SMAP L4 root-zone soil-moisture percentile (vs 2015-2024, same time of year) at issue date + lead",
                target_type="PROXY for crop water stress (model-assimilated satellite soil moisture), not measured crop stress",
                dry_threshold_pct=DRY, versions=dict(lightgbm=lgb.__version__, xgboost=xgb.__version__), leakage_rules=F.LAT,
                no_future_weather="No weather forecasts used (ECMWF reforecasts unavailable): only information published by the issue date + climatology.")
    out = {"meta": meta}
    for L in F.LEADS:
        out[f"lead{L}"] = train_lead(df, L)
        r = out[f"lead{L}"]["test_regression"]
        print(f"lead {L}: " + " | ".join(f"{k} MAE {v['mae']}" + (f" skill {v.get('skill_vs_persistence')}" if k not in ('persistence',) else "") for k, v in r.items()), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "metrics.json").write_text(json.dumps(out, indent=1))
    from geocrop.predict import model_card
    model_card.main()
    return out


if __name__ == "__main__":
    main()
