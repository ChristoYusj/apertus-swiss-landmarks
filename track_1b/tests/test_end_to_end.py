"""End-to-end replay on the synthetic fixture with a fake model: run -> grade -> score -> verify.

Also proves the regression guards work: verify must FAIL when an expected number,
a stored label or a response is tampered with, and a resumed run makes no new calls.
"""

import json
import shutil
from pathlib import Path

import pytest

from landmarks_eval import run as run_mod
from landmarks_eval.client import Endpoint, Result
from landmarks_eval.score import compute_scores, grade_all, write_scores
from landmarks_eval.verify import verify

FIXTURE = Path(__file__).parent / "fixtures" / "mini_dataset"
ANSWERS = {  # fake model: right on Q101, invents on Q102, abstains on Q103
    "Q101-photo_main-name-fr": "C'est la Fontaine Alpha.",
    "Q102-photo_main-name-fr": "Il s'agit de la Tour de Berne.",
    "Q103-photo_main-name-fr": "Je ne peux pas identifier ce monument.",
    "Q101-text_only-place-fr": "À Lausanne, canton de Vaud.",
    "Q102-text_only-place-fr": "À Genève.",
    "Q103-text_only-place-fr": "Je ne sais pas.",
}


@pytest.fixture()
def fake_model(monkeypatch):
    calls = []

    def fake_chat(ep, messages, params, retries=6):
        q = messages[-1]["content"]
        text = q if isinstance(q, str) else q[-1]["text"]
        calls.append(text)
        if text == "Reply with the word OK.":
            return Result("OK", "ok")
        # identify the item by question text + presence of an image
        has_img = not isinstance(q, str)
        for iid, ans in ANSWERS.items():
            qid = iid.split("-")[0]
            name = {"Q101": "Fontaine Alpha", "Q102": "Château Beta", "Q103": "Tour Gamma"}[qid]
            if has_img and "photo_main" in iid and any(qid in m.get("image_url", {}).get("url", "") or True for m in q[:-1]):
                pass
            if not has_img and "text_only" in iid and name in text:
                return Result(ans, "ok", "stop", {"total_tokens": 10}, 0.01, "fake")
        return Result(None, "ok")  # replaced below for photo items

    monkeypatch.setattr(run_mod, "chat", fake_chat)
    monkeypatch.setattr(run_mod, "supports_images", lambda ep, jpeg: True)
    return calls


def _patch_photo_answers(monkeypatch, calls):
    """Photo questions share the same text, so answer by image order (Q101, Q102, Q103)."""
    order = iter(["Q101", "Q102", "Q103"])

    def fake_chat(ep, messages, params, retries=6):
        q = messages[-1]["content"]
        text = q if isinstance(q, str) else q[-1]["text"]
        calls.append(text)
        if isinstance(q, str):
            for iid, ans in ANSWERS.items():
                if "text_only" in iid and {"Q101": "Fontaine Alpha", "Q102": "Château Beta", "Q103": "Tour Gamma"}[iid[:4]] in text:
                    return Result(ans, "ok", "stop", {"total_tokens": 10}, 0.01, "fake")
        qid = next(order)
        return Result(ANSWERS[f"{qid}-photo_main-name-fr"], "ok", "stop", {"total_tokens": 10}, 0.01, "fake")

    monkeypatch.setattr(run_mod, "chat", fake_chat)


