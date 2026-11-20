"""Plant Doctor dataset: unified labels, leakage-safe splits, image cache.

Sources (both public, CC BY / CC BY-SA):
  * PlantVillage (Hughes & Salathe 2015): 54k LAB photos, one leaf on a plain background, 38 classes.
    The same leaf was photographed several times -> images are grouped by leaf before splitting
    (official leaf-map.json where available; otherwise a perceptual-hash + photo-number grouping).
  * PlantDoc (Singh et al. 2020): ~2.6k FIELD/internet photos (cropped classification version).
    Its official test split is our "real-world" test; near-duplicates of any training image are removed from it.

Output: data/processed/plantdoctor/manifest.parquet with path, label, source, group, split
        split in {train, val, test_lab, test_field}
"""
import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from geocrop.config import PROCESSED, RAW, SCRATCH

PV = RAW / "plant_health/plantvillage/PlantVillage-Dataset"
PD = RAW / "plant_health/plantdoc/PlantDoc-Dataset"
OUT = PROCESSED / "plantdoctor"
CACHE = SCRATCH.parent / "plant_cache"          # D:\geocrop_work\plant_cache (resized field photos)
SEED = 20261119

# canonical label -> (crop, condition, PlantVillage folder, PlantDoc folder or None)
LABELS = {
    "apple__scab": ("apple", "scab", "Apple___Apple_scab", "Apple Scab Leaf"),
    "apple__black_rot": ("apple", "black_rot", "Apple___Black_rot", None),
    "apple__cedar_rust": ("apple", "cedar_apple_rust", "Apple___Cedar_apple_rust", "Apple rust leaf"),
    "apple__healthy": ("apple", "healthy", "Apple___healthy", "Apple leaf"),
    "blueberry__healthy": ("blueberry", "healthy", "Blueberry___healthy", "Blueberry leaf"),
    "cherry__powdery_mildew": ("cherry", "powdery_mildew", "Cherry_(including_sour)___Powdery_mildew", None),
    "cherry__healthy": ("cherry", "healthy", "Cherry_(including_sour)___healthy", "Cherry leaf"),
    "maize__gray_leaf_spot": ("maize", "gray_leaf_spot", "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot", "Corn Gray leaf spot"),
    "maize__common_rust": ("maize", "common_rust", "Corn_(maize)___Common_rust_", "Corn rust leaf"),
    "maize__northern_leaf_blight": ("maize", "northern_leaf_blight", "Corn_(maize)___Northern_Leaf_Blight", "Corn leaf blight"),
    "maize__healthy": ("maize", "healthy", "Corn_(maize)___healthy", None),
    "grape__black_rot": ("grape", "black_rot", "Grape___Black_rot", "grape leaf black rot"),
    "grape__esca": ("grape", "esca", "Grape___Esca_(Black_Measles)", None),
    "grape__leaf_blight": ("grape", "isariopsis_leaf_spot", "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)", None),
    "grape__healthy": ("grape", "healthy", "Grape___healthy", "grape leaf"),
    "orange__greening": ("orange", "citrus_greening", "Orange___Haunglongbing_(Citrus_greening)", None),
    "peach__bacterial_spot": ("peach", "bacterial_spot", "Peach___Bacterial_spot", None),
    "peach__healthy": ("peach", "healthy", "Peach___healthy", "Peach leaf"),
    "pepper__bacterial_spot": ("bell_pepper", "bacterial_spot", "Pepper,_bell___Bacterial_spot", "Bell_pepper leaf spot"),
    "pepper__healthy": ("bell_pepper", "healthy", "Pepper,_bell___healthy", "Bell_pepper leaf"),
    "potato__early_blight": ("potato", "early_blight", "Potato___Early_blight", "Potato leaf early blight"),
    "potato__late_blight": ("potato", "late_blight", "Potato___Late_blight", "Potato leaf late blight"),
    "potato__healthy": ("potato", "healthy", "Potato___healthy", None),
    "raspberry__healthy": ("raspberry", "healthy", "Raspberry___healthy", "Raspberry leaf"),
    "soybean__healthy": ("soybean", "healthy", "Soybean___healthy", "Soyabean leaf"),
    "squash__powdery_mildew": ("squash", "powdery_mildew", "Squash___Powdery_mildew", "Squash Powdery mildew leaf"),
    "strawberry__leaf_scorch": ("strawberry", "leaf_scorch", "Strawberry___Leaf_scorch", None),
    "strawberry__healthy": ("strawberry", "healthy", "Strawberry___healthy", "Strawberry leaf"),
    "tomato__bacterial_spot": ("tomato", "bacterial_spot", "Tomato___Bacterial_spot", "Tomato leaf bacterial spot"),
    "tomato__early_blight": ("tomato", "early_blight", "Tomato___Early_blight", "Tomato Early blight leaf"),
    "tomato__late_blight": ("tomato", "late_blight", "Tomato___Late_blight", "Tomato leaf late blight"),
    "tomato__leaf_mold": ("tomato", "leaf_mold", "Tomato___Leaf_Mold", "Tomato mold leaf"),
    "tomato__septoria_leaf_spot": ("tomato", "septoria_leaf_spot", "Tomato___Septoria_leaf_spot", "Tomato Septoria leaf spot"),
    "tomato__spider_mites": ("tomato", "two_spotted_spider_mite", "Tomato___Spider_mites Two-spotted_spider_mite", "Tomato two spotted spider mites leaf"),
    "tomato__target_spot": ("tomato", "target_spot", "Tomato___Target_Spot", None),
    "tomato__yellow_leaf_curl_virus": ("tomato", "yellow_leaf_curl_virus", "Tomato___Tomato_Yellow_Leaf_Curl_Virus", "Tomato leaf yellow virus"),
    "tomato__mosaic_virus": ("tomato", "mosaic_virus", "Tomato___Tomato_mosaic_virus", "Tomato leaf mosaic virus"),
    "tomato__healthy": ("tomato", "healthy", "Tomato___healthy", "Tomato leaf"),
}
CLASSES = sorted(LABELS)


