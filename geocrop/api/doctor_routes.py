"""Plant Doctor API: leaf-photo disease screening."""
import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from geocrop.config import ROOT

router = APIRouter(prefix="/doctor", tags=["plant doctor"])
D = ROOT / "models/plant_disease"
MAX_BYTES = 12 * 1024 * 1024


def _ready():
    if not (D / "effnet_b0_best.pt").exists() or not (D / "metrics.json").exists():
        raise HTTPException(503, "Plant Doctor model not trained yet (run geocrop.plantdoctor.train)")


@router.get("/info")
def info():
    _ready()
    from geocrop.plantdoctor import infer
    m = json.loads((D / "metrics.json").read_text())
    keys = ("n", "top1", "top3", "top1_crop_given", "healthy_vs_diseased_acc_crop_given", "diseased_recall_crop_given", "ece")
    return {"crops": infer.crops(), "unsure_below": infer.UNSURE_BELOW, "trained_at": m["meta"]["trained_at"],
            "skill": {s: {k: m[s][k] for k in keys} for s in ("test_lab", "test_field")}}


@router.post("/diagnose")
async def diagnose(image: UploadFile = File(...), crop: str | None = Form(None)):
    _ready()
    data = await image.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "image larger than 12 MB")
    from PIL import UnidentifiedImageError
    from geocrop.plantdoctor import infer
    try:
        return infer.diagnose(data, crop or None)
    except UnidentifiedImageError:
        raise HTTPException(415, "not a readable image (use JPEG or PNG)")
    except ValueError as e:
        raise HTTPException(422, str(e))
