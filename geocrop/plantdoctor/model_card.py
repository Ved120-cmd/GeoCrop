"""Generate models/plant_disease/model_card.md from metrics.json."""
import json

from geocrop.config import ROOT

D = ROOT / "models/plant_disease"


def main():
    m = json.loads((D / "metrics.json").read_text())
    meta, lab, fld = m["meta"], m["test_lab"], m["test_field"]
    crops = sorted({v["crop"] for v in meta["labels"].values()})
    pct = lambda x: f"{100 * x:.1f}%"
    worst = sorted(((c, r) for c, r in fld["per_class"].items() if r["n"] >= 5), key=lambda t: t[1]["acc_crop_given"])[:6]
    lines = [
        "# Model card: GeoCrop Plant Doctor (leaf disease classifier)", "",
        f"*Generated from `metrics.json`; trained {meta['trained_at']} on {meta['device']}; manifest hash `{meta['manifest_sha256']}`.*", "",
        "## What it does",
        f"* Classifies a photo of a single leaf into {len(meta['classes'])} crop–condition classes ({len(crops)} crops: {', '.join(crops)}).",
        "* **Not covered:** cotton, soybean diseases (only healthy soybean is in the data), onion, sugarcane, pulses, rice, pomegranate and most "
        "Maharashtra field crops. Pests, nutrient deficiency, herbicide or water damage are also not covered: the model will still pick one of its classes.",
        "* Output is a ranked list with calibrated confidence. It is a **screening aid, not a diagnosis**; confirm with KVK / agriculture officer.", "",
        "## Data and splits",
        "* PlantVillage (lab photos, plain background). Split by **leaf**: repeat photos of one leaf never cross splits "
        "(official leaf map + perceptual-hash + photo-sequence grouping).",
        "* PlantDoc (internet field photos). Official test set = field test; near-duplicates of any training image removed from it.",
        f"* Counts: `{meta['manifest_info']['by_split']}`.", "",
        "## Training",
        f"* {meta['arch']} (ImageNet pretrained, timm {meta['versions']['timm']}), {meta['img_size']} px, {meta['epochs']} epochs, AdamW lr {meta['lr']}, "
        f"label smoothing 0.1, strong augmentation, field photos oversampled ×{meta['field_oversampling']}, classes balanced by 1/√n.",
        f"* Checkpoint: {meta['selection']}. Temperature {meta['temperature']}.",
        *([f"* **Calibration change (disclosed):** {meta['calibration_note']}"] if meta.get("calibration_note") else []), "",
        "## Results (test sets used once)",
        "| | Lab test (PlantVillage) | **Field test (PlantDoc)** |", "|---|---|---|",
        f"| Images | {lab['n']} | {fld['n']} |",
        f"| Top-1, all classes | {pct(lab['top1'])} | {pct(fld['top1'])} |",
        f"| Top-3, all classes | {pct(lab['top3'])} | {pct(fld['top3'])} |",
        f"| Top-1 when the crop is given (as in the app) | {pct(lab['top1_crop_given'])} | {pct(fld['top1_crop_given'])} |",
        f"| Healthy vs diseased, crop given | {pct(lab['healthy_vs_diseased_acc_crop_given'])} | {pct(fld['healthy_vs_diseased_acc_crop_given'])} |",
        f"| Diseased leaves flagged as diseased | {pct(lab['diseased_recall_crop_given'])} | {pct(fld['diseased_recall_crop_given'])} |",
        f"| Macro F1 | {lab['macro_f1']:.3f} | {fld['macro_f1']:.3f} |",
        f"| Calibration error (ECE) | {lab['ece']:.3f} | {fld['ece']:.3f} |", "",
        "**Read the field column.** Lab accuracy is near-perfect because PlantVillage photos are uniform; real photos are much harder. "
        "PlantDoc's field test is small (a few to ~20 images per class), so per-class numbers are noisy.", "",
        "### Weakest field classes (crop given, n ≥ 5)",
        "| Class | n | Accuracy |", "|---|---|---|",
        *[f"| {c} | {r['n']} | {pct(r['acc_crop_given'])} |" for c, r in worst], "",
        "## Intended use and limits",
        "* Farmer self-screening of one clear leaf photo, in daylight, for the listed crops, with the crop chosen by the user.",
        "* Show top-3 and confidence; below 50% confidence the app says it is unsure.",
        "* Not validated on Maharashtra photos. PlantDoc images are web-scraped and labelled by non-pathologists (known label noise).",
        "* Next: collect Maharashtra field photos with expert labels (KVK / SAU plant pathology), add cotton, soybean, onion, pomegranate, grape diseases.",
    ]
    (D / "model_card.md").write_text("\n".join(lines), encoding="utf-8")
    print("model card written")


if __name__ == "__main__":
    main()
