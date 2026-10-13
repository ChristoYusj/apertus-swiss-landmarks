"""Merge the annotators' photo-screening files (screening_A1.json ...) into the image records.

Decision rules (docs/annotation_guidelines.md, Task P):
  privacy     exclude if ANY reviewer says exclude (cautious); keep needs >= 1 keep and no exclude
  2nd view    an alt photo is accepted if every reviewer who saw it said "good" (and privacy keep);
              at most one accepted alt per landmark (first in id order)
  low-info    an alt photo becomes a trap_lowinfo item only if >= 2 reviewers ticked it
  main photo  excluded main photo -> the landmark is dropped and reported (no silent swap)
Agreement on the overlap set (photos seen by all three) is reported with Fleiss' kappa.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ..metrics import fleiss_kappa


def merge_review(work: Path, files: list[Path]) -> dict:
    images = [json.loads(l) for l in open(work / "images.jsonl", encoding="utf-8")]
    assignment = json.loads((work / "review" / "assignment.json").read_text(encoding="utf-8"))
    who = {x["id"]: x["who"] for x in assignment["items"]}
    decisions: dict[str, dict] = {}
    for f in files:
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        decisions[d["annotator"]] = d["decisions"]
    missing = {a: [i for i, ws in who.items() if a in ws and a in decisions and not decisions[a].get(i, {}).get("privacy")]
               for a in decisions}
    by_img = {im["image_id"]: im for im in images}
    alt_accepted: dict[str, str] = {}
    lowinfo: dict[str, str] = {}
    dropped_landmarks = []
    stats = Counter()
    for iid, im in sorted(by_img.items()):
        votes = [(a, decisions[a].get(iid, {})) for a in who.get(iid, []) if a in decisions]
        priv = [v.get("privacy") for _, v in votes if v.get("privacy")]
        if not priv:
            im["pii_decision"] = "pending"
            stats["unreviewed"] += 1
            continue
        excl = "exclude" in priv
        im["pii_decision"] = "exclude" if excl else "keep"
        im["pii_reason"] = "flagged by reviewer" if excl else None
        im["pii_reviewer_ids"] = sorted(a for a, v in votes if v.get("privacy"))
        stats[f"privacy_{im['pii_decision']}"] += 1
        if im["role"] == "main_p18" and excl:
            dropped_landmarks.append(im["landmark_qid"])
        if im["role"] == "alt" and not excl:
            views = [v.get("view") for _, v in votes if v.get("view")]
            if views and all(v == "good" for v in views) and im["landmark_qid"] not in alt_accepted:
                alt_accepted[im["landmark_qid"]] = iid
            if sum(bool(v.get("lowinfo")) for _, v in votes) >= 2 and im["landmark_qid"] not in lowinfo:
                lowinfo[im["landmark_qid"]] = iid
    # agreement on the overlap set
    overlap = [i for i, ws in who.items() if len(ws) == 3 and all(decisions.get(a, {}).get(i, {}).get("privacy") for a in ws)]
    table = [[decisions[a][i]["privacy"] for a in ("A1", "A2", "A3")] for i in overlap] if len(decisions) == 3 else []
    with open(work / "images.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for im in images:
            f.write(json.dumps(im, ensure_ascii=False) + "\n")
    report = {"annotators": sorted(decisions), "missing_per_annotator": {a: len(v) for a, v in missing.items()},
              "stats": dict(stats), "alt_accepted": len(alt_accepted), "lowinfo_traps": len(lowinfo),
              "dropped_landmarks_main_photo_excluded": dropped_landmarks,
              "overlap_items_complete": len(overlap),
              "privacy_fleiss_kappa_overlap": fleiss_kappa(table) if table else None,
              "privacy_raw_agreement_overlap": (sum(len(set(r)) == 1 for r in table) / len(table)) if table else None}
    (work / "review" / "merged.json").write_text(json.dumps({"report": report, "alt_accepted": alt_accepted,
                                                             "lowinfo": lowinfo}, indent=1), encoding="utf-8")
    return report
