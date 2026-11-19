"""PHASE 1 - Recursively inventory the GeoCrop project.

Outputs  data/manifests/file_inventory.csv  and  file_inventory.json
 - every file (excluding .venv / caches), size, extension class, sha256
 - ZIP / TAR member listings (archives are read, never extracted or modified)
 - duplicate groups by content hash
 - best-guess catalog dataset id (by glob match)

Usage:  python scripts/audit/scan_project.py [--root PATH] [--no-hash-over MB]
"""
import argparse, csv, fnmatch, hashlib, json, sys, tarfile, zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from catalog import CATALOG, ROOT  # noqa: E402

SKIP_DIRS = {".venv", "__pycache__", ".git", ".ipynb_checkpoints", "node_modules"}
DATA_EXT = {".csv", ".xlsx", ".xls", ".json", ".geojson", ".shp", ".shx", ".dbf", ".prj", ".gpkg", ".tif", ".tiff",
            ".nc", ".hdf", ".h5", ".parquet", ".grib", ".grb", ".grd", ".bin", ".vrt", ".topojson"}
MODEL_EXT = {".pkl", ".joblib", ".ubj", ".pt", ".pth", ".onnx", ".keras", ".safetensors", ".ckpt"}
CODE_EXT = {".py", ".ipynb", ".js", ".r", ".sql"}
DOC_EXT = {".pdf", ".md", ".txt", ".docx", ".html"}
ARCH_EXT = {".zip", ".tar", ".gz", ".tgz", ".7z", ".rar"}
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def classify(p: Path) -> str:
    e = p.suffix.lower()
    if e in ARCH_EXT: return "archive"
    if e in MODEL_EXT: return "model"
    if e in DATA_EXT: return "data"
    if e in CODE_EXT: return "code"
    if e in DOC_EXT: return "document"
    if e in IMG_EXT: return "image"
    return "other"


def sha256(p: Path, limit_mb: float):
    if p.stat().st_size > limit_mb * 1e6:
        return ""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def archive_members(p: Path):
    try:
        if zipfile.is_zipfile(p):
            with zipfile.ZipFile(p) as z:
                return [(i.filename, i.file_size) for i in z.infolist() if not i.is_dir()]
        if tarfile.is_tarfile(p):
            with tarfile.open(p) as t:
                return [(m.name, m.size) for m in t.getmembers() if m.isfile()]
    except Exception as e:  # corrupt archive
        return [("<ERROR>", str(e))]
    return []


def match_dataset(rel: str):
    rel = rel.replace("\\", "/")
    hits = []
    for did, r in CATALOG.items():
        for g in r["globs"]:
            if fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(rel, g.replace("/**/", "/")):
                hits.append(did)
                break
    return hits


def scan(root: Path, hash_limit_mb: float, image_summary=True):
    rows = []
    img_dirs = {}
    for p in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in p.parts) or not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        cls = classify(p)
        # Image datasets can hold 100k files: summarise per top-level class dir instead of hashing each.
        if cls == "image" and image_summary:
            key = "/".join(rel.split("/")[:5])
            d = img_dirs.setdefault(p.parent.relative_to(root).as_posix(), [0, 0])
            d[0] += 1; d[1] += p.stat().st_size
            continue
        st = p.stat()
        row = dict(path=rel, ext=p.suffix.lower(), cls=cls, size_bytes=st.st_size,
                   modified=datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                   sha256=sha256(p, hash_limit_mb), dataset_ids=";".join(match_dataset(rel)),
                   archive_members="")
        if cls == "archive":
            mem = archive_members(p)
            row["archive_members"] = json.dumps(mem[:500])
            row["archive_member_count"] = len(mem)
        rows.append(row)
    # duplicates
    by_hash = {}
    for r in rows:
        if r["sha256"]:
            by_hash.setdefault(r["sha256"], []).append(r["path"])
    for r in rows:
        grp = by_hash.get(r["sha256"], [])
        r["duplicate_of"] = grp[0] if len(grp) > 1 and grp[0] != r["path"] else ""
        r["duplicate_group_size"] = len(grp) if r["sha256"] else ""
    imgs = [dict(dir=k, n_images=v[0], size_bytes=v[1], dataset_ids=";".join(match_dataset(k + "/x.jpg")))
            for k, v in sorted(img_dirs.items())]
    return rows, imgs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--hash-limit-mb", type=float, default=2000)
    ap.add_argument("--out", default=str(ROOT / "data/manifests"))
    a = ap.parse_args()
    root, out = Path(a.root), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows, imgs = scan(root, a.hash_limit_mb)
    cols = ["path", "ext", "cls", "size_bytes", "modified", "sha256", "duplicate_of", "duplicate_group_size",
            "dataset_ids", "archive_member_count", "archive_members"]
    with open(out / "file_inventory.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    with open(out / "image_dirs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["dir", "n_images", "size_bytes", "dataset_ids"]); w.writeheader(); w.writerows(imgs)
    summary = dict(generated=datetime.now(timezone.utc).isoformat(timespec="seconds"), root=str(root),
                   n_files=len(rows), n_image_files=sum(i["n_images"] for i in imgs),
                   total_bytes=sum(r["size_bytes"] for r in rows) + sum(i["size_bytes"] for i in imgs),
                   by_class={}, duplicate_groups=0)
    for r in rows:
        summary["by_class"][r["cls"]] = summary["by_class"].get(r["cls"], 0) + 1
    summary["duplicate_groups"] = len({r["duplicate_of"] for r in rows if r["duplicate_of"]})
    json.dump(dict(summary=summary, files=rows, image_dirs=imgs), open(out / "file_inventory.json", "w", encoding="utf-8"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
