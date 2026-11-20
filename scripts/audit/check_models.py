"""PHASE 3 - Inventory ML models, checkpoints, code and dependencies.

Distinguishes:  (a) a GeoCrop-trained checkpoint with metadata + metrics,
                (b) a generic pretrained checkpoint (e.g. ImageNet weights),
                (c) code only / nothing.
A model only counts as TRAINED if a checkpoint loads AND a metrics file (metrics.json) sits beside it.

Writes reports/model_audit/model_inventory.csv and model_audit.json
"""
import csv, importlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from catalog import MODELS, ROOT  # noqa: E402

CKPT_EXT = {".pkl", ".joblib", ".ubj", ".pt", ".pth", ".onnx", ".keras", ".h5", ".safetensors", ".ckpt", ".bin", ".txt", ".json"}
SKIP = {".venv", "__pycache__", ".git"}
LIBS = {"xgboost": "xgboost", "lightgbm": "lightgbm", "shap": "shap", "sklearn": "scikit-learn", "torch": "torch",
        "torchvision": "torchvision", "timm": "timm", "tensorflow": "tensorflow", "ee": "earthengine-api"}


def lib_versions():
    out = {}
    for mod, pkg in LIBS.items():
        try:
            m = importlib.import_module(mod); out[pkg] = getattr(m, "__version__", "installed")
        except Exception as e:
            out[pkg] = f"NOT AVAILABLE ({type(e).__name__})"
    return out


def try_load(p: Path):
    e = p.suffix.lower()
    try:
        if e in (".pt", ".pth", ".ckpt"):
            import torch
            obj = torch.load(p, map_location="cpu", weights_only=True)
            keys = list(obj.keys())[:5] if isinstance(obj, dict) else type(obj).__name__
            return True, f"torch state ({keys})"
        if e == ".onnx":
            return True, "onnx file (not loaded; onnxruntime check skipped)"
        if e in (".json", ".ubj") and "xgb" in p.name.lower():
            import xgboost as xgb
            b = xgb.Booster(); b.load_model(str(p)); return True, f"xgboost booster, {b.num_features()} features"
        if e == ".txt" and "lgb" in p.name.lower():  # LightGBM text model
            import lightgbm as lgb
            b = lgb.Booster(model_file=str(p)); return True, f"lightgbm booster, {b.num_feature()} features"
        if e in (".pkl", ".joblib"):
            return None, "pickle/joblib - NOT loaded automatically (arbitrary code execution risk); verify provenance first"
    except Exception as ex:
        return False, f"{type(ex).__name__}: {ex}"
    return None, "unrecognised"


def find_code(code_dir: Path):
    files = [p for p in code_dir.rglob("*") if p.is_file() and p.suffix in (".py", ".ipynb")] if code_dir.exists() else []
    names = " ".join(p.name.lower() for p in files)
    return dict(files=[str(p.relative_to(ROOT)) for p in files],
                preprocessing=any(k in names for k in ("preprocess", "features", "dataset")),
                training="train" in names, evaluation=any(k in names for k in ("eval", "metric", "validate")),
                inference=any(k in names for k in ("infer", "predict", "serve")), config=any(k in names for k in ("config", ".yaml")))


