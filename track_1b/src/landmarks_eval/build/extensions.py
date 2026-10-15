"""Extension items registered in docs/extensions_plan.md (15 Oct): multiple choice (E2) and a second wording (E3).

Appended to data/test_cases.jsonl after the main items; idempotent (earlier extension items are replaced). The main
items are never touched.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import yaml

from ..schema import TestCase
from .questions import town_for

SEED = 20261019
EXT_ARMS = ("photo_mc", "photo_main_w2")
REGION_LANG = {"DE": "de", "FR": "fr", "IT": "it", "RM": "rm"}
MC_LANGS = ("fr", "de", "it", "rm")
W2_LANGS = ("fr", "rm")


def _templates() -> dict:
    return yaml.safe_load((Path(__file__).resolve().parent.parent / "prompts" / "templates_v2.yaml").read_text(encoding="utf-8"))


def display_name(lm: dict, lang: str) -> str:
    """Label in the question's language, else in the landmark's region language, else English, else the first
    name alias; followed by the municipality (as shown in that language)."""
    labels = lm["labels"]
    name = labels.get(lang) or labels.get(REGION_LANG[lm["language_region"]]) or labels.get("en") \
        or lm["name_aliases"][0]["text"]
    return f"{name} ({town_for(lm, lang)})"


def _distractors(lm: dict, pool: list[dict], rng: random.Random) -> list[dict]:
    """3 other landmarks: same type group, same language region first, then any region; if the type group is too
    small (fewer than 4 landmarks), the rest come from all landmarks."""
    others = [o for o in pool if o["qid"] != lm["qid"]]
    tiers = [[o for o in others if o["type_group"] == lm["type_group"] and o["language_region"] == lm["language_region"]],
             [o for o in others if o["type_group"] == lm["type_group"] and o["language_region"] != lm["language_region"]],
             [o for o in others if o["type_group"] != lm["type_group"]]]
    picked: list[dict] = []
    shown = {display_name(lm, l) for l in MC_LANGS}
    for tier in tiers:
        tier = sorted(tier, key=lambda o: o["qid"])
        rng.shuffle(tier)
        for o in tier:
            names = {display_name(o, l) for l in MC_LANGS}
            if len(picked) < 3 and not (names & shown):        # no option may read like another one, in any language
                picked.append(o)
                shown |= names
    assert len(picked) == 3, lm["qid"]
    return picked


def build_extensions(ds: Path) -> dict:
    path = ds / "data" / "test_cases.jsonl"
    cases = [json.loads(l) for l in open(path, encoding="utf-8")]
    main = [c for c in cases if c["arm"] not in EXT_ARMS]
    lms = [json.loads(l) for l in open(ds / "data" / "landmarks.jsonl", encoding="utf-8")]
    main_photo = {c["landmark_qid"]: c["image_id"] for c in main if c["arm"] == "photo_main"}
    T = _templates()
    new = []
    for lm in sorted(lms, key=lambda l: l["qid"]):
        img = main_photo[lm["qid"]]
        rng = random.Random(f"{SEED}-{lm['qid']}")
        opts = [lm, *_distractors(lm, lms, rng)]
        rng.shuffle(opts)
        answer = "ABCD"[[o["qid"] for o in opts].index(lm["qid"])]
        for lang in MC_LANGS:
            names = [display_name(o, lang) for o in opts]
            text = T["mc"]["templates"][lang].format(options="\n".join(f"{l}) {n}" for l, n in zip("ABCD", names)))
            new.append({"item_id": f"{lm['qid']}-photo_mc-name-{lang}", "landmark_qid": lm["qid"], "arm": "photo_mc",
                        "question_type": "name", "lang": lang, "template_id": "mc.photo",
                        "prompt_version": T["mc"]["prompt_version"], "question_text": text, "image_id": img,
                        "expected_behavior": "answer", "options": names, "option_qids": [o["qid"] for o in opts],
                        "answer_option": answer})
        for lang in W2_LANGS:
            for q in ("name", "place"):
                new.append({"item_id": f"{lm['qid']}-photo_main_w2-{q}-{lang}", "landmark_qid": lm["qid"],
                            "arm": "photo_main_w2", "question_type": q, "lang": lang, "template_id": f"{q}.photo.w2",
                            "prompt_version": T["w2"]["prompt_version"], "question_text": T["w2"]["templates"][lang][q],
                            "image_id": img, "expected_behavior": "answer"})
    for c in new:
        TestCase.model_validate(c)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for c in main + new:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    letters = {l: sum(1 for c in new if c.get("answer_option") == l and c["lang"] == "fr") for l in "ABCD"}
    return {"main_items": len(main), "photo_mc": sum(c["arm"] == "photo_mc" for c in new),
            "photo_main_w2": sum(c["arm"] == "photo_main_w2" for c in new), "answer_letters": letters}
