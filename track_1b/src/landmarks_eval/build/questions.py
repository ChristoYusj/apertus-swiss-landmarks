"""Step 4: generate the test cases from the frozen templates (pre-registered design).

Arms and languages (every landmark gets the same language set within an arm):
  photo_main   Q1 name, Q2 place, Q3 year (if a gold year exists)        x fr de it rm
  text_only    Q2 place (only if no shown name reveals the town and the name is distinctive),
               Q3 year (with the town given, since only the date is asked)  x fr de
  photo_alt    Q1-Q3 on a second photo of the same object                    x fr de   (after the photo screening)
  trap_premise Q1 name, the question asserts the town of a real look-alike  x fr de
  trap_lowinfo Q1 name on a low-information photo                           x fr de   (after the photo screening)
The plan says "human-accepted" / "human-confirmed" photos; as run, the screening was AI-led (review_merge.py).
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

import yaml

from ..grading.normalize import distinctive, normalize, split_bilingual
from ..schema import TestCase
from .wikidata_api import details

TEMPLATES = Path(__file__).resolve().parents[1] / "prompts" / "templates.yaml"
PREMISE_N = 25
SEED = 20261014


def _templates() -> tuple[str, dict]:
    t = yaml.safe_load(TEMPLATES.read_text(encoding="utf-8"))
    return t["prompt_version"], t["templates"]


def _label(lm: dict, lang: str) -> str:
    return label_with_lang(lm, lang)[0]


def label_with_lang(lm: dict, lang: str) -> tuple[str, str]:
    """The name shown in a question in `lang`, and the language of that label (a fallback when no own label)."""
    for l in (lang, "en", "de", "fr", "it", "rm"):
        if lm["labels"].get(l):
            return lm["labels"][l], l
    a = lm["name_aliases"][0]
    return a["text"], a["lang"] or "und"


YEAR_LEAK_RULE = ("item-validity rule: the name shown in a text-only year question must not contain a year "
                  "(it gives the answer away); decided from the question text only")
TEXT_ONLY_RULE = ("item-validity rule: the name shown in a text-only place question must be distinctive in both "
                  "FR and DE (generic-word list audited 13 Oct); decided from the question text only")


def _public(lm: dict) -> dict:
    pub = {k: v for k, v in lm.items() if not k.startswith("_") and k != "main_image_id"}
    pub["lookalike_siblings"] = [{"qid": q, "municipality": t} for q, t in lm.get("_siblings") or []]
    return pub


def _case(lm, arm, qtype, lang, tid, pv, text, image_id, expected="answer", **extra) -> dict:
    c = {"item_id": f"{lm['qid']}-{arm}-{qtype}-{lang}", "landmark_qid": lm["qid"], "arm": arm,
         "question_type": qtype, "lang": lang, "template_id": tid, "prompt_version": pv,
         "question_text": text, "image_id": image_id, "expected_behavior": expected, **extra}
    TestCase.model_validate(c)
    return c


def town_for(lm: dict, lang: str) -> str:
    """Municipality name to show in a question, preferring a label in the question's language."""
    for a in lm["place_aliases"]:
        if a["lang"] == lang and a["source"] == "wikidata:place_label":
            return a["text"]
    return split_bilingual(lm["municipality_name"])[-1] if "(" in lm["municipality_name"] else lm["municipality_name"]