def main():
    out = ROOT / "reports/model_audit"; out.mkdir(parents=True, exist_ok=True)
    libs = lib_versions()
    all_ckpts = [p for p in ROOT.rglob("*") if p.is_file() and p.suffix.lower() in CKPT_EXT and not any(s in p.parts for s in SKIP)
                 and "data" not in p.relative_to(ROOT).parts[:1]]
    # .h5/.json also appear as data; only treat files under models/ or named like checkpoints as model candidates
    cand = [p for p in all_ckpts if ("models" in p.parts and (p.suffix.lower() not in (".txt", ".json") or "lgb" in p.name.lower() or "xgb" in p.name.lower()))
            or p.suffix.lower() in (".pt", ".pth", ".onnx", ".ckpt", ".safetensors", ".pkl", ".joblib", ".keras")]
    rows, audit = [], []
    for m in MODELS:
        mdir, cdir = ROOT / m["dir"], ROOT / m["code"]
        ck = [p for p in cand if mdir in p.parents]
        loads = {str(p.relative_to(ROOT)): try_load(p) for p in ck}
        metrics = list(mdir.rglob("metrics*.json")) if mdir.exists() else []
        meta = list(mdir.rglob("model_card*.md")) + list(mdir.rglob("metadata*.json")) if mdir.exists() else []
        code = find_code(cdir)
        labels_ok = bool(m.get("labels")) and (ROOT / m["labels"]).exists()
        metrics = metrics or (list(mdir.parent.glob("metrics*.json")) if mdir.parent.exists() else [])  # shared metrics file
        meta = meta or list(mdir.parent.glob("model_card*.md"))
        trained = any(v[0] for v in loads.values()) and bool(metrics)
        # hyper-parameters, features and iterations are recorded in metrics.json for the GeoCrop models
        config_ok = code["config"] or any(k in p.read_text(errors="ignore") for p in metrics for k in ("best_iterations", "\"epochs\""))
        missing = [k for k, ok in [("training dataset/labels", labels_ok), ("preprocessing pipeline", code["preprocessing"]),
                                   ("training code", code["training"]), ("model config", config_ok),
                                   ("trained checkpoint", bool(ck)), ("evaluation metrics", bool(metrics)),
                                   ("inference code", code["inference"]), ("documentation/model card", bool(meta))] if not ok]
        if m["id"] == "M2":  # rule-based: no checkpoint expected
            missing = [x for x in missing if x not in ("trained checkpoint", "training dataset/labels")]
        rec = dict(model=m["name"], module=m["module"], architecture={"M1a": "XGBoost + LightGBM baselines; LSTM/TCN later",
                   "M1b": "XGBoost + LightGBM baselines; LSTM/TCN later", "M2": "Agronomic rules + scoring", "M3": "EfficientNet-B0 / MobileNetV3 transfer learning",
                   "M4": "ResNet/EfficientNet classifier (IP102)", "M5": "LightGBM / temporal CNN on S1+S2 time series", "M6": "SHAP TreeExplainer + model registry"}[m["id"]],
                   training_data="; ".join(m["needs_data"]), checkpoints=list(loads), load_results=loads, metrics_files=[str(p) for p in metrics],
                   training_status="TRAINED (verified)" if trained else ("CHECKPOINT WITHOUT METRICS" if ck else "NOT TRAINED"),
                   inference_status="POSSIBLE" if trained and code["inference"] else "NOT POSSIBLE",
                   code=code, missing=missing)
        audit.append(rec)
        deps = {"M1a": ["xgboost", "lightgbm", "shap"], "M1b": ["xgboost", "lightgbm", "shap"], "M2": [], "M3": ["torch", "torchvision", "timm"],
                "M4": ["torch", "torchvision", "timm"], "M5": ["lightgbm", "earthengine-api"], "M6": ["shap"]}[m["id"]]
        rows.append([rec["model"], rec["architecture"], rec["training_data"], ";".join(rec["checkpoints"]) or "none",
                     rec["training_status"], rec["inference_status"], ";".join(rec["metrics_files"]) or "none",
                     "; ".join(f"{d}={libs.get(d, '?')}" for d in deps), "; ".join(missing),
                     "Build pipeline in " + m["code"] + " once training data/labels exist" if missing else "none"])
    with open(out / "model_inventory.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Model name", "Architecture", "Training data", "Checkpoint path", "Training status", "Inference status",
                    "Evaluation metrics", "Dependencies", "Missing components", "Recommended action"])
        w.writerows(rows)
    other = [str(p.relative_to(ROOT)) for p in cand if not any((ROOT / m["dir"]) in p.parents for m in MODELS)]
    json.dump(dict(generated=datetime.now(timezone.utc).isoformat(timespec="seconds"), libraries=libs,
                   unassigned_checkpoints=other, models=audit), open(out / "model_audit.json", "w"), indent=1, default=str)
    for r in rows: print(f"{r[0][:50]:50s} {r[4]:28s} missing: {r[8][:90]}")
    print("libraries:", libs); print("unassigned checkpoints:", other)


if __name__ == "__main__":
    main()
