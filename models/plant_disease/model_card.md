# Model card: GeoCrop Plant Doctor (leaf disease classifier)

*Generated from `metrics.json`; trained 2026-11-20T13:48:31+00:00 on NVIDIA GeForce RTX 3050 6GB Laptop GPU; manifest hash `b823118ba2c799b5`.*

## What it does
* Classifies a photo of a single leaf into 38 crop–condition classes (14 crops: apple, bell_pepper, blueberry, cherry, grape, maize, orange, peach, potato, raspberry, soybean, squash, strawberry, tomato).
* **Not covered:** cotton, soybean diseases (only healthy soybean is in the data), onion, sugarcane, pulses, rice, pomegranate and most Maharashtra field crops. Pests, nutrient deficiency, herbicide or water damage are also not covered: the model will still pick one of its classes.
* Output is a ranked list with calibrated confidence. It is a **screening aid, not a diagnosis**; confirm with KVK / agriculture officer.

## Data and splits
* PlantVillage (lab photos, plain background). Split by **leaf**: repeat photos of one leaf never cross splits (official leaf map + perceptual-hash + photo-sequence grouping).
* PlantDoc (internet field photos). Official test set = field test; near-duplicates of any training image removed from it.
* Counts: `{'plantdoc/test_field': 231, 'plantdoc/train': 1973, 'plantdoc/val': 344, 'plantvillage/test_lab': 5571, 'plantvillage/train': 43301, 'plantvillage/val': 5433}`.

## Training
* efficientnet_b0 (ImageNet pretrained, timm 1.0.12), 224 px, 10 epochs, AdamW lr 0.0004, label smoothing 0.1, strong augmentation, field photos oversampled ×8.0, classes balanced by 1/√n.
* Checkpoint: best epoch by 0.7*val_field_top1 + 0.3*val_lab_top1; temperature fitted on val. Temperature 0.8831.
* **Calibration change (disclosed):** Temperature refit on the PlantDoc (field) validation photos only, after the first test read showed field over-confidence (ECE 0.1614). Only confidence values change; predictions and accuracies do not.

## Results (test sets used once)
| | Lab test (PlantVillage) | **Field test (PlantDoc)** |
|---|---|---|
| Images | 5571 | 231 |
| Top-1, all classes | 99.6% | 70.1% |
| Top-3, all classes | 100.0% | 91.8% |
| Top-1 when the crop is given (as in the app) | 99.6% | 81.4% |
| Healthy vs diseased, crop given | 100.0% | 96.5% |
| Diseased leaves flagged as diseased | 100.0% | 97.9% |
| Macro F1 | 0.994 | 0.695 |
| Calibration error (ECE) | 0.045 | 0.077 |

**Read the field column.** Lab accuracy is near-perfect because PlantVillage photos are uniform; real photos are much harder. PlantDoc's field test is small (a few to ~20 images per class), so per-class numbers are noisy.

### Weakest field classes (crop given, n ≥ 5)
| Class | n | Accuracy |
|---|---|---|
| tomato__bacterial_spot | 9 | 33.3% |
| maize__northern_leaf_blight | 12 | 50.0% |
| tomato__mosaic_virus | 10 | 50.0% |
| potato__early_blight | 8 | 62.5% |
| potato__late_blight | 8 | 62.5% |
| tomato__healthy | 8 | 62.5% |

## Intended use and limits
* Farmer self-screening of one clear leaf photo, in daylight, for the listed crops, with the crop chosen by the user.
* Show top-3 and confidence; below 50% confidence the app says it is unsure.
* Not validated on Maharashtra photos. PlantDoc images are web-scraped and labelled by non-pathologists (known label noise).
* Next: collect Maharashtra field photos with expert labels (KVK / SAU plant pathology), add cotton, soybean, onion, pomegranate, grape diseases.