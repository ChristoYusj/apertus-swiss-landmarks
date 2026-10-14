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

    kept_key = [json.loads(l) for l in open(ds / "metadata" / "excluded_landmarks.jsonl")]
    assert [(k["qid"], k["excluded_reason"]) for k in kept_key] == [("Q2", "main photo excluded for privacy")]
    moved = prune_results(ds, new_ids, tmp_path / "removed_items.jsonl")
    assert moved == {"m": len(removed)}
    kept = [json.loads(l)["item_id"] for l in open(rdir / "responses.jsonl")]
    assert set(kept) == new_ids and len([l for l in open(rdir / "judgements.jsonl")]) == len(new_ids)
    excl = [json.loads(l) for l in open(ds / "metadata" / "excluded_items.jsonl")]
    assert {e["item_id"] for e in excl} == {r["item_id"] for r in removed}
    assert all(e["model"] == "m" and e["response_text"] == "x" and e["question_text"] for e in excl)
    assert prune_results(ds, new_ids, tmp_path / "removed_items.jsonl") == {}   # second call: nothing to move


def test_prune_is_idempotent_verbatim_and_reversible(tmp_path):
    ds = tmp_path / "ds"
    rdir = ds / "responses" / "m"
    rdir.mkdir(parents=True)
    (ds / "metadata").mkdir()
    resp = [{"item_id": i, "model": "m", "response_text": f"t{i}", "request_sha256": "abc", "usage": {"x": 1}} for i in ("a", "b", "c")]
    judg = [{"item_id": i, "code_label": "incorrect"} for i in ("a", "b", "c", "d")]   # "d": judgement without a response
    (rdir / "responses.jsonl").write_bytes("".join(json.dumps(r) + "\r\n" for r in resp).encode())  # CRLF file
    (rdir / "judgements.jsonl").write_text("".join(json.dumps(j) + "\n" for j in judg), encoding="utf-8")
    removed = tmp_path / "removed.jsonl"
    removed.write_text(json.dumps({"item_id": "c", "question_text": "Q?", "reason": "test"}) + "\n", encoding="utf-8")

    first = prune_results(ds, {"a", "b"}, removed)
    second = prune_results(ds, {"a", "b"}, removed)
    excl = [json.loads(l) for l in open(ds / "metadata" / "excluded_items.jsonl")]
    assert first == {"m": 2} and second == {}                                      # c (response) + d (judgement only)
    assert sorted(e["item_id"] for e in excl) == ["c", "d"]                         # one record each, no duplicates
    c = next(e for e in excl if e["item_id"] == "c")
    assert c["response_row"] == resp[2] and c["judgement_row"] == judg[2] and c["reason"] == "test"
    assert (rdir / "responses.jsonl").read_bytes().count(b"\r\n") == 2             # kept lines untouched (CRLF)

    back = prune_results(ds, {"a", "b", "c"}, removed)                              # item c comes back
    assert back == {"m:restored": 1}
    rows = [json.loads(l) for l in open(rdir / "responses.jsonl")]
    assert [r["item_id"] for r in rows] == ["a", "b", "c"] and rows[2] == resp[2]
    assert [e["item_id"] for e in (json.loads(l) for l in open(ds / "metadata" / "excluded_items.jsonl"))] == ["d"]


def _ai(decisions):
    return {"format": "ai-screening", "model": "claude-opus-5-5", "decisions": {
        q: {"main_id": f"{q}-main", "alt": "none", "low": "none", **d} for q, d in decisions.items()}}


