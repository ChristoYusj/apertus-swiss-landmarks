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
