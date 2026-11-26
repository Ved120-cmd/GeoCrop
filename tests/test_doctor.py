"""Plant Doctor: split hygiene, label mapping, inference and API."""
import io
import json

import pandas as pd
import pytest
from PIL import Image

from geocrop.config import ROOT
from geocrop.plantdoctor.dataset import CLASSES, LABELS, OUT

MAN = OUT / "manifest.parquet"
MODEL = ROOT / "models/plant_disease/effnet_b0_best.pt"


def test_label_map_is_one_to_one():
    pv = [v[2] for v in LABELS.values()]; pdoc = [v[3] for v in LABELS.values() if v[3]]
    assert len(set(pv)) == len(pv) == 38 and len(set(pdoc)) == len(pdoc)
    assert CLASSES == sorted(CLASSES)


@pytest.mark.skipif(not MAN.exists(), reason="run geocrop.plantdoctor.dataset first")
def test_no_leaf_or_duplicate_crosses_splits():
    m = pd.read_parquet(MAN)
    # every leaf-group lives in exactly one split
    assert (m.groupby("group").split.nunique() == 1).all()
    # no identical image (same class + same hash) in both a training split and a test split
    # (a 64-bit dhash can collide between unrelated photos of different classes; those are not leaks)
    key = m.label + ":" + m.h
    tr = set(key[m.split.isin(["train", "val"])]); te = set(key[m.split.isin(["test_lab", "test_field"])])
    assert not (tr & te)
    assert set(m[m.split == "test_field"].source) == {"plantdoc"}


@pytest.mark.skipif(not MODEL.exists(), reason="train the model first")
def test_diagnose_and_api():
    from fastapi.testclient import TestClient
    from geocrop.api.main import app
    m = pd.read_parquet(MAN)
    row = m[(m.split == "test_lab") & (m.label == "tomato__late_blight")].iloc[0]
    data = open(row.path, "rb").read()
    c = TestClient(app, headers={"X-GeoCrop-Client": "web"})
    r = c.post("/doctor/diagnose", files={"image": ("leaf.jpg", data, "image/jpeg")}, data={"crop": "tomato"}).json()
    assert len(r["predictions"]) == 3 and all(p["crop"] == "tomato" for p in r["predictions"])
    assert abs(sum(p["probability"] for p in r["predictions"]) - 1) < 0.2
    assert r["predictions"][0]["probability"] >= r["predictions"][1]["probability"]
    assert c.post("/doctor/diagnose", files={"image": ("x.txt", b"not an image", "text/plain")}).status_code == 415
    assert c.post("/doctor/diagnose", files={"image": ("leaf.jpg", data, "image/jpeg")}, data={"crop": "cotton"}).status_code == 422
    info = c.get("/doctor/info").json()
    assert {"test_lab", "test_field"} == set(info["skill"]) and len(info["crops"]) == 14
