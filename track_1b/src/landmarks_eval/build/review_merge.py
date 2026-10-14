"""Merge the team's photo-screening file (screening_team.json) into the image records.

The team screens together on one computer and records one joint decision per landmark
(docs/annotation_guidelines.md, Task P, guideline v2-team). Decision rules:
  main photo  "ok"       -> privacy keep
              "exclude"  -> privacy exclude; the landmark is dropped and reported (no silent swap)
              "wrong"    -> the photo does not show the landmark; the landmark is dropped and reported
  2nd view    the photo picked as "2nd view" -> privacy keep, becomes the photo_alt image
  low-info    the photo marked "Too generic" -> privacy keep, becomes the trap_lowinfo image
  other alts  not picked -> stay "pending" and are never shipped
A landmark without a decision stays pending (reported), so a partial file can be merged safely.

Protocol v3-ai-assisted (14 Oct, before any team decision existed): an AI screens every photo and a second AI pass
re-checks every photo it would ship; annotator A1 then checks every published photo (tools/screening_online/check.html).
`combine_ai_check` turns the AI decisions + A1's checks into the same decision file; a photo is shipped only when A1
accepted it, and the file names both reviewers.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

REVIEWER = "team"


def merge_review(work: Path, files: list[Path]) -> dict:
    if len(files) != 1:
        raise SystemExit("merge-review takes exactly one file: screening_team.json")
    sub = json.loads(Path(files[0]).read_text(encoding="utf-8"))
    if sub.get("format") != "team-consensus":
        raise SystemExit(f"{files[0]}: not a team screening file (format={sub.get('format')!r})")
    decisions: dict[str, dict] = sub["decisions"]
    reviewers = list(sub.get("reviewers") or [REVIEWER])
    how = "AI screening checked by A1" if sub.get("guideline_version") == "v3-ai-assisted" else "team screening"
    images =[json.loads(l) for l in open(work / "images.jsonl", encoding="utf-8")]
    by_lm: dict[str, dict] = {}
    for im in images:
        by_lm.setdefault(im["landmark_qid"], {"main": None, "alts": {}})
        if im["role"] == "main_p18":
            by_lm[im["landmark_qid"]]["main"] = im
        else:
            by_lm[im["landmark_qid"]]["alts"][im["image_id"]] = im
    unknown = sorted(set(decisions) - set(by_lm))
    if unknown:
        raise SystemExit(f"decisions for unknown landmarks: {unknown[:5]}")
    for im in images:  # merging is idempotent: start from a clean slate every time
        im.update(pii_decision="pending", pii_reason=None, pii_reviewer_ids=[])
    alt_accepted: dict[str, str] = {}
    lowinfo: dict[str, str] = {}
    dropped: dict[str, str] = {}
    stats = Counter()
    for qid, g in sorted(by_lm.items()):
        d = decisions.get(qid) or {}
        main = g["main"]
        if main is None:
            stats["landmarks_without_main_photo"] += 1
            continue
        if d.get("main") not in ("ok", "exclude", "wrong"):
            stats["landmarks_pending"] += 1
            continue
        if d.get("main_id") and d["main_id"] != main["image_id"]:
            raise SystemExit(f"{qid}: the decision was made on photo {d['main_id']}, but the main photo is {main['image_id']}")
        stats[f"main_{d['main']}"] += 1
        if d["main"] == "exclude":
            main.update(pii_decision="exclude", pii_reason=f"recognisable person or private detail ({how})",
                        pii_reviewer_ids=reviewers)
            dropped[qid] = "main photo excluded for privacy"
            continue
        main.update(pii_decision="keep", pii_reviewer_ids=reviewers)
        if d["main"] == "wrong":
            dropped[qid] = "main photo does not show the landmark"
            continue
        if g["alts"] and not d.get("alt"):
            stats["alt_choice_pending"] += 1
        for field, target in (("alt", alt_accepted), ("low", lowinfo)):
            iid = d.get(field)
            if not iid or iid == "none":
                continue
            if iid not in g["alts"]:
                raise SystemExit(f"{qid}: {field}={iid} is not one of this landmark's other photos")
            g["alts"][iid].update(pii_decision="keep", pii_reviewer_ids=reviewers)
            target[qid] = iid
        if alt_accepted.get(qid) and alt_accepted.get(qid) == lowinfo.get(qid):
            raise SystemExit(f"{qid}: the same photo is both the 2nd view and 'too generic'")
    with open(work / "images.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for im in images:
            f.write(json.dumps(im, ensure_ascii=False) + "\n")
    report = {"source_file": Path(files[0]).name, "guideline_version": sub.get("guideline_version"),
              "exported_at": sub.get("exported_at"), "landmarks": len(by_lm), "stats": dict(stats),
              "alt_accepted": len(alt_accepted), "lowinfo_traps": len(lowinfo),
              "dropped_landmarks": dropped, "complete": stats["landmarks_pending"] == 0 and stats["alt_choice_pending"] == 0}
    (work / "review").mkdir(exist_ok=True)
    (work / "review" / "merged.json").write_text(json.dumps({"report": report, "alt_accepted": alt_accepted,
                                                             "lowinfo": lowinfo}, indent=1), encoding="utf-8")
    return report


AI_REVIEWER = "ai:claude-opus-5-5"


def combine_ai_check(ai: dict, check: dict) -> dict:
    """AI screening (format ai-screening) + A1's check (format screening-check) -> a decision file for merge_review.

    A1's verdict wins: the main photo is kept only if A1 marked it OK; a 2nd view or too-generic photo is shipped
    only if A1 marked it OK, otherwise it becomes "none" (no silent replacement). A landmark A1 did not check stays
    pending, so the privacy gate (verify V7) keeps failing until every published photo was seen by a person.
    """
    if ai.get("format") != "ai-screening" or check.get("format") != "screening-check":
        raise SystemExit("combine-screening needs an ai-screening file and a screening-check file")
    decisions, stats = {}, Counter()
    for qid, d in sorted(ai["decisions"].items()):
        c = check["checks"].get(qid) or {}
        if c.get("main") not in ("ok", "exclude", "wrong"):
            stats["unchecked"] += 1
            continue
        out = {"main": c["main"], "main_id": d["main_id"]}
        stats["main_" + ("agree" if c["main"] == d["main"] else f"{d['main']}_to_{c['main']}")] += 1
        if c["main"] == "ok":
            for slot in ("alt", "low"):
                pick = d.get(slot) or "none"
                if pick == "none":
                    if slot == "alt":
                        out["alt"] = "none"
                    continue
                if c.get(slot) not in ("ok", "exclude", "reject"):
                    stats[f"{slot}_unchecked"] += 1
                    continue
                stats[f"{slot}_{c[slot]}"] += 1
                if c[slot] == "ok":
                    out[slot] = pick
                elif slot == "alt":
                    out["alt"] = "none"
        decisions[qid] = out
    return {"format": "team-consensus", "annotator": "ai+A1", "guideline_version": "v3-ai-assisted",
            "reviewers": [AI_REVIEWER, "A1"], "ai_model": ai.get("model"), "check_exported_at": check.get("exported_at"),
            "check_stats": dict(sorted(stats.items())), "decisions": decisions}
