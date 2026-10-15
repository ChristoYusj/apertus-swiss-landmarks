"""Human photo check: a flagged photo becomes an A1 decision; `record` removes exactly the items of removed photos and
landmarks (every other item byte for byte) and stores the check; the card claims a full check only when recorded."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "mini_dataset"
TOOL = Path(__file__).resolve().parents[1] / "tools" / "screening_online" / "apply_photo_check.py"
spec = importlib.util.spec_from_file_location("apply_photo_check", TOOL)
apc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apc)


def _work(tmp_path):
    work = tmp_path / "work"
    shutil.copytree(FIXTURE, work / "dataset")
    ims = [json.loads(l) for l in open(FIXTURE / "metadata" / "images.jsonl", encoding="utf-8")]
    (work / "images.jsonl").write_text("".join(json.dumps({**i, "pii_decision": "keep"}) + "\n" for i in ims),
                                       encoding="utf-8")
    (work / "review").mkdir()
    (work / "review" / "merged.json").write_text(json.dumps({"report": {"dropped_landmarks": {}}}), encoding="utf-8")
    (work / "review" / "a1_decisions.json").write_text(json.dumps({"annotator": "A1", "decisions": {}}), encoding="utf-8")
    return work


def _online(tmp_path, checks):
    p = tmp_path / "photo_check_A1.json"
    p.write_text(json.dumps({"format": "photo-check", "annotator": "A1", "checks": checks}), encoding="utf-8")
    return p


def _lines(path):
    return open(path, encoding="utf-8").read().splitlines()


def test_unflagged_check_is_recorded_and_credited(tmp_path):
    work = _work(tmp_path)
    shipped = apc.shipped_photos(work / "dataset")
    before = _lines(work / "dataset" / "data" / "test_cases.jsonl")
    check = apc.read_check(_online(tmp_path, {q: {"main": "ok", "t": "2026-10-15T20:00:00Z"} for q in shipped}), shipped)
    res = apc.record(check, work)
    assert res["flagged"] == 0 and res["items_removed"] == 0
    assert _lines(work / "dataset" / "data" / "test_cases.jsonl") == before
    hc = json.loads((work / "review" / "merged.json").read_text(encoding="utf-8"))["report"]["human_photo_check"]
    assert hc["photos"] == 3 and hc["flagged"] == [] and hc["checked_by"] == "A1"
    assert all("A1" in json.loads(l)["pii_reviewer_ids"] for l in open(work / "images.jsonl", encoding="utf-8"))


def test_undecided_photos_are_refused(tmp_path):
    work = _work(tmp_path)
    shipped = apc.shipped_photos(work / "dataset")
    partial = apc.read_check(_online(tmp_path, {"Q101": {"main": "ok"}}), shipped)
    with pytest.raises(SystemExit):
        apc.decisions(partial, work)
    with pytest.raises(SystemExit):
        apc.record(partial, work)


def test_flagged_main_photo_removes_exactly_its_landmark(tmp_path):
    work = _work(tmp_path)
    shipped = apc.shipped_photos(work / "dataset")
    before = _lines(work / "dataset" / "data" / "test_cases.jsonl")
    check = apc.read_check(_online(tmp_path, {q: {"main": "exclude" if q == "Q102" else "ok"} for q in shipped}), shipped)
    apc.decisions(check, work)
    a1 = json.loads((work / "review" / "a1_decisions.json").read_text(encoding="utf-8"))
    assert a1["decisions"]["Q102"]["main"] == "exclude"
    with pytest.raises(SystemExit):        # the screening merge must run first
        apc.record(check, work)
    # what merge-review does with that decision: the photo is excluded and its landmark dropped
    ims = [json.loads(l) for l in open(work / "images.jsonl", encoding="utf-8")]
    (work / "images.jsonl").write_text("".join(json.dumps({**i, "pii_decision": "exclude" if i["image_id"] == "Q102-main"
                                                           else i["pii_decision"]}) + "\n" for i in ims), encoding="utf-8")
    (work / "review" / "merged.json").write_text(json.dumps({"report": {"dropped_landmarks": {"Q102": "privacy"}}}),
                                                 encoding="utf-8")
    res = apc.record(check, work)
    after = _lines(work / "dataset" / "data" / "test_cases.jsonl")
    assert res["landmarks_removed"] == 1 and all(json.loads(l)["landmark_qid"] != "Q102" for l in after)
    assert after == [l for l in before if json.loads(l)["landmark_qid"] != "Q102"]      # the rest byte for byte
    assert [json.loads(l)["qid"] for l in open(work / "dataset" / "metadata" / "excluded_landmarks.jsonl",
                                               encoding="utf-8")] == ["Q102"]
    reasons = {json.loads(l)["reason"] for l in open(work / "removed_items.jsonl", encoding="utf-8")}
    assert reasons == {"landmark removed in the photo screening: privacy"}


def test_ai_review_is_recorded_as_ai_and_credits_no_person(tmp_path):
    work = _work(tmp_path)
    shipped = apc.shipped_photos(work / "dataset")
    p = tmp_path / "ai_review.json"
    p.write_text(json.dumps({"format": "ai-photo-review", "reviewer": "ai:some-model", "accepted_by": "A1", "photos": 3,
                             "flagged": ["Q102-main"], "ai_notes": {"Q102-main": "a face"}}), encoding="utf-8")
    check = apc.read_check(p, shipped)
    apc.decisions(check, work)
    d = json.loads((work / "review" / "a1_decisions.json").read_text(encoding="utf-8"))["decisions"]["Q102"]
    assert d["by"].startswith("ai:some-model") and "third AI review" in d["reason"] and "decided_at" not in d
    ims = [json.loads(l) for l in open(work / "images.jsonl", encoding="utf-8")]
    (work / "images.jsonl").write_text("".join(json.dumps({**i, "pii_decision": "exclude" if i["image_id"] == "Q102-main"
                                                           else i["pii_decision"]}) + "\n" for i in ims), encoding="utf-8")
    (work / "review" / "merged.json").write_text(json.dumps({"report": {"dropped_landmarks": {"Q102": d["reason"]}}}),
                                                 encoding="utf-8")
    assert apc.record(check, work)["recorded_as"] == "ai_photo_review"
    report = json.loads((work / "review" / "merged.json").read_text(encoding="utf-8"))["report"]
    assert "human_photo_check" not in report and report["ai_photo_review"]["checked_by"] == "ai:some-model"
    assert not any("A1" in (json.loads(l).get("pii_reviewer_ids") or []) for l in open(work / "images.jsonl", encoding="utf-8"))
    bad = tmp_path / "bad.json"           # an AI review must name itself as AI
    bad.write_text(json.dumps({"format": "ai-photo-review", "reviewer": "A1", "photos": 3, "flagged": []}), encoding="utf-8")
    with pytest.raises(SystemExit):
        apc.read_check(bad, shipped)


def test_card_claims_a_full_human_check_only_when_recorded():
    from landmarks_eval.build.card import _human_check_line
    none = "No person reviewed every shipped photo."
    assert _human_check_line(None, 429) == none
    assert _human_check_line({"checked_by": "A1", "photos": 400, "flagged": []}, 429) == none
    assert "checked all 429 shipped photos" in _human_check_line({"checked_by": "A1", "photos": 429, "flagged": []}, 429)
    hc = {"checked_by": "A1", "photos": 429, "flagged": ["a", "b"], "removed_landmarks": ["Q1"], "method": "fillable PDF"}
    line = _human_check_line(hc, 409)
    assert "checked all 429 photos shipped at that point on a fillable PDF" in line and "flagged 2" in line
    assert _human_check_line({**hc, "photos": 410}, 409) == none     # fewer photos removed than flagged: inconsistent