def test_pipeline_and_regression_guards(tmp_path, monkeypatch, fake_model):
    calls = fake_model
    _patch_photo_answers(monkeypatch, calls)
    ep = Endpoint(model="fake/model", base_url="http://fake", api_key="x")
    results = tmp_path / "results"
    run_mod.run(FIXTURE, results, ep, concurrency=1, log=lambda *_: None)
    rows = [json.loads(l) for l in open(results / "responses.jsonl", encoding="utf-8")]
    assert len(rows) == 6 and all(r["status"] == "ok" for r in rows)

    grade_all(FIXTURE, results, judge_ep=None, log=lambda *_: None)
    scores = compute_scores(FIXTURE, results, bootstrap=200)
    name = scores["overall_by_arm_qtype"]["photo_main|name"]
    assert (name["correct"], name["incorrect"], name["not_attempted"]) == (1, 1, 1)
    assert name["hallucination_rate"] == 0.5
    place = scores["overall_by_arm_qtype"]["text_only|place"]
    assert (place["correct"], place["incorrect"], place["not_attempted"]) == (1, 1, 1)
    expected = tmp_path / "expected.json"
    write_scores(compute_scores(FIXTURE, results), expected)

    log = []
    assert verify(FIXTURE, results, expected, log=log.append), "\n".join(log)

    # resume: a second run must not call the model again
    n = len(calls)
    run_mod.run(FIXTURE, results, ep, concurrency=1, log=lambda *_: None)
    assert len(calls) == n + 0 or all(c == "Reply with the word OK." for c in calls[n:])

    # tamper 1: an expected number
    bad = json.loads(expected.read_text(encoding="utf-8"))
    bad["overall_by_arm_qtype"]["photo_main|name"]["correct"] = 3
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    assert not verify(FIXTURE, results, bad_path, log=lambda *_: None)

    # tamper 2: a stored code label
    j = results / "judgements.jsonl"
    original = j.read_text(encoding="utf-8")
    j.write_text(original.replace('"code_label": "incorrect"', '"code_label": "correct"', 1), encoding="utf-8")
    assert not verify(FIXTURE, results, expected, log=lambda *_: None)
    j.write_text(original, encoding="utf-8")

    # tamper 3: an image file
    ds = tmp_path / "ds"
    shutil.copytree(FIXTURE, ds)
    (ds / "images" / "Q101-main.jpg").write_bytes(b"not the same image")
    assert not verify(ds, results, expected, log=lambda *_: None)

    # clean state passes again
    assert verify(FIXTURE, results, expected, log=lambda *_: None)


def test_parallel_judge_cache_and_dev_set(tmp_path, monkeypatch, fake_model):
    """The judge runs in parallel, its verdicts become the final labels, a second grading run makes no new judge
    calls (cache by response hash + prompt version), and judge-dev compares the judge with confirmed labels."""
    from landmarks_eval.grading import judge as J
    from landmarks_eval.judge_dev import judge_dev
    _patch_photo_answers(monkeypatch, fake_model)
    ep = Endpoint(model="fake/model", base_url="http://fake", api_key="x")
    results = tmp_path / "results"
    run_mod.run(FIXTURE, results, ep, concurrency=1, log=lambda *_: None)

    judge_calls = []

    def fake_judge_chat(ep, messages, params, retries=6):
        judge_calls.append(1)
        text = messages[-1]["content"]
        grade = "A" if "Fontaine Alpha" in text.split("MODEL ANSWER:")[1] or "Lausanne" in text.split("MODEL ANSWER:")[1] else "C"
        return Result('{"grade": "%s", "predicted_place": null, "reason": "fake"}' % grade, "ok", "stop")

    monkeypatch.setattr(J, "chat", fake_judge_chat)
    monkeypatch.setenv("JUDGE_CONCURRENCY", "3")
    judge_ep = Endpoint(model="fake/judge", base_url="http://fake", api_key="x")
    grade_all(FIXTURE, results, judge_ep=judge_ep, log=lambda *_: None)
    rows = [json.loads(l) for l in open(results / "judgements.jsonl", encoding="utf-8")]
    assert len(judge_calls) == 6 and all(r["final_source"] == "judge" for r in rows)
    assert {r["item_id"]: r["final_label"] for r in rows}["Q101-photo_main-name-fr"] == "correct"
    assert [r["item_id"] for r in rows] == [json.loads(l)["item_id"] for l in open(results / "responses.jsonl", encoding="utf-8")]
    grade_all(FIXTURE, results, judge_ep=judge_ep, log=lambda *_: None)
    assert len(judge_calls) == 6                                # cached: no new calls

    (results / "judge_dev_set.jsonl").write_text(
        json.dumps({"item_id": "Q101-photo_main-name-fr", "confirmed_label": "correct", "confirmed_by": "test"}) + "\n" +
        json.dumps({"item_id": "Q102-photo_main-name-fr", "confirmed_label": "incorrect", "confirmed_by": "test"}) + "\n",
        encoding="utf-8")
    rep = judge_dev(FIXTURE, results, judge_ep, log=lambda *_: None)
    assert rep["n"] == 2 and rep["agreement_with_confirmed"] == 0.5
    assert [d["item_id"] for d in rep["disagreements"]] == ["Q102-photo_main-name-fr"]