def test_ai_screening_needs_a1_check_and_a1_wins(tmp_path):
    """Protocol v3-ai-assisted: a photo ships only if A1 accepted it; unchecked landmarks stay pending."""
    ai = _ai({"Q1": {"main": "ok", "alt": "Q1-alt2", "low": "Q1-alt1"},
              "Q2": {"main": "ok", "alt": "Q2-alt1"},            # A1: recognisable person on the main photo
              "Q3": {"main": "exclude"},                         # A1 overrules: OK, no other photos
              "Q4": {"main": "ok", "alt": "Q4-alt1"},            # A1: 2nd view is another building -> none
              "Q5": {"main": "ok", "alt": "Q5-alt1"}})           # not checked -> pending
    check = {"format": "screening-check", "annotator": "A1", "checks": {
        "Q1": {"main": "ok", "alt": "ok", "low": "ok", "agree": True},
        "Q2": {"main": "exclude"},
        "Q3": {"main": "ok"},
        "Q4": {"main": "ok", "alt": "reject"}}}
    from landmarks_eval.build.review_merge import combine_ai_check
    team = combine_ai_check(ai, check)
    assert team["format"] == "team-consensus" and team["reviewers"] == ["ai:claude-opus-5-5", "A1"]
    assert team["decisions"] == {"Q1": {"main": "ok", "main_id": "Q1-main", "alt": "Q1-alt2", "low": "Q1-alt1"},
                                 "Q2": {"main": "exclude", "main_id": "Q2-main"},
                                 "Q3": {"main": "ok", "main_id": "Q3-main", "alt": "none"},
                                 "Q4": {"main": "ok", "main_id": "Q4-main", "alt": "none"}}
    assert team["check_stats"]["unchecked"] == 1 and team["check_stats"]["main_ok_to_exclude"] == 1
    assert team["check_stats"]["main_exclude_to_ok"] == 1
    _write_images(tmp_path, IMGS)
    p = tmp_path / "screening_team.json"
    p.write_text(json.dumps(team))
    rep = merge_review(tmp_path, [p])
    out = {json.loads(l)["image_id"]: json.loads(l) for l in open(tmp_path / "images.jsonl")}
    assert out["Q1-alt2"]["pii_reviewer_ids"] == ["ai:claude-opus-5-5", "A1"]
    assert out["Q2-main"]["pii_decision"] == "exclude" and "checked by A1" in out["Q2-main"]["pii_reason"]
    assert out["Q4-alt1"]["pii_decision"] == "pending"            # rejected 2nd view is never shipped
    assert rep["stats"]["landmarks_pending"] == 1 and rep["complete"] is False   # Q5: the privacy gate stays shut


def test_ai_screening_alt_left_unchecked_keeps_the_merge_incomplete():
    from landmarks_eval.build.review_merge import combine_ai_check
    team = combine_ai_check(_ai({"Q1": {"main": "ok", "alt": "Q1-alt1"}}),
                            {"format": "screening-check", "checks": {"Q1": {"main": "ok"}}})
    assert team["decisions"]["Q1"] == {"main": "ok", "main_id": "Q1-main"} and team["check_stats"]["alt_unchecked"] == 1
    with pytest.raises(SystemExit):
        combine_ai_check({"format": "x", "decisions": {}}, {"format": "screening-check", "checks": {}})


def test_second_ai_reviewer_is_named_and_human_edge_cases_add_a1(tmp_path):
    """Protocol v3b-ai-review: a second AI checks; only landmarks with a human edge decision name A1."""
    from landmarks_eval.build.review_merge import combine_ai_check
    ai = _ai({"Q1": {"main": "ok", "alt": "Q1-alt2"}, "Q2": {"main": "ok", "alt": "Q2-alt1"},
              "Q3": {"main": "ok"}, "Q4": {"main": "ok"}, "Q5": {"main": "ok", "alt": "Q5-alt1"}})
    check = {"format": "screening-check", "annotator": "ai:hermes", "checks": {
        "Q1": {"main": "ok", "alt": "ok"},
        "Q2": {"main": "wrong", "reason": "main photo may not show the landmark (excluded when unsure)"},
        "Q3": {"main": "ok"}, "Q4": {"main": "wrong", "human": True, "reason": "photo shows another building"},
        "Q5": {"main": "ok", "alt": "reject", "human": True}}}
    team = combine_ai_check(ai, check)
    assert team["guideline_version"] == "v3b-ai-review" and team["reviewers"] == ["ai:claude-opus-5-5", "ai:hermes"]
    assert team["decisions"]["Q5"]["reviewers"] == ["ai:claude-opus-5-5", "ai:hermes", "A1"]
    assert "reviewers" not in team["decisions"]["Q1"] and "reason" not in team["decisions"]["Q1"]
    _write_images(tmp_path, IMGS)
    p = tmp_path / "screening_team.json"
    p.write_text(json.dumps(team))
    rep = merge_review(tmp_path, [p])
    out = {json.loads(l)["image_id"]: json.loads(l) for l in open(tmp_path / "images.jsonl")}
    assert out["Q1-alt2"]["pii_reviewer_ids"] == ["ai:claude-opus-5-5", "ai:hermes"]
    assert out["Q5-main"]["pii_reviewer_ids"] == ["ai:claude-opus-5-5", "ai:hermes", "A1"]
    assert out["Q5-alt1"]["pii_decision"] == "pending"
    assert rep["dropped_landmarks"] == {"Q2": "main photo may not show the landmark (excluded when unsure)",
                                        "Q4": "photo shows another building"}
    assert rep["complete"] is True
    with pytest.raises(SystemExit):
        combine_ai_check(ai, {**check, "annotator": "someone"})
