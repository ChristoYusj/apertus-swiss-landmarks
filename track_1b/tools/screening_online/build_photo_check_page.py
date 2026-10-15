"""Online human check of every published photo (photo_check.html), built from the assembled dataset.

  python build_photo_check_page.py <dataset dir> <out dir>

One row per landmark with exactly the published photos (main, 2nd view, too generic), embedded byte for byte as
published (no re-encoding), 20 rows per pack, rows with a face-detector hit first. Checks are stored per landmark
(collection `pcheck`, doc = QID: main/alt/low = ok | exclude | wrong | reject, agree, t) or downloaded as
photo_check_A1.json.
"""

import base64
import json
import sys
from pathlib import Path

ds, out = Path(sys.argv[1]), Path(sys.argv[2])
PER_PACK = 20
imgs = {json.loads(l)["image_id"]: json.loads(l) for l in open(ds / "metadata" / "images.jsonl", encoding="utf-8")}
lms = [json.loads(l) for l in open(ds / "data" / "landmarks.jsonl", encoding="utf-8")]
cases = [json.loads(l) for l in open(ds / "data" / "test_cases.jsonl", encoding="utf-8")]
slot_of = {"photo_main": "main", "photo_alt": "alt", "trap_lowinfo": "low"}
shipped: dict[str, dict] = {}
for c in cases:
    if c["arm"] in slot_of:
        shipped.setdefault(c["landmark_qid"], {})[slot_of[c["arm"]]] = c["image_id"]
rows = []
for n, lm in enumerate(sorted(lms, key=lambda l: l["qid"]), 1):
    ph = shipped[lm["qid"]]
    name = next((v for v in (lm["labels"].get(l) for l in ("fr", "de", "en", "it", "rm")) if v), lm["qid"])
    risk = [f"face detector ({s})" for s, i in ph.items() if imgs[i]["faces_detected"]]
    row = {"qid": lm["qid"], "n": n, "name": name, "town": lm["municipality_name"], "canton": lm["canton_code"],
           "ai": {"main": "ok", "note": ""}, "risk": risk}
    for s in ("main", "alt", "low"):
        row[s] = {"id": ph[s], "page": imgs[ph[s]]["commons_page_url"]} if s in ph else None
    rows.append(row)
rows.sort(key=lambda r: (not r["risk"], r["n"]))
(out / "data").mkdir(parents=True, exist_ok=True)
(out / "img").mkdir(parents=True, exist_ok=True)
total = 0
for k in range(0, len(rows), PER_PACK):
    pack = {}
    for r in rows[k:k + PER_PACK]:
        r["pack"] = k // PER_PACK
        for s in ("main", "alt", "low"):
            if r[s]:
                pack[r[s]["id"]] = base64.b64encode((ds / "images" / f"{r[s]['id']}.jpg").read_bytes()).decode("ascii")
    path = out / "img" / f"k{k // PER_PACK:02d}.json"
    path.write_text(json.dumps(pack, separators=(",", ":")), encoding="utf-8")
    total += path.stat().st_size
(out / "data" / "rows.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
(out / "index.html").write_text((Path(__file__).parent / "photo_check.html").read_text(encoding="utf-8"), encoding="utf-8")
print(f"{len(rows)} rows ({sum(1 for r in rows if r['risk'])} with a face-detector hit), "
      f"{sum(1 for r in rows for s in ('main', 'alt', 'low') if r[s])} photos, {total / 1e6:.1f} MB")
