"""Plant Doctor inference: one leaf photo (+ optional crop) -> ranked, calibrated diagnosis."""
import io
import json
from functools import lru_cache

import numpy as np
from PIL import Image, ImageOps

from geocrop.config import ROOT

D = ROOT / "models/plant_disease"
UNSURE_BELOW = 0.5

CROP_MR = {"apple": "सफरचंद", "blueberry": "ब्लूबेरी", "cherry": "चेरी", "maize": "मका", "grape": "द्राक्ष", "orange": "संत्रा",
           "peach": "पीच", "bell_pepper": "ढोबळी मिरची", "potato": "बटाटा", "raspberry": "रास्पबेरी", "soybean": "सोयाबीन",
           "squash": "भोपळा (स्क्वॉश)", "strawberry": "स्ट्रॉबेरी", "tomato": "टोमॅटो"}
COND = {  # English, Marathi (Marathi needs expert review)
    "healthy": ("Healthy", "निरोगी"), "scab": ("Scab", "खपली (स्कॅब)"), "black_rot": ("Black rot", "काळी कूज"),
    "cedar_apple_rust": ("Cedar apple rust", "तांबेरा"), "powdery_mildew": ("Powdery mildew", "भुरी"),
    "gray_leaf_spot": ("Gray leaf spot", "करडे ठिपके"), "common_rust": ("Common rust", "तांबेरा"),
    "northern_leaf_blight": ("Northern leaf blight", "पानांवरील करपा"), "esca": ("Esca (black measles)", "एस्का"),
    "isariopsis_leaf_spot": ("Isariopsis leaf spot", "पानांवरील ठिपके (आयसॅरिऑप्सिस)"), "citrus_greening": ("Citrus greening (HLB)", "ग्रीनिंग (एचएलबी)"),
    "bacterial_spot": ("Bacterial spot", "जिवाणूजन्य ठिपके"), "early_blight": ("Early blight", "लवकर येणारा करपा"),
    "late_blight": ("Late blight", "उशिरा येणारा करपा"), "leaf_scorch": ("Leaf scorch", "पाने करपणे"),
    "leaf_mold": ("Leaf mould", "पानांवरील बुरशी"), "septoria_leaf_spot": ("Septoria leaf spot", "सेप्टोरिया ठिपके"),
    "two_spotted_spider_mite": ("Two-spotted spider mite", "लाल कोळी"), "target_spot": ("Target spot", "टार्गेट स्पॉट"),
    "yellow_leaf_curl_virus": ("Yellow leaf curl virus", "पर्णगुच्छ / पिवळा पर्णवक्र विषाणू"), "mosaic_virus": ("Mosaic virus", "मोझॅक विषाणू"),
}


@lru_cache(maxsize=1)
def load():
    import torch
    from geocrop.plantdoctor.train import make_model
    meta = json.loads((D / "metrics.json").read_text())["meta"]
    model = make_model(pretrained=False)
    model.load_state_dict(torch.load(D / "effnet_b0_best.pt", map_location="cpu", weights_only=True))
    model.eval()
    torch.set_num_threads(4)
    return model, meta


def crops():
    _, meta = load()
    cs = sorted({v["crop"] for v in meta["labels"].values()})
    return [dict(crop=c, name=c.replace("_", " ").title(), name_mr=CROP_MR.get(c, c),
                 conditions=[v["condition"] for v in meta["labels"].values() if v["crop"] == c]) for c in cs]


def _prep(img, meta):
    import torch
    s = meta["img_size"]
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size; r = int(s * 1.14) / min(w, h)
    img = img.resize((max(1, round(w * r)), max(1, round(h * r))), Image.BILINEAR)
    w, h = img.size; l, t = (w - s) // 2, (h - s) // 2
    a = (np.asarray(img.crop((l, t, l + s, t + s)), dtype=np.float32) / 255 - meta["mean"]) / meta["std"]
    return torch.from_numpy(a.transpose(2, 0, 1)).unsqueeze(0).float()


def diagnose(data: bytes, crop: str | None = None, top_k=3):
    import torch
    model, meta = load()
    img = Image.open(io.BytesIO(data))
    warnings = []
    if min(img.size) < 160:
        warnings.append("low_resolution")
    x = _prep(img, meta)
    with torch.no_grad():
        logits = (model(x) + model(torch.flip(x, dims=[3]))) / 2  # flip test-time augmentation
    p = torch.softmax(logits[0] / meta["temperature"], 0).numpy()
    classes, labels = meta["classes"], meta["labels"]
    if crop:
        if crop not in {v["crop"] for v in labels.values()}:
            raise ValueError(f"crop '{crop}' is not covered by this model")
        mask = np.array([labels[c]["crop"] == crop for c in classes]); p = np.where(mask, p, 0); p = p / p.sum()
    order = np.argsort(-p)[:top_k]
    res = []
    for i in order:
        c = classes[i]; cr, cond = labels[c]["crop"], labels[c]["condition"]
        res.append(dict(label=c, crop=cr, crop_mr=CROP_MR.get(cr, cr), condition=cond, condition_name=COND[cond][0],
                        condition_name_mr=COND[cond][1], healthy=cond == "healthy", probability=round(float(p[i]), 4)))
    top = res[0]["probability"]
    return dict(predictions=res, confident=top >= UNSURE_BELOW, crop_given=crop, warnings=warnings,
                value_type="MODEL ESTIMATE from one photo (screening aid, not a diagnosis)")
