"""Assemble the publishable dataset folder (work/dataset/) in the Hugging Face layout.

  data/test_cases.jsonl        evaluation set (one row per question)
  data/landmarks.jsonl         answer keys, one row per landmark (gold from Wikidata CC0 + BFS)
  images/<image_id>.jpg        500 px re-encodes, metadata stripped
  metadata/images.jsonl        per-image licence, author, TASL attribution, hashes, privacy review
  metadata/item_metadata.jsonl per-test-case licences per modality + design covariates
  metadata/selection_report.json, images_report.json, questions_report.json, review.json
  responses/<model>/responses.jsonl, judgements.jsonl   (added after the evaluation run)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..schema import ImageRecord, Landmark, TestCase
from .questions import label_with_lang


def assemble(work: Path) -> dict:
    ds = work / "dataset"
    (ds / "images").mkdir(parents=True, exist_ok=True)
    (ds / "metadata").mkdir(parents=True, exist_ok=True)
    cases = [json.loads(l) for l in open(ds / "data" / "test_cases.jsonl", encoding="utf-8")]
    lms = {json.loads(l)["qid"]: json.loads(l) for l in open(ds / "data" / "landmarks.jsonl", encoding="utf-8")}
    images = {json.loads(l)["image_id"]: json.loads(l) for l in open(work / "images.jsonl", encoding="utf-8")}
    used = {c["image_id"] for c in cases if c.get("image_id")}
    problems = []
    for c in cases:
        TestCase.model_validate(c)
        if c["landmark_qid"] not in lms:
            problems.append(f"{c['item_id']}: landmark missing")
        if c.get("image_id"):
            im = images.get(c["image_id"])
            if im is None:
                problems.append(f"{c['item_id']}: image record missing")
            elif im["pii_decision"] != "keep":
                problems.append(f"{c['item_id']}: image {c['image_id']} not cleared ({im['pii_decision']})")
    for lm in lms.values():
        Landmark.model_validate(lm)
    for old in (ds / "images").glob("*.jpg"):
        if old.stem not in used:
            old.unlink()
    shipped = []
    for iid in sorted(used):
        im = images[iid]
        ImageRecord.model_validate(im)
        shutil.copy2(work / "images" / f"{iid}.jpg", ds / "images" / f"{iid}.jpg")
        shipped.append(im)
    with open(ds / "metadata" / "images.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for im in shipped:
            f.write(json.dumps(im, ensure_ascii=False) + "\n")
    with open(ds / "metadata" / "item_metadata.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for c in cases:
            lm = lms[c["landmark_qid"]]
            im = images.get(c.get("image_id") or "", {})
            f.write(json.dumps({
                "item_id": c["item_id"],
                "question_text_license": "CDLA-Permissive-2.0",
                "gold_license": "CC0-1.0", "gold_source": f"Wikidata {lm['qid']} (P571, P131, labels), BFS municipality register 2026-10-01",
                "image_license_spdx": im.get("license_spdx"), "image_attribution_text": im.get("attribution_text"),
                "response_license": "CDLA-Permissive-2.0",
                "translation_method": "template drafted with AI coding assistant" + ("" if c["lang"] == "fr" else "; back-translation check"),
                "translation_review_status": {"fr": "reviewed by French-speaking team members", "de": "back-translation checked",
                                              "it": "back-translation checked", "rm": "not reviewed by a native speaker (exploratory)"}[c["lang"]],
                "fame_tier": lm["fame_tier"], "language_region": lm["language_region"], "type_group": lm["type_group"],
                "heritage_class": lm["heritage_class"], "arm": c["arm"], "lang": c["lang"],
                "post_cutoff_image": im.get("post_cutoff"),
                # text-only questions show a label; when the landmark has none in the question's language a
                # fallback label is shown (mostly English in FR questions) -> covariate for a sensitivity analysis
                "shown_name_lang": label_with_lang(lm, c["lang"])[1] if c["arm"] == "text_only" else None,
            }, ensure_ascii=False) + "\n")
    for name in ("selection_report.json", "images_report.json", "questions_report.json"):
        if (work / name).exists():
            shutil.copy2(work / name, ds / "metadata" / name)
    if (work / "review" / "merged.json").exists():
        shutil.copy2(work / "review" / "merged.json", ds / "metadata" / "review.json")
    pruned = prune_results(ds, {c["item_id"] for c in cases}, work / "removed_items.jsonl")
    return {"test_cases": len(cases), "landmarks": len(lms), "images_shipped": len(shipped), "problems": problems[:20],
            "n_problems": len(problems), "responses_moved_to_excluded_items": pruned}


def prune_results(ds: Path, case_ids: set[str], removed_path: Path) -> dict[str, int]:
    """Responses/judgements of items no longer in the dataset move to metadata/excluded_items.jsonl (with the
    reason); nothing is deleted silently. Scores in those results folders must be recomputed afterwards."""
    removed = {json.loads(l)["item_id"]: json.loads(l) for l in open(removed_path, encoding="utf-8")} \
        if removed_path.exists() else {}
    excl_path = ds / "metadata" / "excluded_items.jsonl"
    excluded = [json.loads(l) for l in open(excl_path, encoding="utf-8")] if excl_path.exists() else []
    moved: dict[str, int] = {}
    for rdir in sorted(p for p in (ds / "responses").glob("*") if p.is_dir()):
        lines = {n: [l for l in open(rdir / n, encoding="utf-8") if l.strip()] if (rdir / n).exists() else None
                 for n in ("responses.jsonl", "judgements.jsonl")}
        rows = {n: [(json.loads(l), l) for l in ls] if ls is not None else None for n, ls in lines.items()}
        gone = [r for r, _ in rows["responses.jsonl"] or [] if r["item_id"] not in case_ids]
        if not gone and not any(j["item_id"] not in case_ids for j, _ in rows["judgements.jsonl"] or []):
            continue
        for r in gone:
            info = removed.get(r["item_id"], {})
            excluded.append({"item_id": r["item_id"], "model": r.get("model"), "question_text": info.get("question_text"),
                             "response_text": r.get("response_text"),
                             "reason": info.get("reason", "item not in the current dataset"),
                             "decided_without_looking_at_answers": True})
        for n, rs in rows.items():
            if rs is None:
                continue
            with open(rdir / n, "w", encoding="utf-8", newline="\n") as f:
                for r, raw in rs:  # kept rows are copied byte for byte
                    if r["item_id"] in case_ids:
                        f.write(raw if raw.endswith("\n") else raw + "\n")
        moved[rdir.name] = len(gone)
    if moved:
        with open(excl_path, "w", encoding="utf-8", newline="\n") as f:
            for e in excluded:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return moved
