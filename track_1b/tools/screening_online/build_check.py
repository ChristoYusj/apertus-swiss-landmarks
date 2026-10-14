"""Build the data files for the human check of the AI photo screening (check.html, protocol v3-ai-assisted).

  data/rows.json   one row per landmark: the AI's decision, the photos that would be published (main, 2nd view,
                   too generic) and the reasons it is flagged; flagged rows first
  img/kNN.json     photo packs {image_id: base64 JPEG (420 px, q70)}, 20 rows per pack, loaded on scroll
Run with the project venv: python build_check.py <track_1b dir> <screening_ai.json> <output dir>
"""
import base64
import io
import json
import sys
from pathlib import Path

from PIL import Image

root, ai_path, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
PER_PACK, WIDTH, QUALITY = 20, 420, 70
work = root / "work"
images = {i["image_id"]: i for i in (json.loads(l) for l in open(work / "images.jsonl", encoding="utf-8"))}
lms = [json.loads(l) for l in open(work / "landmarks_final.jsonl", encoding="utf-8")]
ai = json.loads(ai_path.read_text(encoding="utf-8"))
assert ai.get("format") == "ai-screening", ai_path
dec, recheck = ai["decisions"], ai["recheck"]
SLOT_NAME = {"main": "main photo", "alt": "2nd view", "low": "too generic photo"}


def risks(qid: str, d: dict, shipped: dict) -> list[str]:
    r = []
    if d["main"] != "ok":
        r.append({"exclude": "AI: exclude", "wrong": "AI: wrong object"}[d["main"]])
    if d["confidence"] != "high":
        r.append(f"AI confidence {d['confidence']}")
    by_id = {p["id"]: p for p in d["photos"]}
    for slot, iid in shipped.items():
        where = SLOT_NAME[slot]
        for who, p in (("screener", by_id.get(iid)), ("checker", recheck.get(iid))):
            if not p:
                continue
            if p["people"] == "recognisable":
                r.append(f"{who}: recognisable person ({where})")
            elif p["people"] == "distant_unrecognisable":
                r.append(f"{who}: distant people ({where})")
            for k, t in (("plate_readable", "plate"), ("private_interior", "private interior"), ("personal_text", "personal text")):
                if p.get(k):
                    r.append(f"{who}: {t} ({where})")
        c = recheck.get(iid)
        if c and c["role_ok"] != "yes":
            r.append(f"checker: {where} {c['role_ok']}" if slot != "main" else f"checker: shows the landmark? {c['role_ok']}")
        if iid not in recheck:
            r.append(f"not re-checked ({where})")
        if images[iid]["faces_detected"]:
            r.append(f"face detector ({where})")
    return list(dict.fromkeys(r))


rows = []
for n, lm in enumerate(lms, 1):
    d = dec[lm["qid"]]
    main_id = lm["main_image_id"]
    shipped = {"main": main_id}
    for slot in ("alt", "low"):
        if d.get(slot) and d[slot] != "none":
            shipped[slot] = d[slot]
    name = next((v for v in (lm["labels"].get(l) for l in ("fr", "de", "en", "it", "rm")) if v), lm["qid"])
    note = d["main_reason"] if d["main"] != "ok" else d.get("note", "")
    row = {"qid": lm["qid"], "n": n, "name": name, "town": lm["municipality_name"], "canton": lm["canton_code"],
           "ai": {"main": d["main"], "note": note[:220]}, "risk": risks(lm["qid"], d, shipped)}
    for slot in ("main", "alt", "low"):
        row[slot] = {"id": shipped[slot], "page": images[shipped[slot]]["commons_page_url"]} if slot in shipped else None
    rows.append(row)
SEVERITY = [("AI: exclude", "AI: wrong object", "recognisable person", "plate", "private interior", "personal text",
             "shows the landmark? no"),
            ("unsure", " no", "face detector", "not re-checked"), ("distant people",), ("AI confidence",)]


def severity(r: dict) -> int:
    for k, keys in enumerate(SEVERITY):
        if any(key in t for t in r["risk"] for key in keys):
            return k
    return len(SEVERITY)


rows.sort(key=lambda r: (severity(r), r["n"]))   # privacy / wrong object first, then doubts, then the rest


def thumb(image_id: str) -> str:
    im = Image.open(work / "images" / f"{image_id}.jpg").convert("RGB")
    h = round(im.height * WIDTH / im.width)
    b = io.BytesIO()
    im.resize((WIDTH, h), Image.LANCZOS).save(b, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    return base64.b64encode(b.getvalue()).decode("ascii")


(out / "data").mkdir(parents=True, exist_ok=True)
(out / "img").mkdir(parents=True, exist_ok=True)
total = 0
for k in range(0, len(rows), PER_PACK):
    pack = {}
    for r in rows[k:k + PER_PACK]:
        r["pack"] = k // PER_PACK
        for slot in ("main", "alt", "low"):
            if r[slot]:
                pack[r[slot]["id"]] = thumb(r[slot]["id"])
    path = out / "img" / f"k{k // PER_PACK:02d}.json"
    path.write_text(json.dumps(pack, separators=(",", ":")), encoding="utf-8")
    total += path.stat().st_size
(out / "data" / "rows.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"{len(rows)} rows ({sum(1 for r in rows if r['risk'])} flagged), "
      f"{sum(1 for r in rows for s in ('main', 'alt', 'low') if r[s])} photos, {total / 1e6:.1f} MB")
