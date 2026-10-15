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


def _translation(c: dict) -> dict:
    """Template provenance per item: the q-v1 statuses apply only to q-v1; the extension templates (q-v2-*) were
    AI-drafted and locked before the run with no recorded review (templates_v2.yaml header)."""
    if c["prompt_version"] != "q-v1":
        return {"translation_method": "template drafted with AI coding assistant",
                "translation_review_status": "not reviewed by a native speaker (exploratory)" if c["lang"] == "rm"
                else "not reviewed (extension template)"}
    return {"translation_method": "template drafted with AI coding assistant" + ("" if c["lang"] == "fr" else "; back-translation check"),
            "translation_review_status": {"fr": "reviewed by French-speaking team members", "de": "back-translation checked",
                                          "it": "back-translation checked", "rm": "not reviewed by a native speaker (exploratory)"}[c["lang"]]}


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
                **_translation(c),
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
    from .gazetteer import build_gazetteer
    gazetteer = build_gazetteer(work, ds)
    removed_aliases = clean_place_aliases(ds)
    return {"test_cases": len(cases), "landmarks": len(lms), "images_shipped": len(shipped), "problems": problems[:20],
            "n_problems": len(problems), "responses_moved_to_excluded_items": pruned, "gazetteer": gazetteer,
            "place_aliases_removed": removed_aliases}


def clean_place_aliases(ds: Path) -> int:
    """Team-lead village rule (13 Oct): only the gold municipality counts as the place. A Wikidata "located in"
    label that is not a name of the current gold municipality (a city district "Kreis 1", a region "Surselva", a
    former municipality "Ardez") is removed from place_aliases and logged in metadata/removed_place_aliases.jsonl.
    BFS register names are always kept (a landmark on a border lists both municipalities). Runs after the questions
    are built, so item-validity checks (which use the aliases) are unchanged."""
    from ..grading.normalize import normalize, split_bilingual
    gz = json.loads((ds / "metadata" / "gazetteer.json").read_text(encoding="utf-8"))
    current = {}
    for m in gz["municipalities"]:
        if m["current"]:
            current.setdefault(m["bfs"], set()).update(m["names"])
    log_path = ds / "metadata" / "removed_place_aliases.jsonl"
    log = {(r["qid"], r["text"]): r for r in map(json.loads, open(log_path, encoding="utf-8"))} if log_path.exists() else {}
    path = ds / "data" / "landmarks.jsonl"
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    for lm in rows:
        names = current.get(int(lm["municipality_bfs"]), set())
        keep = []
        for a in lm["place_aliases"]:
            forms = {normalize(a["text"])} | {normalize(x) for x in split_bilingual(a["text"])}
            if a["source"] == "bfs:name" or forms & names:
                keep.append(a)
            else:
                log[(lm["qid"], a["text"])] = {"qid": lm["qid"], "municipality": lm["municipality_name"], "text": a["text"],
                                               "source": a["source"], "reason": "not a name of the current gold municipality"}
        lm["place_aliases"] = keep
        kept = {a["text"] for a in keep}
        lm["ambiguous_place_aliases"] = [a for a in lm.get("ambiguous_place_aliases", []) if a in kept]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for lm in rows:
            f.write(json.dumps(lm, ensure_ascii=False) + "\n")
    with open(log_path, "w", encoding="utf-8", newline="\n") as f:
        for r in sorted(log.values(), key=lambda r: (r["qid"], r["text"])):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(log)


def _read_rows(path: Path) -> list[tuple[dict, str]] | None:
    """(parsed row, raw line) pairs; newline="" keeps the file's own line endings (byte-for-byte copies)."""
    if not path.exists():
        return None
    with open(path, encoding="utf-8", newline="") as f:
        return [(json.loads(l), l if l.endswith("\n") else l + "\n") for l in f if l.strip()]