def dhash(path, size=8):
    """64-bit difference hash; robust to small resizes/re-encodes."""
    im = Image.open(path).convert("L").resize((size + 1, size), Image.BILINEAR)
    a = np.asarray(im, dtype=np.int16)
    return np.packbits((a[:, 1:] > a[:, :-1]).ravel()).view(">u8")[0]


_POP = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)


def _hamming(a, b):
    """Pairwise Hamming distance between two uint64 hash vectors (popcount via byte lookup table)."""
    x = np.bitwise_xor(a[:, None], b[None, :])
    return _POP[x.view(np.uint8).reshape(*x.shape, 8)].sum(-1, dtype=np.uint8)


def _hashes(paths, cache_name):
    """dhash for each path, cached on D: (hashing 54k images from E: takes ~40 min)."""
    f = CACHE / f"{cache_name}_dhash.parquet"
    old = pd.read_parquet(f).set_index("path").h.to_dict() if f.exists() else {}
    todo = [p for p in paths if p not in old]
    if todo:  # disk-bound: threads help
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(8) as ex:
            for i, (p, h) in enumerate(zip(todo, ex.map(lambda q: int(dhash(q)), todo, chunksize=64))):
                old[p] = h
                if i % 5000 == 0:
                    print(" hashed", i, "/", len(todo), flush=True)
    out = [old[p] for p in paths]
    CACHE.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"path": list(old), "h": [np.uint64(v) for v in old.values()]}).to_parquet(f, index=False)
    return np.array(out, dtype=np.uint64)


class _UF:
    def __init__(self, n): self.p = list(range(n))
    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]; i = self.p[i]
        return i
    def union(self, a, b): self.p[self.find(a)] = self.find(b)


