"""Train the Plant Doctor leaf-disease classifier (transfer learning, EfficientNet-B0, ImageNet weights).

Honest-evaluation rules
  * Splits come from dataset.py (leaf-grouped PlantVillage, de-duplicated PlantDoc).
  * Training mixes LAB (PlantVillage) and FIELD (PlantDoc train) photos; field photos are oversampled
    because a lab-only model is known to collapse on real photos.
  * Checkpoint and temperature are chosen on VALIDATION only; the two test sets are evaluated once at the end.
  * Reported separately: lab test (PlantVillage) and field test (PlantDoc) - the field number is the realistic one.

Run:  python -m geocrop.plantdoctor.train      (GPU strongly recommended; ~30-40 min on an RTX 3050)
"""
import hashlib
import json
import os
import time
from datetime import datetime, timezone

os.environ.setdefault("HF_HOME", r"D:\geocrop_work\hf_cache")  # pretrained weights cache (not C:)

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
torch.backends.cudnn.benchmark = True
from PIL import Image
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import transforms as T

from geocrop.config import ROOT
from geocrop.plantdoctor.dataset import CLASSES, LABELS, OUT as DATA_OUT

MODEL_DIR = ROOT / "models/plant_disease"
ARCH = "efficientnet_b0"
IMG = 224
MEAN, STD = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)
EPOCHS, BATCH, LR, FIELD_WEIGHT = 10, 48, 4e-4, 8.0
# each Windows DataLoader worker re-imports torch (~0.5 GB commit); this machine has little headroom
WORKERS = int(os.environ.get("GEOCROP_WORKERS", "2"))
SEED = 20261119

train_tf = T.Compose([
    T.RandomResizedCrop(IMG, scale=(0.35, 1.0), ratio=(0.75, 1.33)),
    T.RandomHorizontalFlip(), T.RandomVerticalFlip(), T.RandomRotation(25),
    T.ColorJitter(0.35, 0.35, 0.3, 0.04), T.RandomGrayscale(0.03),
    T.RandomApply([T.GaussianBlur(5, (0.1, 2.0))], p=0.25),
    T.ToTensor(), T.Normalize(MEAN, STD), T.RandomErasing(p=0.25, scale=(0.02, 0.15)),
])
eval_tf = T.Compose([T.Resize(int(IMG * 1.14)), T.CenterCrop(IMG), T.ToTensor(), T.Normalize(MEAN, STD)])


class Images(Dataset):
    def __init__(self, df, tf):
        self.p, self.y, self.tf = df.path.tolist(), df.label.map({c: i for i, c in enumerate(CLASSES)}).tolist(), tf
    def __len__(self): return len(self.p)
    def __getitem__(self, i):
        return self.tf(Image.open(self.p[i]).convert("RGB")), self.y[i]


def make_model(pretrained=True):
    import timm
    return timm.create_model(ARCH, pretrained=pretrained, num_classes=len(CLASSES), drop_rate=0.3, drop_path_rate=0.1)


@torch.no_grad()
def logits_for(model, df, dev, bs=128):
    model.eval(); out = []
    dl = DataLoader(Images(df, eval_tf), batch_size=bs, num_workers=0)
    for x, _ in dl:
        with torch.autocast("cuda", enabled=dev.type == "cuda"):
            out.append(model(x.to(dev, non_blocking=True)).float().cpu())
    return torch.cat(out)


def fit_temperature(logits, y):
    t = torch.zeros(1, requires_grad=True); opt = torch.optim.LBFGS([t], lr=0.1, max_iter=100)
    def closure():
        opt.zero_grad(); loss = F.cross_entropy(logits / t.exp(), y); loss.backward(); return loss
    opt.step(closure); return float(t.exp())


CROP_OF = {c: LABELS[c][0] for c in CLASSES}
CROP_IDX = {cr: [i for i, c in enumerate(CLASSES) if CROP_OF[c] == cr] for cr in sorted(set(CROP_OF.values()))}


def evaluate(logits, labels, temp):
    from sklearn.metrics import f1_score
    y = np.array([CLASSES.index(l) for l in labels]); p = F.softmax(logits / temp, 1).numpy()
    pred = p.argmax(1); top3 = np.argsort(-p, 1)[:, :3]
    # crop-given accuracy: the app asks the farmer for the crop, so restrict to that crop's classes
    pc = p.copy()
    for i, l in enumerate(labels):
        mask = np.zeros(p.shape[1], bool); mask[CROP_IDX[CROP_OF[l]]] = True; pc[i, ~mask] = 0
    pred_c = pc.argmax(1)
    conf = p.max(1); bins = np.linspace(0, 1, 11); ece = 0.0
    for a, b in zip(bins[:-1], bins[1:]):
        m = (conf > a) & (conf <= b)
        if m.any(): ece += m.mean() * abs((pred[m] == y[m]).mean() - conf[m].mean())
    # healthy-vs-diseased (what matters most to a farmer)
    hy = np.array([LABELS[CLASSES[i]][1] == "healthy" for i in y]); hp = np.array([LABELS[CLASSES[i]][1] == "healthy" for i in pred_c])
    per = {}
    for c in sorted(set(labels)):
        m = y == CLASSES.index(c)
        per[c] = dict(n=int(m.sum()), acc=round(float((pred[m] == y[m]).mean()), 3), acc_crop_given=round(float((pred_c[m] == y[m]).mean()), 3))
    present = sorted(set(y))
    return dict(n=int(len(y)), top1=round(float((pred == y).mean()), 4), top3=round(float((top3 == y[:, None]).any(1).mean()), 4),
                macro_f1=round(float(f1_score(y, pred, labels=present, average="macro")), 4),
                top1_crop_given=round(float((pred_c == y).mean()), 4),
                healthy_vs_diseased_acc_crop_given=round(float((hy == hp).mean()), 4),
                diseased_recall_crop_given=round(float(((~hy) & (~hp)).sum() / max((~hy).sum(), 1)), 4),
                ece=round(float(ece), 4), per_class=per)


