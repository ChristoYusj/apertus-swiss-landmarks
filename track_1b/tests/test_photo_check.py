"""Human photo check: recorded only when it covers every shipped photo with none flagged; the card follows it."""

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
    shutil.copy(FIXTURE / "metadata" / "images.jsonl", work / "images.jsonl")
    (work / "review").mkdir()
    (work / "review" / "merged.json").write_text(json.dumps({"report": {"guideline_version": "v3b-ai-review"}}),
                                                 encoding="utf-8")
    return work


def _online(tmp_path, checks):
    p = tmp_path / "photo_check_A1.json"
    p.write_text(json.dumps({"format": "photo-check", "annotator": "A1", "checks": checks}), encoding="utf-8")
    return p


def test_complete_online_check_is_recorded_and_credited(tmp_path):
    work = _work(tmp_path)
    shipped = apc.shipped_photos(work / "dataset")
    check = apc.read_check(_online(tmp_path, {q: {"main": "ok", "t": "2026-10-15T20:00:00Z"} for q in shipped}), shipped)
    res = apc.apply(check, work)
    assert res["flagged"] == 0 and res["reviewer_added_to"] == 3
    hc = json.loads((work / "review" / "merged.json").read_text(encoding="utf-8"))["report"]["human_photo_check"]
    assert hc["photos"] == 3 and hc["flagged"] == [] and hc["checked_by"] == "A1"
    assert all("A1" in json.loads(l)["pii_reviewer_ids"] for l in open(work / "images.jsonl", encoding="utf-8"))


def test_undecided_or_flagged_photos_are_refused(tmp_path):
    work = _work(tmp_path)
    shipped = apc.shipped_photos(work / "dataset")
    partial = apc.read_check(_online(tmp_path, {"Q101": {"main": "ok"}}), shipped)
    with pytest.raises(SystemExit):
        apc.apply(partial, work)
    flagged = apc.read_check(_online(tmp_path, {q: {"main": "exclude" if q == "Q102" else "ok"} for q in shipped}), shipped)
    with pytest.raises(SystemExit):
        apc.apply(flagged, work)
    assert "human_photo_check" not in json.loads((work / "review" / "merged.json").read_text(encoding="utf-8"))["report"]


def test_card_claims_a_full_human_check_only_when_recorded():
    from landmarks_eval.build.card import _human_check_line
    assert _human_check_line(None, 429) == "No person reviewed every shipped photo."
    assert _human_check_line({"checked_by": "A1", "photos": 400, "flagged": []}, 429) == "No person reviewed every shipped photo."
    assert _human_check_line({"checked_by": "A1", "photos": 429, "flagged": ["x"]}, 429) == "No person reviewed every shipped photo."
    assert "checked all 429 shipped photos" in _human_check_line({"checked_by": "A1", "photos": 429, "flagged": []}, 429)
