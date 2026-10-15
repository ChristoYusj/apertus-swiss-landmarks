"""Record the human check of every published photo in the screening provenance.

  python apply_photo_check.py <check.json> <work dir>

<check.json> is one of:
  - the online page's download (photo_check.html, format "photo-check": one entry per landmark with
    main/alt/low = ok | exclude | wrong | reject);
  - the page's database documents (collection `pcheck`), as a list of {"id": QID, "data": {...}} or a {QID: {...}} map;
  - read_photo_check_pdf.py's output ({"checked_by", "source", "photos", "flagged"}); a PDF cannot show that a
    box was looked at, only that it was ticked, so its completeness rests on the checker's statement.

With no photo flagged, it adds `human_photo_check` to the report in work/review/merged.json and A1 to the reviewers
of every shipped photo in work/images.jsonl; then run `landmarks-eval assemble`, regenerate the card and re-score.
A flagged photo changes the dataset: the script stops and lists it (record it as an A1 decision in
work/review/a1_decisions.json and rebuild the screening; run this script again afterwards, since merge-review
rewrites merged.json). An online check with a shipped photo left undecided is refused.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SLOT_OF = {"photo_main": "main", "photo_alt": "alt", "trap_lowinfo": "low"}


def shipped_photos(ds: Path) -> dict[str, dict[str, str]]:
    """{QID: {slot: image_id}} for the photos the dataset publishes."""
    out: dict[str, dict[str, str]] = {}
    for line in open(ds / "data" / "test_cases.jsonl", encoding="utf-8"):
        c = json.loads(line)
        if c["arm"] in SLOT_OF:
            out.setdefault(c["landmark_qid"], {})[SLOT_OF[c["arm"]]] = c["image_id"]
    return out


def read_check(path: Path, shipped: dict[str, dict[str, str]]) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "flagged" in data:
        n = sum(len(s) for s in shipped.values())
        if data.get("photos") != n:
            raise SystemExit(f"{path}: the PDF has {data.get('photos')} photos, the dataset ships {n}")
        return {"checked_by": data.get("checked_by", "A1"), "method": "fillable PDF", "source": data.get("source"),
                "photos": n, "flagged": sorted(data["flagged"]), "undecided": [],
                "note": "a PDF records ticks only; that every photo was looked at rests on the checker's statement"}
    if isinstance(data, dict) and data.get("format") == "photo-check":
        checks, by, when = data["checks"], data.get("annotator", "A1"), data.get("exported_at")
    elif isinstance(data, list):
        checks, by, when = {d["id"]: d.get("data", d) for d in data}, "A1", None
    elif isinstance(data, dict):
        checks, by, when = data, "A1", None
    else:
        raise SystemExit(f"{path}: unknown format")
    flagged, undecided, times = [], [], []
    for qid, slots in shipped.items():
        c = checks.get(qid) or {}
        if c.get("t"):
            times.append(c["t"])
        for slot, iid in slots.items():
            v = c.get(slot)
            if v is None:
                undecided.append(iid)
            elif v != "ok":
                flagged.append(f"{iid} ({v})")
    return {"checked_by": by, "method": "online page (every click saved)", "source": path.name,
            "photos": sum(len(s) for s in shipped.values()), "flagged": sorted(flagged), "undecided": sorted(undecided),
            "checked_at": max(times) if times else when}


def apply(check: dict, work: Path) -> dict:
    if check["undecided"]:
        raise SystemExit(f"{len(check['undecided'])} shipped photos have no decision, e.g. {check['undecided'][:3]}")
    if check["flagged"]:
        raise SystemExit("flagged photos change the dataset; record them as A1 decisions and rebuild:\n  "
                         + "\n  ".join(check["flagged"]))
    shipped = {iid for s in shipped_photos(work / "dataset").values() for iid in s.values()}
    merged_path = work / "review" / "merged.json"
    merged = json.loads(merged_path.read_text(encoding="utf-8"))
    merged["report"]["human_photo_check"] = {k: v for k, v in check.items() if k != "undecided"}
    merged_path.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    rows = [json.loads(line) for line in open(work / "images.jsonl", encoding="utf-8")]
    credited = 0
    for r in rows:
        if r["image_id"] in shipped and check["checked_by"] not in (r.get("pii_reviewer_ids") or []):
            r["pii_reviewer_ids"] = (r.get("pii_reviewer_ids") or []) + [check["checked_by"]]
            credited += 1
    with open(work / "images.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"photos": check["photos"], "flagged": 0, "reviewer_added_to": credited, "method": check["method"]}


def main() -> None:
    check_path, work = Path(sys.argv[1]), Path(sys.argv[2])
    check = read_check(check_path, shipped_photos(work / "dataset"))
    print(json.dumps(apply(check, work), indent=1))


if __name__ == "__main__":
    main()