def plantvillage():
    leafmap = {k.lower(): v[0] for k, v in json.loads((PV / "leaf-map.json").read_text()).items()}
    rows = []
    for lab, (_, _, pv, _) in LABELS.items():
        for f in sorted(os.listdir(PV / "raw/color" / pv)):
            key = os.path.splitext(f.split("___", 1)[1])[0].lower() if "___" in f else None
            m = re.match(r"(.*?)\s*(\d+)$", key or "")
            rows.append(dict(path=str(PV / "raw/color" / pv / f), label=lab, source="plantvillage",
                             leaf=leafmap.get(key), src=m.group(1) if m else None, num=int(m.group(2)) if m else None))
    df = pd.DataFrame(rows)
    print("hashing", len(df), "PlantVillage images ...", flush=True)
    df["h"] = _hashes(df.path.tolist(), "plantvillage")
    # group = union of (official leaf id) + (near-exact copy: hash <=2 bits, same class; looser thresholds chain
    #   thousands of distinct plain-background leaves together)
    #       + (unmapped photos with consecutive numbers from the same source series, same class)
    uf = _UF(len(df))
    for _, g in df.groupby("label"):
        idx = g.index.values
        for _, gg in g.dropna(subset=["leaf"]).groupby("leaf"):
            for i in gg.index[1:]: uf.union(i, gg.index[0])
        un = g[g.leaf.isna() & g.num.notna()]
        for _, gg in un.groupby([un.src, un.num // 10]):
            for i in gg.index[1:]: uf.union(i, gg.index[0])
        h = g.h.values.astype(np.uint64)
        for s in range(0, len(idx), 400):
            d = _hamming(h[s:s + 400], h)
            for a, b in zip(*np.nonzero(d <= 2)):
                if s + a < b: uf.union(idx[s + a], idx[b])
    df["group"] = ["pv%d" % uf.find(i) for i in range(len(df))]
    return df


def plantdoc():
    inv = {v[3]: k for k, v in LABELS.items() if v[3]}
    rows = []
    for split in ("train", "test"):
        for cls in sorted(os.listdir(PD / split)):
            if cls not in inv:
                continue
            for f in sorted(os.listdir(PD / split / cls)):
                src = PD / split / cls / f
                dst = CACHE / "plantdoc" / split / cls / (Path(f).stem + ".jpg")
                if not dst.exists():
                    try:
                        im = Image.open(src).convert("RGB")
                    except Exception as e:  # a few PlantDoc files are broken
                        print("skip", src.name, type(e).__name__); continue
                    im.thumbnail((448, 448)); dst.parent.mkdir(parents=True, exist_ok=True); im.save(dst, quality=92)
                rows.append(dict(path=str(dst), label=inv[cls], source="plantdoc", pd_split=split))
    df = pd.DataFrame(rows)
    df["h"] = _hashes(df.path.tolist(), "plantdoc")
    return df


def build():
    rng = np.random.default_rng(SEED)
    pv, pdc = plantvillage(), plantdoc()
    # PlantVillage: split whole leaf-groups 80/10/10 within each class
    pv["split"] = ""
    for _, g in pv.groupby("label"):
        sizes = g.group.value_counts(); groups = np.array(sizes.index, dtype=object); rng.shuffle(groups)
        # fill test then val to ~10% of IMAGES each (whole groups only)
        cut, acc, n = {}, 0, len(g)
        for gr in groups:
            cut[gr] = "test_lab" if acc < 0.1 * n else "val" if acc < 0.2 * n else "train"; acc += sizes[gr]
        pv.loc[g.index, "split"] = g.group.map(cut)
    # PlantDoc: official test -> test_field; official train -> 85% train / 15% val (by near-dup group)
    uf = _UF(len(pdc)); h = pdc.h.values.astype(np.uint64)
    for s in range(0, len(h), 400):
        for a, b in zip(*np.nonzero(_hamming(h[s:s + 400], h) <= 4)):
            if s + a < b: uf.union(s + a, b)
    pdc["group"] = ["pd%d" % uf.find(i) for i in range(len(pdc))]
    test_groups = set(pdc[pdc.pd_split == "test"].group)
    tr = pdc[(pdc.pd_split == "train") & ~pdc.group.isin(test_groups)].copy()   # train images duplicated in test are dropped
    dropped_train = int(((pdc.pd_split == "train") & pdc.group.isin(test_groups)).sum())
    gs = np.array(tr.group.unique(), dtype=object); rng.shuffle(gs); val_g = set(gs[: int(0.15 * len(gs))])
    tr["split"] = np.where(tr.group.isin(val_g), "val", "train")
    te = pdc[pdc.pd_split == "test"].copy(); te["split"] = "test_field"
    # remove field-test images that near-duplicate ANY training/val image (PlantDoc is web-scraped)
    train_h = np.concatenate([pv.h.values, tr.h.values]).astype(np.uint64)
    dmin = np.concatenate([_hamming(te.h.values.astype(np.uint64)[i:i + 50], train_h).min(1) for i in range(0, len(te), 50)])
    te = te[dmin > 4]
    df = pd.concat([pv, tr, te], ignore_index=True)[["path", "label", "source", "group", "split", "h"]]
    df["h"] = df.h.astype("uint64").astype(str)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / "manifest.parquet", index=False)
    info = dict(n=len(df), by_split=df.groupby(["source", "split"]).size().rename(lambda x: str(x)).to_dict() if False else
                {f"{a}/{b}": int(n) for (a, b), n in df.groupby(["source", "split"]).size().items()},
                plantdoc_train_dropped_as_dup_of_test=dropped_train, plantdoc_test_dropped_as_dup_of_train=int((dmin <= 4).sum()),
                pv_groups=int(pv.group.nunique()), classes=len(CLASSES))
    (OUT / "manifest_info.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info, indent=1))
    return df


if __name__ == "__main__":
    build()
