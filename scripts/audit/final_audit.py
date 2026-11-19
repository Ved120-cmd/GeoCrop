"""PHASE 8-9 - Re-run the full audit, compare with the initial snapshot, compute weighted readiness.

Writes reports/GEOCROP_READINESS_REPORT.md and reports/readiness.json
Usage: python scripts/audit/final_audit.py [--skip-rescan]

Readiness weighting
-------------------
Dataset score  : VALID 1.0 | NEEDS PREPROCESSING 0.75 | INCOMPLETE 0.4 | INVALID / MISSING / RESTRICTED 0
                 weighted by catalog weight (1-5).
Model score    : fraction of 8 components present (training data, preprocessing, training code, config,
                 checkpoint, metrics, inference code, docs); weighted by model weight.
Overall        : 0.6 * data readiness + 0.4 * model readiness.
Module         : same formula restricted to that module's datasets/models (data only if the module has no ML model).
"""
import argparse, csv, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from catalog import CATALOG, MODELS, MODULE_REQ, ROOT  # noqa: E402

PY = sys.executable
SCORE = [("PRESENT AND VALID", 1.0), ("PRESENT BUT NEEDS PREPROCESSING", 0.75), ("PRESENT BUT INCOMPLETE", 0.4)]


def ds_score(st):
    return next((s for k, s in SCORE if st.startswith(k)), 0.0)


def wavg(pairs):
    w = sum(p[1] for p in pairs)
    return round(100 * sum(s * w_ for s, w_ in pairs) / w, 1) if w else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--skip-rescan", action="store_true"); a = ap.parse_args()
    if not a.skip_rescan:
        for s in ("scan_project.py", "validate_datasets.py --tag final", "check_models.py"):
            subprocess.run([PY, str(Path(__file__).parent / s.split()[0]), *s.split()[1:]], check=True)
    init = {d["dataset_id"]: d for d in json.load(open(ROOT / "reports/dataset_audit/dataset_audit_initial.json"))["datasets"]}
    fin = {d["dataset_id"]: d for d in json.load(open(ROOT / "reports/dataset_audit/dataset_audit_final.json"))["datasets"]}
    mod = json.load(open(ROOT / "reports/model_audit/model_audit.json"))
    mscore = {}
    for m, rec in zip(MODELS, mod["models"]):
        mscore[m["id"]] = round(1 - len(rec["missing"]) / (6 if m["id"] == "M2" else 8), 3)
    data_r = wavg([(ds_score(d["status"]), CATALOG[k]["weight"]) for k, d in fin.items() if CATALOG[k]["weight"] > 0])
    model_r = wavg([(mscore[m["id"]], m["weight"]) for m in MODELS])
    overall = round(0.6 * data_r + 0.4 * model_r, 1)
    modules = {}
    for name, (dids, mids) in MODULE_REQ.items():
        dr = wavg([(ds_score(fin[i]["status"]), CATALOG[i]["weight"]) for i in dids])
        mr = wavg([(mscore[i], next(m["weight"] for m in MODELS if m["id"] == i)) for i in mids]) if mids else None
        modules[name] = dict(data=dr, models=mr, overall=round(0.6 * dr + 0.4 * mr, 1) if mr is not None else dr,
                             blockers=[f"{i} {CATALOG[i]['name']} [{fin[i]['status']}]" for i in dids if ds_score(fin[i]["status"]) < 0.75])
    changes = [(k, init[k]["status"], fin[k]["status"]) for k in fin if k in init and init[k]["status"] != fin[k]["status"]]
    json.dump(dict(generated=datetime.now(timezone.utc).isoformat(timespec="seconds"), overall=overall, data=data_r, models=model_r,
                   model_scores=mscore, modules=modules, changes=changes), open(ROOT / "reports/readiness.json", "w"), indent=1)
    print(json.dumps(dict(overall=overall, data=data_r, models=model_r, modules={k: v["overall"] for k, v in modules.items()}), indent=1))
    for c in changes: print("CHANGED", *c)


if __name__ == "__main__":
    main()
