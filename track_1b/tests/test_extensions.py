"""Extension items (docs/extensions_plan.md): multiple-choice grading and the item builder."""

import json

import pytest

from landmarks_eval.build.extensions import build_extensions
from landmarks_eval.grading.rules import grade_mc

MC = {"arm": "photo_mc", "answer_option": "B",
      "options": ["Tour des Sorciers (Sion)", "Château de Chillon (Veytaux)", "Église Saint-Martin (Vevey)", "Pont de Berne (Fribourg)"]}


@pytest.mark.parametrize("text,label,rule", [
    ("B) Château de Chillon (Veytaux)", "correct", "mc_option"),
    ("B", "correct", "mc_option"),
    ("La réponse est B.", "correct", "mc_option"),
    ("C'est le Château de Chillon.", "correct", "mc_option"),            # the option's text, without the letter
    ("D'après l'image, c'est C.", "incorrect", "mc_option"),            # "D'" is not option D
    ("A) Tour des Sorciers", "incorrect", "mc_option"),
    ("Peut-être B, le château.", "correct", "mc_option"),               # a hedged guess is graded on the guess
    ("A. ou C.", "incorrect", "mc_several_options"),
    ("Je ne suis pas sûr.", "not_attempted", "mc_refusal"),
    ("Il s'agit d'une église.", "not_attempted", "mc_no_option"),
])
def test_multiple_choice_grading(text, label, rule):
    g = grade_mc(MC, text)
    assert (g.label, g.rule) == (label, rule)


def _lm(qid, typ, region, name):
    return {"qid": qid, "labels": {"fr": name, "de": name}, "name_aliases": [{"text": name, "lang": "fr"}],
            "place_aliases": [{"text": f"Town{qid}", "lang": "", "source": "bfs:name"}], "municipality_name": f"Town{qid}",
            "type_group": typ, "language_region": region}


def _ds(tmp_path):
    ds = tmp_path / "ds"
    (ds / "data").mkdir(parents=True)
    lms = [_lm("Q1", "castle", "FR", "Castle One"), _lm("Q2", "castle", "FR", "Castle Two"),
           _lm("Q3", "castle", "DE", "Castle Three"), _lm("Q4", "church", "FR", "Church Four"),
           _lm("Q5", "monument", "IT", "Statue Five"), _lm("Q6", "castle", "IT", "Castle Six")]
    (ds / "data" / "landmarks.jsonl").write_text("".join(json.dumps(l) + "\n" for l in lms), encoding="utf-8")
    main = [{"item_id": f"{l['qid']}-photo_main-name-fr", "landmark_qid": l["qid"], "arm": "photo_main",
             "question_type": "name", "lang": "fr", "template_id": "name.photo", "prompt_version": "q-v1",
             "question_text": "Quel est ce bâtiment ?", "image_id": f"{l['qid']}-main", "expected_behavior": "answer"}
            for l in lms]
    (ds / "data" / "test_cases.jsonl").write_text("".join(json.dumps(c) + "\n" for c in main), encoding="utf-8")
    return ds, main


def test_builder_is_deterministic_idempotent_and_leaves_main_items(tmp_path):
    ds, main = _ds(tmp_path)
    rep = build_extensions(ds)
    first = (ds / "data" / "test_cases.jsonl").read_text(encoding="utf-8")
    assert build_extensions(ds) == rep and (ds / "data" / "test_cases.jsonl").read_text(encoding="utf-8") == first
    rows = [json.loads(l) for l in first.splitlines()]
    assert rows[:len(main)] == main                                   # main items untouched, in order
    mc = [r for r in rows if r["arm"] == "photo_mc"]
    w2 = [r for r in rows if r["arm"] == "photo_main_w2"]
    assert len(mc) == 6 * 4 and len(w2) == 6 * 2 * 2 and rep["photo_mc"] == 24
    for r in mc:
        assert r["option_qids"]["ABCD".index(r["answer_option"])] == r["landmark_qid"]
        assert len(set(r["option_qids"])) == 4 and all(f"{l}) " in r["question_text"] for l in "ABCD")
    q1 = next(r for r in mc if r["item_id"] == "Q1-photo_mc-name-fr")
    assert {"Q2", "Q3", "Q6"} == set(q1["option_qids"]) - {"Q1"}      # same type first (castle), FR region first
    q5 = next(r for r in mc if r["item_id"] == "Q5-photo_mc-name-fr")
    assert len(set(q5["option_qids"])) == 4                          # a one-landmark type group borrows other types
    langs = {r["option_qids"][0] for r in mc if r["landmark_qid"] == "Q1"}
    assert len(langs) == 1                                            # the same option order in every language