def main():
    torch.manual_seed(SEED); np.random.seed(SEED)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    man = pd.read_parquet(DATA_OUT / "manifest.parquet")
    tr, va = man[man.split == "train"], man[man.split == "val"]
    w = np.where(tr.source == "plantdoc", FIELD_WEIGHT, 1.0)
    # also balance classes (PlantVillage is very imbalanced: 5k tomato curl virus vs 150 apple rust)
    cls_n = tr.label.map(tr.label.value_counts()); w = w / np.sqrt(cls_n.values)
    sampler = WeightedRandomSampler(torch.tensor(w, dtype=torch.double), num_samples=len(tr), replacement=True)
    dl = DataLoader(Images(tr, train_tf), batch_size=BATCH, sampler=sampler, num_workers=WORKERS, pin_memory=True, persistent_workers=WORKERS > 0, drop_last=True)
    model = make_model().to(dev)  # NB: channels_last is ~9x slower with cuDNN 9.1 here (benchmarked)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.02)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=LR, total_steps=EPOCHS * len(dl), pct_start=0.1)
    scaler = torch.amp.GradScaler(enabled=dev.type == "cuda")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    best, hist = -1, []
    va_field = va[va.source == "plantdoc"]; va_lab = va[va.source == "plantvillage"].sample(min(3000, (va.source == "plantvillage").sum()), random_state=SEED)
    for ep in range(EPOCHS):
        model.train(); t0 = time.time(); tot = 0.0
        for i, (x, y) in enumerate(dl):
            x, y = x.to(dev, non_blocking=True), y.to(dev, non_blocking=True)
            with torch.autocast("cuda", enabled=dev.type == "cuda"):
                loss = F.cross_entropy(model(x), y, label_smoothing=0.1)
            opt.zero_grad(set_to_none=True); scaler.scale(loss).backward(); scaler.step(opt); scaler.update(); sched.step()
            tot += loss.item()
            if i % 200 == 0:
                print(f"  epoch {ep + 1} step {i}/{len(dl)} loss {loss.item():.3f} {(time.time() - t0) / 60:.1f} min", flush=True)
        lf, ll = logits_for(model, va_field, dev), logits_for(model, va_lab, dev)
        af = float((lf.argmax(1).numpy() == np.array([CLASSES.index(l) for l in va_field.label])).mean())
        al = float((ll.argmax(1).numpy() == np.array([CLASSES.index(l) for l in va_lab.label])).mean())
        score = 0.7 * af + 0.3 * al  # selection weighted to field photos (the realistic use case)
        hist.append(dict(epoch=ep + 1, loss=round(tot / len(dl), 4), val_field_top1=round(af, 4), val_lab_top1=round(al, 4), minutes=round((time.time() - t0) / 60, 1)))
        print(hist[-1], flush=True)
        if score > best:
            best = score; torch.save(model.state_dict(), MODEL_DIR / "effnet_b0_best.pt")
    model.load_state_dict(torch.load(MODEL_DIR / "effnet_b0_best.pt", weights_only=True))
    lv = logits_for(model, va, dev)
    temp = fit_temperature(lv, torch.tensor([CLASSES.index(l) for l in va.label]))
    res = {"val": evaluate(lv, va.label.tolist(), temp)}
    for s in ("test_lab", "test_field"):  # evaluated exactly once
        d = man[man.split == s]
        res[s] = evaluate(logits_for(model, d, dev), d.label.tolist(), temp)
        print(s, {k: v for k, v in res[s].items() if k != "per_class"}, flush=True)
    import timm
    meta = dict(trained_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), arch=ARCH, img_size=IMG, mean=MEAN, std=STD,
                classes=CLASSES, labels={c: dict(crop=LABELS[c][0], condition=LABELS[c][1]) for c in CLASSES},
                temperature=round(temp, 4), epochs=EPOCHS, batch=BATCH, lr=LR, field_oversampling=FIELD_WEIGHT, history=hist,
                selection="best epoch by 0.7*val_field_top1 + 0.3*val_lab_top1; temperature fitted on val",
                manifest_sha256=hashlib.sha256((DATA_OUT / "manifest.parquet").read_bytes()).hexdigest()[:16],
                manifest_info=json.loads((DATA_OUT / "manifest_info.json").read_text()),
                versions=dict(torch=torch.__version__, timm=timm.__version__), device=torch.cuda.get_device_name(0) if dev.type == "cuda" else "cpu")
    (MODEL_DIR / "metrics.json").write_text(json.dumps(dict(meta=meta, **res), indent=1))
    from geocrop.plantdoctor import model_card
    model_card.main()


if __name__ == "__main__":
    main()