def prune_results(ds: Path, case_ids: set[str], removed_path: Path) -> dict[str, int]:
    """Responses/judgements of items no longer in the dataset move to metadata/excluded_items.jsonl, verbatim
    (full response and judgement rows) and with the reason; an item that comes back is restored from there.
    Idempotent: one record per (item_id, model). Scores in the results folders must be recomputed afterwards."""
    removed = {json.loads(l)["item_id"]: json.loads(l) for l in open(removed_path, encoding="utf-8")} \
        if removed_path.exists() else {}
    excl_path = ds / "metadata" / "excluded_items.jsonl"
    excluded = [json.loads(l) for l in open(excl_path, encoding="utf-8")] if excl_path.exists() else []
    index = {(e["item_id"], e.get("model")): e for e in excluded}
    moved: dict[str, int] = {}
    changed = False
    for rdir in sorted(p for p in (ds / "responses").glob("*") if p.is_dir()):
        resp, judg = _read_rows(rdir / "responses.jsonl"), _read_rows(rdir / "judgements.jsonl")
        if resp is None:
            continue
        models = {r.get("model") for r, _ in resp if r.get("model")}
        model = next(iter(models)) if len(models) == 1 else None
        jrows = {j["item_id"]: j for j, _ in judg or []}
        present = {r["item_id"] for r, _ in resp}
        n_out = 0
        for r, _ in resp:
            if r["item_id"] in case_ids:
                continue
            key = (r["item_id"], r.get("model"))
            info = removed.get(r["item_id"], {})
            rec = index.get(key) or {"item_id": r["item_id"], "model": r.get("model"),
                                     "question_text": info.get("question_text"), "response_text": r.get("response_text"),
                                     "reason": info.get("reason", "item not in the current dataset"),
                                     "decided_without_looking_at_answers": True}
            rec["response_row"] = r
            rec["judgement_row"] = jrows.get(r["item_id"], rec.get("judgement_row"))
            if key not in index:
                excluded.append(rec)
                index[key] = rec
            n_out += 1
        for iid, j in jrows.items():   # a judgement without a response row is recorded too, never dropped
            if iid not in case_ids and iid not in present:
                rec = index.get((iid, model))
                if rec is None:
                    rec = {"item_id": iid, "model": model, "question_text": removed.get(iid, {}).get("question_text"),
                           "response_text": None, "reason": removed.get(iid, {}).get("reason", "item not in the current dataset"),
                           "decided_without_looking_at_answers": True}
                    excluded.append(rec)
                    index[(iid, model)] = rec
                rec["judgement_row"] = j
                n_out += 1
        restore = [e for e in excluded if e["item_id"] in case_ids and e["item_id"] not in present
                   and e.get("response_row") and e.get("model") in (model, None)]
        kept_r = [raw for r, raw in resp if r["item_id"] in case_ids]
        kept_j = [raw for j, raw in judg or [] if j["item_id"] in case_ids]
        for e in restore:  # an item that comes back gets its original rows back
            kept_r.append(json.dumps(e["response_row"], ensure_ascii=False, sort_keys=True) + "\n")
            if e.get("judgement_row"):
                kept_j.append(json.dumps(e["judgement_row"], ensure_ascii=False, sort_keys=True) + "\n")
            excluded.remove(e)
            index.pop((e["item_id"], e.get("model")), None)
        if n_out or restore:
            changed = True
            for name, lines in (("responses.jsonl", kept_r), ("judgements.jsonl", kept_j)):
                if name == "judgements.jsonl" and judg is None:
                    continue
                with open(rdir / name, "w", encoding="utf-8", newline="") as f:
                    f.writelines(sorted(lines, key=lambda l: json.loads(l)["item_id"]))
        if n_out:
            moved[rdir.name] = n_out
        if restore:
            moved[rdir.name + ":restored"] = len(restore)
    if changed:
        with open(excl_path, "w", encoding="utf-8", newline="\n") as f:
            for e in sorted(excluded, key=lambda e: (e["item_id"], e.get("model") or "")):
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return moved
