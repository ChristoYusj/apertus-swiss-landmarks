"""Photo-screening merge rules: cautious privacy, unanimous 2nd views, >=2 votes for low-info traps."""

import json

from landmarks_eval.build.review_merge import merge_review


def _img(iid, qid, role):
    return {"image_id": iid, "landmark_qid": qid, "role": role, "pii_decision": "pending", "pii_reason": None,
            "pii_reviewer_ids": [], "faces_detected": 0}


def test_merge_rules(tmp_path):
    imgs = [_img("Q1-main", "Q1", "main_p18"), _img("Q1-alt1", "Q1", "alt"), _img("Q1-alt2", "Q1", "alt"),
            _img("Q2-main", "Q2", "main_p18"), _img("Q2-alt1", "Q2", "alt")]
    (tmp_path / "images.jsonl").write_text("\n".join(json.dumps(i) for i in imgs) + "\n", encoding="utf-8")
    (tmp_path / "review").mkdir()
    who = {"Q1-main": ["A1"], "Q1-alt1": ["A1", "A2", "A3"], "Q1-alt2": ["A2"], "Q2-main": ["A3"], "Q2-alt1": ["A1", "A2", "A3"]}
    (tmp_path / "review" / "assignment.json").write_text(json.dumps({"items": [{"id": k, "who": v} for k, v in who.items()]}))
    dec = {
        "A1": {"Q1-main": {"privacy": "keep"}, "Q1-alt1": {"privacy": "keep", "view": "good", "lowinfo": True},
               "Q2-alt1": {"privacy": "keep", "view": "good"}},
        "A2": {"Q1-alt1": {"privacy": "keep", "view": "good", "lowinfo": True}, "Q1-alt2": {"privacy": "keep", "view": "good"},
               "Q2-alt1": {"privacy": "exclude"}},
        "A3": {"Q1-alt1": {"privacy": "keep", "view": "bad"}, "Q2-main": {"privacy": "exclude"},
               "Q2-alt1": {"privacy": "keep", "view": "good"}},
    }
    files = []
    for a, d in dec.items():
        p = tmp_path / f"screening_{a}.json"
        p.write_text(json.dumps({"annotator": a, "decisions": d}))
        files.append(p)
    rep = merge_review(tmp_path, files)
    merged = json.loads((tmp_path / "review" / "merged.json").read_text())
    out = {json.loads(l)["image_id"]: json.loads(l) for l in open(tmp_path / "images.jsonl")}
    assert out["Q2-alt1"]["pii_decision"] == "exclude"          # one exclude vote is enough
    assert out["Q1-alt1"]["pii_decision"] == "keep"
    assert merged["alt_accepted"] == {"Q1": "Q1-alt2"}          # Q1-alt1 not unanimous (A3 said bad)
    assert merged["lowinfo"] == {"Q1": "Q1-alt1"}              # two low-info votes
    assert rep["dropped_landmarks_main_photo_excluded"] == ["Q2"]
