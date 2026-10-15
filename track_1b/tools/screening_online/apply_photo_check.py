"""Merge a check of every published photo into the screening and the dataset.

  python apply_photo_check.py decisions <check.json> <work dir>   1. flagged photos -> work/review/a1_decisions.json
  (then: hermes_to_check.py, landmarks-eval combine-screening, landmarks-eval merge-review, as in README.md)
  python apply_photo_check.py record <check.json> <work dir>      2. prune the dataset, record the check

<check.json> is one of:
  - a human check: read_photo_check_pdf.py's output ({"checked_by", "source", "photos", "flagged"}; a PDF records
    ticks only), or the online page's download (photo_check.html, format "photo-check") or its database documents
    (collection `pcheck`); an online check with a shipped photo left undecided is refused;
  - an AI review whose flags the lead accepted (format "ai-photo-review": reviewer "ai:<name>", accepted_by,
    photos, flagged, ai_notes). It is recorded as an AI review, never as a human check, and credits no person.

A flagged photo becomes a decision in a1_decisions.json ("exclude"; marked "by": "ai:<name>" for an AI review), so the
documented screening merge handles it: a flagged main photo removes its landmark, a flagged 2nd view or too-generic
photo removes only that photo (never replaced). `record` then removes exactly the items of removed photos and
landmarks from the dataset (every other item is left byte for byte, so the stored answers still match their
questions), logs each with its reason in work/removed_items.jsonl, moves dropped landmarks to
metadata/excluded_landmarks.jsonl and stores the check in the screening report (`human_photo_check`, with the checker
added to the reviewers of every photo still shipped; or `ai_photo_review`). Then: `landmarks-eval assemble` (moves
the removed items' answers to metadata/excluded_items.jsonl), regenerate the card, re-score every model, verify.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SLOT_OF = {"photo_main": "main", "photo_alt": "alt", "trap_lowinfo": "low"}
PRIVACY = "flagged as a privacy problem in the human photo check of every shipped photo (A1, 15 Oct)"


def shipped_photos(ds: Path) -> dict[str, dict[str, str]]:
    """{QID: {slot: image_id}} for the photos the dataset publishes."""
    out: dict[str, dict[str, str]] = {}
    for line in open(ds / "data" / "test_cases.jsonl", encoding="utf-8"):
        c = json.loads(line)
        if c["arm"] in SLOT_OF:
            out.setdefault(c["landmark_qid"], {})[SLOT_OF[c["arm"]]] = c["image_id"]
    return out


def is_human(check: dict) -> bool:
    return not str(check["checked_by"]).startswith("ai:")


def read_check(path: Path, shipped: dict[str, dict[str, str]]) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    n = sum(len(s) for s in shipped.values())
    ids = {i for s in shipped.values() for i in s.values()}
    if isinstance(data, dict) and ("flagged" in data):
        if data.get("photos") != n:
            raise SystemExit(f"{path}: the check has {data.get('photos')} photos, the dataset ships {n}")
        unknown = sorted(set(data["flagged"]) - ids)
        if unknown:
            raise SystemExit(f"{path}: flagged photos not in the dataset: {unknown}")
        if data.get("format") == "ai-photo-review":
            if not str(data.get("reviewer", "")).startswith("ai:"):
                raise SystemExit(f"{path}: an AI review must name its reviewer as ai:<name>")
            return {"checked_by": data["reviewer"], "accepted_by": data.get("accepted_by"), "tool": data.get("tool"),
                    "method": "AI review of every shipped photo; the team lead accepted its flags",
                    "source": path.name, "photos": n, "flagged": sorted(data["flagged"]), "undecided": [],
                    "ai_notes": data.get("ai_notes", {})}
        return {"checked_by": data.get("checked_by", "A1"), "method": "fillable PDF", "source": data.get("source"),
                "photos": n, "flagged": sorted(data["flagged"]), "undecided": [], "checked_at": data.get("saved_at"),
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
                flagged.append(iid)
    return {"checked_by": by, "method": "online page (every click saved)", "source": path.name, "photos": n,
            "flagged": sorted(flagged), "undecided": sorted(undecided), "checked_at": max(times) if times else when}


def _reason(check: dict, iid: str) -> str:
    if is_human(check):
        return PRIVACY
    note = (check.get("ai_notes") or {}).get(iid)
    return (f"flagged in a third AI review ({check['checked_by']}), accepted by the team lead"
            + (f" (AI's note: {note})" if note else ""))


def decisions(check: dict, work: Path) -> dict:
    """Write the flagged photos as decisions that override the second AI reviewer (hermes_to_check.py)."""
    if check["undecided"]:
        raise SystemExit(f"{len(check['undecided'])} shipped photos have no decision, e.g. {check['undecided'][:3]}")
    where = {iid: (qid, slot) for qid, s in shipped_photos(work / "dataset").items() for slot, iid in s.items()}
    path = work / "review" / "a1_decisions.json"
    a1 = json.loads(path.read_text(encoding="utf-8"))
    # the screening's own edge-case count, before the check's decisions are merged into it
    stats = json.loads((work / "review" / "merged.json").read_text(encoding="utf-8"))["report"].get("stats", {})
    a1.setdefault("edge_case_landmarks_before_photo_check", stats.get("landmarks_with_human_decision", 0))
    for iid in check["flagged"]:
        qid, slot = where[iid]
        d = a1["decisions"].setdefault(qid, {})
        d[slot] = "exclude"
        if slot == "main":
            d["reason"] = f"main photo {_reason(check, iid)}"
        if is_human(check):
            d["decided_at"] = check.get("checked_at") or "2026-10-15"
        else:
            d["by"] = f"{check['checked_by']} (flags accepted by {check.get('accepted_by') or 'A1'})"
    a1["note"] = ("Decisions the lead (A1) made directly (in chat), and flags of a third AI review the lead accepted "
                  "(marked `by`; not credited to a person). They override the second AI reviewer for these photos.")
    path.write_text(json.dumps(a1, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return {"flagged": len(check["flagged"]), "landmarks_with_decisions": len(a1["decisions"])}


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in open(path, encoding="utf-8")] if path.exists() else []


def _write(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def record(check: dict, work: Path) -> dict:
    """After merge-review: drop exactly the items of removed photos/landmarks and record the check."""
    if check["undecided"]:
        raise SystemExit(f"{len(check['undecided'])} shipped photos have no decision")
    ds = work / "dataset"
    images = {r["image_id"]: r for r in _rows(work / "images.jsonl")}
    merged_path = work / "review" / "merged.json"
    merged = json.loads(merged_path.read_text(encoding="utf-8"))
    dropped = merged["report"]["dropped_landmarks"]
    still = [i for i in check["flagged"] if images[i]["pii_decision"] == "keep"]
    if still:
        raise SystemExit(f"run the screening merge first: flagged photos still cleared: {still}")
    cases = _rows(ds / "data" / "test_cases.jsonl")
    keep, gone = [], []
    for c in cases:
        if c["landmark_qid"] in dropped:
            gone.append((c, f"landmark removed in the photo screening: {dropped[c['landmark_qid']]}"))
        elif c.get("image_id") and images[c["image_id"]]["pii_decision"] != "keep":
            gone.append((c, f"photo {c['image_id']} {_reason(check, c['image_id'])}"))
        else:
            keep.append(c)
    removed = {r["item_id"]: r for r in _rows(work / "removed_items.jsonl")}
    for c, why in gone:
        removed[c["item_id"]] = {"item_id": c["item_id"], "landmark_qid": c["landmark_qid"],
                                 "question_text": c["question_text"], "reason": why}
    _write(work / "removed_items.jsonl", sorted(removed.values(), key=lambda r: r["item_id"]))
    _write(ds / "data" / "test_cases.jsonl", keep)
    lms = _rows(ds / "data" / "landmarks.jsonl")
    out_lms = [lm for lm in lms if lm["qid"] in dropped]
    _write(ds / "data" / "landmarks.jsonl", [lm for lm in lms if lm["qid"] not in dropped])
    excl = {r["qid"]: r for r in _rows(ds / "metadata" / "excluded_landmarks.jsonl")}
    for lm in out_lms:
        excl[lm["qid"]] = {**lm, "excluded_reason": dropped[lm["qid"]]}
    _write(ds / "metadata" / "excluded_landmarks.jsonl", list(excl.values()))
    shipped = {c["image_id"] for c in keep if c.get("image_id")}
    if is_human(check):          # a person who checked every shipped photo is credited on each; an AI review is not
        for iid in shipped:
            rev = images[iid].get("pii_reviewer_ids") or []
            if check["checked_by"] not in rev:
                images[iid]["pii_reviewer_ids"] = rev + [check["checked_by"]]
        _write(work / "images.jsonl", list(images.values()))
    a1 = json.loads((work / "review" / "a1_decisions.json").read_text(encoding="utf-8"))
    removed_lms = sorted({lm["qid"] for lm in out_lms})
    merged["report"]["human_photo_check" if is_human(check) else "ai_photo_review"] = {
        **{k: v for k, v in check.items() if k != "undecided"},
        "edge_case_landmarks_before": a1.get("edge_case_landmarks_before_photo_check"),
        "removed_landmarks": removed_lms,
        "removed_photos": sorted(i for i in check["flagged"] if i.split("-")[0] not in removed_lms)}
    merged_path.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return {"photos_checked": check["photos"], "flagged": len(check["flagged"]), "landmarks_removed": len(out_lms),
            "items_removed": len(gone), "items_left": len(keep), "photos_still_shipped": len(shipped),
            "recorded_as": "human_photo_check" if is_human(check) else "ai_photo_review"}


def main() -> None:
    cmd, check_path, work = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    check = read_check(check_path, shipped_photos(work / "dataset"))
    if cmd == "decisions":
        print(json.dumps(decisions(check, work), indent=1))
    elif cmd == "record":
        print(json.dumps(record(check, work), indent=1))
    else:
        raise SystemExit("usage: apply_photo_check.py decisions|record <check.json> <work dir>")


if __name__ == "__main__":
    main()
