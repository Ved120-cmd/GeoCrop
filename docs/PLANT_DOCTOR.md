# Plant Doctor: leaf-disease screening from one photo

**What it does:** the farmer chooses a crop (optional) and takes or uploads a photo of one leaf. The model returns:
- the 3 most likely crop–condition classes, each with a calibrated probability;
- an "unsure" flag when the top probability is below 50%.

It is a **screening aid, not a diagnosis**. The page always points to the KVK or agriculture officer and the Kisan Call Centre before any spraying.

Full metrics: [`models/plant_disease/model_card.md`](../models/plant_disease/model_card.md), generated from `metrics.json`.

## Coverage
- **Included:** 38 classes over 14 crops. Apple, bell pepper, blueberry, cherry, grape, maize, orange, peach, potato, raspberry, soybean (healthy only), squash, strawberry and tomato.
- **Not covered:** cotton, soybean diseases, onion, sugarcane, pulses, rice, pomegranate. The model also doesn't recognise pests, nutrient deficiency or spray and water damage, but it will still choose one of its classes for such photos. The page says this.

## Pipeline

| Step | Code | Output |
|---|---|---|
| Labels + leakage-safe splits | `geocrop/plantdoctor/dataset.py` | `data/processed/plantdoctor/manifest.parquet`, `manifest_info.json` |
| Training + evaluation | `geocrop/plantdoctor/train.py` | `models/plant_disease/effnet_b0_best.pt` (16 MB), `metrics.json`, `model_card.md` |
| Inference | `geocrop/plantdoctor/infer.py` | used by the API |
| API | `geocrop/api/doctor_routes.py` | `GET /doctor/info`, `POST /doctor/diagnose` (multipart: `image`, optional `crop`) |
| Web page | `frontend/src/pages/DoctorPage.tsx` | `/plant-doctor` |

## Data and splits

**PlantVillage** (54,305 lab photos)
- The same leaf was photographed several times, so images are grouped before splitting. Groups come from:
  - the official `leaf-map.json`, which covers 41k images;
  - consecutive photo numbers from the same series;
  - near-exact copies (dhash ≤ 2 bits).
- Whole groups are assigned to train/val/test at 80/10/10 per class.
- A looser hash threshold (6 bits) chained thousands of distinct plain-background leaves together and put 83% of blueberry into test, so it was rejected.

**PlantDoc** (2,572 internet field photos)
- The official test set is our field test.
- Near-duplicates were removed in both directions: 19 training photos that duplicated test photos, and 5 test photos that duplicated training photos.

**Final split:**

| Split | Lab photos | Field photos |
|---|---|---|
| Train | 43,301 | 1,973 |
| Validation | 5,433 | 344 |
| Lab test | 5,571 | – |
| Field test | – | 231 |

`tests/test_doctor.py` checks that no group and no identical image crosses splits.

## Training
- EfficientNet-B0 with ImageNet weights (timm), at 224 px, for 10 epochs. AdamW with a one-cycle learning-rate schedule (max 4e-4), label smoothing, and strong augmentation.
- Field photos are oversampled ×8, and classes are balanced by 1/√n.
- The checkpoint is chosen on validation: 0.7 × field + 0.3 × lab top-1, which picked epoch 10.
- Training ran on an RTX 3050 in about 50 minutes.

**Hard-won lessons on this laptop:**
- `channels_last` memory format is **9× slower** with cuDNN 9.1 here (29 vs 258 img/s), so it isn't used.
- The Windows page file had to move to D:. GPU allocations under WDDM count against system commit, and with C: full the commit limit was exhausted.

## Results (test sets used once)

| | Lab test (5,571) | **Field test (231)** |
|---|---|---|
| Top-1, all classes | 99.6% | **70.1%** |
| Top-1, crop given (as in the app) | 99.6% | **81.4%** |
| Top-3 | 100% | 91.8% |
| Healthy vs diseased, crop given | 99.98% | 96.5% |
| Calibration error (ECE) | 0.045 | 0.077 |

- **The field column is the realistic one.** Lab photos are uniform, so lab accuracy says little about real use.
- **Weakest field classes:** tomato bacterial spot (33%), maize northern leaf blight (50%), tomato mosaic virus (50%). Each has only 8–12 test photos, so these numbers are noisy.
- **Calibration change (disclosed):** the first temperature was fitted on the mostly-lab validation set and left field predictions over-confident (ECE 0.16). It was refit on the field validation photos only. This was done **after** the first test read; only the confidence values changed, not the predictions or accuracies.

## Run

```bash
.venv/Scripts/python -m geocrop.plantdoctor.dataset   # splits (first run hashes 54k images, ~40 min; cached on D:)
GEOCROP_WORKERS=4 .venv/Scripts/python -m geocrop.plantdoctor.train   # ~50 min on the RTX 3050; stop preview servers first
```

The first API call after a server start takes about 20 s, while PyTorch and the model load.

## Improving it
1. **Maharashtra field photos with expert labels** (KVK / SAU plant pathology), for validation first and then for fine-tuning.
2. **Add the state's major crops:** cotton (pink bollworm damage, leaf curl), soybean (yellow mosaic, rust), onion (purple blotch), pomegranate (bacterial blight), and more grape diseases (downy mildew).
3. **A pest model on IP102.** It needs a manual download.
4. **An "is this a leaf / a known crop?" gate,** so the model can refuse unrelated photos.
