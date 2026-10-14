"""Dataset card: who screened the photos and who graded is derived from the files, never assumed."""

import json
import shutil
from pathlib import Path

import pytest

from landmarks_eval.build.card import build_card

FIXTURE = Path(__file__).parent / "fixtures" / "mini_dataset"


def _ds(tmp_path, review=None, ai_rows=None, human_rows=None):
    ds = tmp_path / "ds"
    shutil.copytree(FIXTURE, ds)
    ims = [json.loads(l) for l in open(ds / "metadata" / "images.jsonl", encoding="utf-8")]
    (ds / "metadata" / "images.jsonl").write_text(
        "".join(json.dumps({**i, "pii_decision": "keep"}) + "\n" for i in ims), encoding="utf-8")
    if review is not None:
        (ds / "metadata" / "review.json").write_text(json.dumps({"report": review}), encoding="utf-8")
    ref = ds / "responses" / "apertus-v1.5-70b"
    ref.mkdir(parents=True)
    (ref / "responses.jsonl").write_text(json.dumps({"item_id": "x", "model": "m"}) + "\n", encoding="utf-8")
    for name, rows in (("ai_crosscheck_audit.jsonl", ai_rows), ("human_audit.jsonl", human_rows)):
        if rows:
            (ref / name).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return ds


V3B = {"guideline_version": "v3b-ai-review", "reviewers": ["ai:claude-opus-5-5", "ai:hermes"],
       "stats": {"landmarks_with_human_decision": 4}, "dropped_landmarks": {"Q9": "x"}}


def test_ai_screening_and_ai_crosscheck_are_never_called_human(tmp_path):
    card = build_card(_ds(tmp_path, V3B, ai_rows=[{"item_id": "a", "annotator_id": "ai:hermes", "label": "correct"},
                                                  {"item_id": "b", "annotator_id": "ai:hermes", "label": None}]))
    assert "No person reviewed every shipped photo" in card and "edge cases of 4 landmarks" in card
    assert "**Human audit:** not part of this version." in card
    assert "AI cross-check (not a human audit)" in card and "(1 of 2 items" in card
    assert "reviewed by the team, jointly" not in card and "written by the team" not in card


def test_unknown_screening_provenance_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        build_card(_ds(tmp_path, {"guideline_version": None}))
    with pytest.raises(SystemExit):   # v3b with other reviewers: the detailed text would be false
        build_card(_ds(tmp_path / "b", {**V3B, "reviewers": ["ai:claude-opus-5-5", "ai:other"]}))


def test_self_consistency_only_claimed_with_repeat_labels(tmp_path):
    human = [{"item_id": "a", "annotator_id": "A1", "label": "correct", "in_overlap": False}]
    card = build_card(_ds(tmp_path, V3B, human_rows=human))
    assert "labelled blind by one annotator (A1)" in card and "self-consistency" not in card
