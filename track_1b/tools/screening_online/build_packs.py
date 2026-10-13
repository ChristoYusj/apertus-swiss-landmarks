"""Build the data files for the online (shared) photo-screening page.

  data/cards.json      one entry per landmark: name, town, canton, photo ids, face flags, source links, pack index
  img/cNN.json         photo packs {image_id: base64 JPEG (420 px, q70)}, 22 landmarks per pack, loaded on scroll
Run with the project venv: python build_packs.py <track_1b dir> <output dir>
"""
import base64
import io
import json
import sys
from pathlib import Path

from PIL import Image

root, out = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(root / "src"))
from landmarks_eval.build.review_page import cards  # noqa: E402

PER_PACK, WIDTH, QUALITY = 22, 420, 70
work = root / "work"
images = [json.loads(l) for l in open(work / "images.jsonl", encoding="utf-8")]
lms = [json.loads(l) for l in open(work / "landmarks_final.jsonl", encoding="utf-8")]
data = cards(images, lms)
(out / "data").mkdir(parents=True, exist_ok=True)
(out / "img").mkdir(parents=True, exist_ok=True)


def thumb(image_id: str) -> str:
    im = Image.open(work / "images" / f"{image_id}.jpg").convert("RGB")
    h = round(im.height * WIDTH / im.width)
    b = io.BytesIO()
    im.resize((WIDTH, h), Image.LANCZOS).save(b, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    return base64.b64encode(b.getvalue()).decode("ascii")


total = 0
for k in range(0, len(data), PER_PACK):
    pack = {}
    for c in data[k:k + PER_PACK]:
        c["pack"] = k // PER_PACK
        for p in [c["main"]] + c["alts"]:
            pack[p["id"]] = thumb(p["id"])
            p.pop("fallback", None)
    path = out / "img" / f"c{k // PER_PACK:02d}.json"
    path.write_text(json.dumps(pack, separators=(",", ":")), encoding="utf-8")
    total += path.stat().st_size
(out / "data" / "cards.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"{len(data)} cards, {sum(1 + len(c['alts']) for c in data)} photos, "
      f"{len(range(0, len(data), PER_PACK))} packs, {total / 1e6:.1f} MB")