def test_ai_crosscheck_is_separate_and_dropped_audit_items_are_skipped(tmp_path, monkeypatch, fake_model):
    """A second AI's grades of the audit sample are scored apart from the human audit (never merged into it), and
    sampled items whose landmark was dropped later are left out and counted instead of crashing the scorer."""
    _patch_photo_answers(monkeypatch, fake_model)
    results = tmp_path / "results"
    run_mod.run(FIXTURE, results, Endpoint(model="fake/model", base_url="http://fake", api_key="x"),
                concurrency=1, log=lambda *_: None)
    grade_all(FIXTURE, results, judge_ep=None, log=lambda *_: None)
    gone = "Q999-photo_main-name-fr"   # landmark dropped by the photo screening after the sample was drawn
    human = [{"item_id": "Q101-photo_main-name-fr", "annotator_id": "A1", "label": "correct"},
             {"item_id": gone, "annotator_id": "A1", "label": "incorrect"}]
    (results / "human_audit.jsonl").write_text("".join(json.dumps(r) + "\n" for r in human), encoding="utf-8")
    ai = [{"item_id": "Q101-photo_main-name-fr", "annotator_id": "ai:other", "label": "correct"},
          {"item_id": "Q102-photo_main-name-fr", "annotator_id": "ai:other", "label": "not_attempted"},
          {"item_id": "Q103-photo_main-name-fr", "annotator_id": "ai:other", "label": None},
          {"item_id": gone, "annotator_id": "ai:other", "label": "incorrect"}]
    (results / "ai_crosscheck_audit.jsonl").write_text("".join(json.dumps(r) + "\n" for r in ai), encoding="utf-8")
    s = compute_scores(FIXTURE, results, bootstrap=0)
    assert s["human_audit"]["items"] == 1 and s["human_audit"]["sampled_items_dropped_with_landmark"] == 1
    x = s["ai_crosscheck_audit"]
    assert x["not_a_human_audit"] is True and x["reviewer"] == ["ai:other"]
    assert (x["sampled"], x["left_unscored_as_uncertain"], x["sampled_items_dropped_with_landmark"], x["items"]) == (4, 1, 1, 2)
    assert x["code_vs_ai"]["n"] == 2 and x["code_vs_ai"]["raw_agreement"] == 0.5   # code: Q102 incorrect vs AI NA


def test_verify_works_on_a_read_only_dataset(tmp_path, monkeypatch, fake_model):
    """Judges' `make run` may read the dataset from a read-only location: verify must not need to write there."""
    _patch_photo_answers(monkeypatch, fake_model)
    results = tmp_path / "results"
    run_mod.run(FIXTURE, results, Endpoint(model="fake/model", base_url="http://fake", api_key="x"),
                concurrency=1, log=lambda *_: None)
    grade_all(FIXTURE, results, judge_ep=None, log=lambda *_: None)
    expected = tmp_path / "expected.json"
    write_scores(compute_scores(FIXTURE, results), expected)
    real_write = Path.write_text

    def read_only(self, *a, **k):
        if self.parent == results:
            raise OSError(30, "Read-only file system")
        return real_write(self, *a, **k)

    monkeypatch.setattr(Path, "write_text", read_only)
    log = []
    assert verify(FIXTURE, results, expected, log=log.append), "\n".join(log)
    assert any("read-only" in line for line in log)
    assert not (results / "scores.recomputed.json").exists()
