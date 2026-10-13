"""Photo screening (guideline v2-team): one joint decision per landmark, dropped landmarks, no silent deletion."""

import json

import pytest

from landmarks_eval.build.assemble import prune_results
from landmarks_eval.build.questions import build_questions
from landmarks_eval.build.review_merge import merge_review


def _img(iid, qid, role):
    return {"image_id": iid, "landmark_qid": qid, "role": role, "pii_decision": "pending", "pii_reason": None,
            "pii_reviewer_ids": [], "faces_detected": 0}


def _write_images(tmp_path, imgs):
    (tmp_path / "images.jsonl").write_text("\n".join(json.dumps(i) for i in imgs) + "\n", encoding="utf-8")


def _team_file(tmp_path, decisions, fmt="team-consensus"):
    p = tmp_path / "screening_team.json"
    p.write_text(json.dumps({"format": fmt, "annotator": "team", "guideline_version": "v2-team", "decisions": decisions}))
    return p


IMGS = [_img("Q1-main", "Q1", "main_p18"), _img("Q1-alt1", "Q1", "alt"), _img("Q1-alt2", "Q1", "alt"),
        _img("Q2-main", "Q2", "main_p18"), _img("Q2-alt1", "Q2", "alt"),
        _img("Q3-main", "Q3", "main_p18"), _img("Q4-main", "Q4", "main_p18"), _img("Q4-alt1", "Q4", "alt"),
        _img("Q5-main", "Q5", "main_p18"), _img("Q5-alt1", "Q5", "alt")]


def test_merge_team_decisions(tmp_path):
    _write_images(tmp_path, IMGS)
    dec = {"Q1": {"main": "ok", "alt": "Q1-alt2", "low": "Q1-alt1"},
           "Q2": {"main": "exclude", "alt": "Q2-alt1"},   # alt choice ignored: landmark dropped
           "Q3": {"main": "ok"},                           # no other photos: complete without an alt choice
           "Q4": {"main": "wrong"},
           "Q5": {"main": "ok", "alt": "none"}}
    rep = merge_review(tmp_path, [_team_file(tmp_path, dec)])
    merged = json.loads((tmp_path / "review" / "merged.json").read_text())
    out = {json.loads(l)["image_id"]: json.loads(l) for l in open(tmp_path / "images.jsonl")}
    assert merged["alt_accepted"] == {"Q1": "Q1-alt2"}
    assert merged["lowinfo"] == {"Q1": "Q1-alt1"}
    assert rep["dropped_landmarks"] == {"Q2": "main photo excluded for privacy", "Q4": "main photo does not show the landmark"}
    assert out["Q2-main"]["pii_decision"] == "exclude" and out["Q2-alt1"]["pii_decision"] == "pending"
    assert out["Q1-alt1"]["pii_decision"] == out["Q1-alt2"]["pii_decision"] == "keep"
    assert out["Q5-alt1"]["pii_decision"] == "pending"           # not picked -> never shipped
    assert out["Q1-main"]["pii_reviewer_ids"] == ["team"]
    assert rep["complete"] is True


def test_partial_file_is_safe_and_merge_is_idempotent(tmp_path):
    _write_images(tmp_path, IMGS)
    merge_review(tmp_path, [_team_file(tmp_path, {"Q1": {"main": "ok", "alt": "Q1-alt1"}})])
    rep = merge_review(tmp_path, [_team_file(tmp_path, {"Q1": {"main": "ok"}})])  # later file un-picks the alt
    out = {json.loads(l)["image_id"]: json.loads(l) for l in open(tmp_path / "images.jsonl")}
    assert out["Q1-alt1"]["pii_decision"] == "pending"           # earlier "keep" did not stick
    assert rep["stats"]["landmarks_pending"] == 4 and rep["stats"]["alt_choice_pending"] == 1
    assert rep["complete"] is False


def test_merge_rejects_bad_files(tmp_path):
    _write_images(tmp_path, IMGS)
    with pytest.raises(SystemExit):
        merge_review(tmp_path, [_team_file(tmp_path, {}, fmt=None)])
    with pytest.raises(SystemExit):   # a photo of another landmark
        merge_review(tmp_path, [_team_file(tmp_path, {"Q1": {"main": "ok", "alt": "Q2-alt1"}})])
    with pytest.raises(SystemExit):   # same photo as 2nd view and too generic
        merge_review(tmp_path, [_team_file(tmp_path, {"Q1": {"main": "ok", "alt": "Q1-alt1", "low": "Q1-alt1"}})])


def _lm(qid, town):
    return {"qid": qid, "labels": {"fr": f"Tour Zyx{qid}", "de": f"Turm Zyx{qid}"},
            "name_aliases": [{"text": f"Tour Zyx{qid}", "lang": "fr", "source": "wikidata:label", "distinctive": True}],
            "place_aliases": [{"text": town, "lang": "", "source": "bfs:name"}], "municipality_name": town,
            "gold_year": None, "language_region": "FR", "_siblings": [], "main_image_id": f"{qid}-main"}


def test_dropped_landmark_items_are_logged_then_moved_not_deleted(tmp_path):
    lms = [_lm("Q1", "Aigle"), _lm("Q2", "Bex")]
    (tmp_path / "landmarks_final.jsonl").write_text("\n".join(json.dumps(l) for l in lms) + "\n", encoding="utf-8")
    first = build_questions(tmp_path)
    ds = tmp_path / "dataset"
    ids = [json.loads(l)["item_id"] for l in open(ds / "data" / "test_cases.jsonl")]
    rdir = ds / "responses" / "m"
    rdir.mkdir(parents=True)
    (rdir / "responses.jsonl").write_text("".join(json.dumps({"item_id": i, "model": "m", "response_text": "x"}) + "\n" for i in ids))
    (rdir / "judgements.jsonl").write_text("".join(json.dumps({"item_id": i}) + "\n" for i in ids))

    second = build_questions(tmp_path, dropped={"Q2": "main photo excluded for privacy"})
    new_ids = {json.loads(l)["item_id"] for l in open(ds / "data" / "test_cases.jsonl")}
    assert second["test_cases"] == first["test_cases"] - sum(i.startswith("Q2-") for i in ids)
    assert not any(i.startswith("Q2-") for i in new_ids)
    assert [json.loads(l)["qid"] for l in open(ds / "data" / "landmarks.jsonl")] == ["Q1"]
    removed = [json.loads(l) for l in open(tmp_path / "removed_items.jsonl")]
    assert {r["item_id"] for r in removed} == {i for i in ids if i.startswith("Q2-")}
    assert all("photo screening" in r["reason"] and r["question_text"] for r in removed)

    (ds / "metadata").mkdir()
    moved = prune_results(ds, new_ids, tmp_path / "removed_items.jsonl")
    assert moved == {"m": len(removed)}
    kept = [json.loads(l)["item_id"] for l in open(rdir / "responses.jsonl")]
    assert set(kept) == new_ids and len([l for l in open(rdir / "judgements.jsonl")]) == len(new_ids)
    excl = [json.loads(l) for l in open(ds / "metadata" / "excluded_items.jsonl")]
    assert {e["item_id"] for e in excl} == {r["item_id"] for r in removed}
    assert all(e["model"] == "m" and e["response_text"] == "x" and e["question_text"] for e in excl)
    assert prune_results(ds, new_ids, tmp_path / "removed_items.jsonl") == {}   # second call: nothing to move