def build_questions(work: Path, alt_accepted: dict[str, str] | None = None,
                    lowinfo: dict[str, str] | None = None, dropped: dict[str, str] | None = None) -> dict:
    """`dropped` = landmarks removed in the photo screening ({qid: reason}); they get no items at all."""
    pv, T = _templates()
    dropped = dropped or {}
    all_lms = [json.loads(l) for l in open(work / "landmarks_final.jsonl", encoding="utf-8")]
    # (re)compute name distinctiveness with the current rule (single source of truth: normalize.distinctive)
    for lm in all_lms:
        town_tokens = {t for a in lm["place_aliases"] for t in normalize(a["text"]).split()}
        for a in lm["name_aliases"]:
            a["distinctive"] = distinctive(a["text"], town_tokens)
        lm["name_needs_place"] = not any(a["distinctive"] for a in lm["name_aliases"])
    with open(work / "landmarks_final.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for lm in all_lms:
            f.write(json.dumps(lm, ensure_ascii=False) + "\n")
    lms = [lm for lm in all_lms if lm["qid"] not in dropped]
    cases = []
    for lm in lms:
        img = lm["main_image_id"]
        for lang in ("fr", "de", "it", "rm"):
            cases.append(_case(lm, "photo_main", "name", lang, "name.photo", pv, T[lang]["name.photo"], img))
            cases.append(_case(lm, "photo_main", "place", lang, "place.photo", pv, T[lang]["place.photo"], img))
            if lm["gold_year"] is not None:
                cases.append(_case(lm, "photo_main", "year", lang, "year.photo", pv, T[lang]["year.photo"], img))
        towns = {normalize(a["text"]) for a in lm["place_aliases"]}
        town_tokens = {t for n in towns for t in n.split()}
        shown = {lang: _label(lm, lang) for lang in ("fr", "de")}
        leaks = any(f" {t} " in f" {normalize(n)} " for n in shown.values() for t in towns if t)
        # the NAME SHOWN in the question must identify the object, otherwise "where is it?" is unanswerable
        shown_ok = all(distinctive(n, town_tokens) for n in shown.values())
        # a shown name that contains a year ("Rathausbrunnen (1833)") gives the answer to the year question away
        year_ok = not any(re.search(r"\d{3,4}", n) for n in shown.values())
        for lang in ("fr", "de"):
            if not leaks and shown_ok:
                cases.append(_case(lm, "text_only", "place", lang, "place.text", pv,
                                   T[lang]["place.text"].format(name=shown[lang]), None))
            if lm["gold_year"] is not None and year_ok:
                cases.append(_case(lm, "text_only", "year", lang, "year.text", pv,
                                   T[lang]["year.text"].format(name=shown[lang], town=town_for(lm, lang)), None))
        if alt_accepted and lm["qid"] in alt_accepted:
            for lang in ("fr", "de"):
                for q in ("name", "place") + (("year",) if lm["gold_year"] is not None else ()):
                    cases.append(_case(lm, "photo_alt", q, lang, f"{q}.photo", pv, T[lang][f"{q}.photo"],
                                       alt_accepted[lm["qid"]]))
        if lowinfo and lm["qid"] in lowinfo:
            for lang in ("fr", "de"):
                cases.append(_case(lm, "trap_lowinfo", "name", lang, "name.photo", pv, T[lang]["name.photo"],
                                   lowinfo[lm["qid"]], expected="answer_or_abstain", trap_type="low_information_photo"))

    # premise traps: the question asserts the town of a real look-alike in another municipality
    rng = random.Random(SEED)
    # drawn from ALL landmarks, then screened-out ones skipped: a dropped landmark must not reshuffle the others
    with_sib = [lm for lm in all_lms if lm.get("_siblings")]
    rng.shuffle(with_sib)
    by_region: dict[str, list] = {}
    for lm in with_sib:
        by_region.setdefault(lm["language_region"], []).append(lm)
    picked = []
    while len(picked) < PREMISE_N and any(by_region.values()):
        for reg in sorted(by_region):
            if by_region[reg] and len(picked) < PREMISE_N:
                picked.append(by_region[reg].pop(0))
    sib_qids = sorted({lm["_siblings"][0][0] for lm in picked})
    _, sib_places = details(sib_qids, work)
    for lm in picked:
        if lm["qid"] in dropped:
            continue
        sib_qid, sib_town = lm["_siblings"][0]
        own = {normalize(a["text"]) for a in lm["place_aliases"]}
        false_aliases = sorted({x for t, l, _q, _b in sib_places.get(sib_qid, []) if l in ("en", "fr", "de", "it", "rm")
                                for x in split_bilingual(t)} | set(split_bilingual(sib_town)))
        false_aliases = [a for a in false_aliases if normalize(a) not in own]
        if not false_aliases:
            continue
        for lang in ("fr", "de"):
            shown_town = next((t for t, l, _q, _b in sib_places.get(sib_qid, []) if l == lang),
                              split_bilingual(sib_town)[-1])
            if normalize(shown_town) in own:
                continue
            cases.append(_case(lm, "trap_premise", "name", lang, "name.premise", pv,
                               T[lang]["name.premise"].format(false_town=shown_town), lm["main_image_id"],
                               expected="reject_premise", trap_type="premise_lookalike_town",
                               false_premise_claim=shown_town, false_premise_aliases=false_aliases,
                               paired_control_item_id=f"{lm['qid']}-photo_main-name-{lang}",
                               confusable_with=[sib_qid]))

    ids = [c["item_id"] for c in cases]
    assert len(ids) == len(set(ids)), "duplicate item ids"
    # every landmark has the same language set within each arm (no language-vs-landmark confound)
    langsets: dict[tuple, set] = {}
    for c in cases:
        langsets.setdefault((c["landmark_qid"], c["arm"], c["question_type"]), set()).add(c["lang"])
    expected_langs = {"photo_main": {"fr", "de", "it", "rm"}}
    bad = [k for k, v in langsets.items() if k[1] in expected_langs and v != expected_langs[k[1]]]
    assert not bad, f"language set mismatch: {bad[:3]}"

    out = work / "dataset" / "data"
    out.mkdir(parents=True, exist_ok=True)
    # items of the previous build that are no longer generated: logged with the reason (assemble() moves
    # any responses they already have to metadata/excluded_items.jsonl instead of silently deleting them)
    new_ids = set(ids)
    removed_path = work / "removed_items.jsonl"
    removed = {json.loads(l)["item_id"]: json.loads(l) for l in open(removed_path, encoding="utf-8")} \
        if removed_path.exists() else {}
    if (out / "test_cases.jsonl").exists():
        for l in open(out / "test_cases.jsonl", encoding="utf-8"):
            c = json.loads(l)
            if c["item_id"] not in new_ids and c["item_id"] not in removed:
                why = dropped.get(c["landmark_qid"])
                removed[c["item_id"]] = {"item_id": c["item_id"], "landmark_qid": c["landmark_qid"],
                                         "question_text": c["question_text"],
                                         "reason": f"landmark removed in the photo screening: {why}" if why
                                         else YEAR_LEAK_RULE if c["arm"] == "text_only" and c["question_type"] == "year"
                                         else TEXT_ONLY_RULE if c["arm"] == "text_only"
                                         else "no longer generated by the current builder rules"}
    for i in new_ids & set(removed):  # an item that comes back is not removed any more
        del removed[i]
    with open(removed_path, "w", encoding="utf-8", newline="\n") as f:
        for r in sorted(removed.values(), key=lambda r: r["item_id"]):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(out / "test_cases.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with open(out / "landmarks.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for lm in lms:
            f.write(json.dumps(_public(lm), ensure_ascii=False) + "\n")
    # landmarks dropped in the screening keep their answer key, so their excluded answers stay gradable
    (work / "dataset" / "metadata").mkdir(parents=True, exist_ok=True)
    with open(work / "dataset" / "metadata" / "excluded_landmarks.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for lm in all_lms:
            if lm["qid"] in dropped:
                f.write(json.dumps({**_public(lm), "excluded_reason": dropped[lm["qid"]]}, ensure_ascii=False) + "\n")
    counts: dict[str, int] = {}
    for c in cases:
        k = f"{c['arm']}|{c['question_type']}"
        counts[k] = counts.get(k, 0) + 1
    report = {"prompt_version": pv, "test_cases": len(cases), "landmarks": len(lms), "by_arm_qtype": counts,
              "premise_landmarks": sum(lm["qid"] not in dropped for lm in picked), "dropped_landmarks": dropped}
    (work / "questions_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report
