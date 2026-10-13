"""Human grading audit (Task G): pre-registered sampling, blind page, label merge."""

import json
import re

from landmarks_eval.build import audit


def _dataset(tmp_path, n=600):
    ds, res = tmp_path / "ds", tmp_path / "res"
    (ds / "data").mkdir(parents=True)
    res.mkdir()
    lm = {"qid": "Q1", "labels": {"fr": "Tour Zyx"}, "name_aliases": [{"text": "Tour Zyx", "lang": "fr", "source": "x"}],
          "place_aliases": [{"text": "Aigle", "lang": "", "source": "bfs:name"}], "canton_aliases": [{"text": "VD", "lang": "", "source": "x"}],
          "municipality_name": "Aigle", "gold_year": None, "language_region": "FR", "canton_code": "VD"}
    (ds / "data" / "landmarks.jsonl").write_text(json.dumps(lm) + "\n", encoding="utf-8")
    cases, resp, judg = [], [], []
    for i in range(n):
        iid = f"Q1-x{i:04d}"
        cases.append({"item_id": iid, "landmark_qid": "Q1", "arm": "photo_main" if i % 5 else "text_only",
                      "question_type": "name", "lang": ["fr", "de"][i % 2], "template_id": "name.photo",
                      "question_text": "Quel est ce bâtiment ?"})
        resp.append({"item_id": iid, "response_text": f"answer {i}"})
        judg.append({"item_id": iid, "code_label": ["incorrect", "not_attempted"][i % 3 == 0], "judge_label": None,
                     "final_label": "incorrect"})
    for name, rows in (("data/test_cases.jsonl", cases),):
        (ds / name).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (res / "responses.jsonl").write_text("".join(json.dumps(r) + "\n" for r in resp), encoding="utf-8")
    (res / "judgements.jsonl").write_text("".join(json.dumps(r) + "\n" for r in judg), encoding="utf-8")
    return ds, res


def test_sample_is_stratified_seeded_and_excludes_dev(tmp_path):
    ds, res = _dataset(tmp_path)
    s1 = audit.draw_sample(ds, res, dev_ids={"Q1-x0001"})
    s2 = audit.draw_sample(ds, res, dev_ids={"Q1-x0001"})
    assert s1 == s2                                                     # seeded
    ids = [x["item_id"] for x in s1["items"]]
    assert "Q1-x0001" not in ids
    assert abs(len(ids) - 0.2 * 599) <= 4                               # 20 %, rounded per stratum
    assert s1["n_overlap"] == 100 and sum(x["in_overlap"] for x in s1["items"]) == 100
    assert all(len(x["annotators"]) == (3 if x["in_overlap"] else 1) for x in s1["items"])
    assert max(s1["per_annotator"].values()) - min(s1["per_annotator"].values()) <= 1


def test_page_is_blind_and_merge_keeps_latest(tmp_path):
    ds, res = _dataset(tmp_path)
    page = audit.build_page(ds, res, tmp_path / "out")
    html = page.read_text(encoding="utf-8")
    data = json.loads(re.search(r"const D = (\{.*?\}), VERSION", html, re.S).group(1).replace("<\\/", "</"))
    assert not any(k in it for it in data["items"] for k in ("code_label", "judge_label", "final_label", "label"))
    sample = json.loads((tmp_path / "out" / "audit_sample.json").read_text())
    ov = next(x["item_id"] for x in sample["items"] if x["in_overlap"])
    solo = next(x for x in sample["items"] if not x["in_overlap"])
    other = next(a for a in ("A1", "A2", "A3") if a not in solo["annotators"])
    f1 = tmp_path / "a.json"
    f1.write_text(json.dumps({"format": "audit-v1", "guideline_version": "v2", "labels": {
        "A1": {ov: {"label": "correct", "t": "2026-10-15T08:00:00Z"}},
        other: {solo["item_id"]: {"label": "correct", "t": "2026-10-15T08:00:00Z"}}}}))   # not assigned -> ignored
    f2 = tmp_path / "b.json"
    f2.write_text(json.dumps({"format": "audit-v1", "guideline_version": "v2", "labels": {
        "A1": {ov: {"label": "incorrect", "t": "2026-10-15T09:00:00Z", "used_translation": True}}}}))
    rep = audit.merge_labels(res, [f1, f2], tmp_path / "out" / "audit_sample.json")
    rows = [json.loads(l) for l in open(res / "human_audit.jsonl")]
    assert rep["labels"] == 1 and rows[0]["label"] == "incorrect" and rows[0]["used_translation"] is True
    assert rows[0]["in_overlap"] is True and rep["complete"] is False


def test_agreement_majority_and_kappas():
    from landmarks_eval.agreement import agreement
    cases = {f"i{k}": {"lang": "fr" if k < 3 else "de"} for k in range(5)}
    judg = {"i0": {"judge_label": "incorrect", "code_label": "incorrect"},
            "i1": {"judge_label": "correct", "code_label": "incorrect"},
            "i2": {"judge_label": "not_attempted", "code_label": "not_attempted"},
            "i3": {"judge_label": "incorrect", "code_label": "incorrect"},
            "i4": {"judge_label": None, "code_label": "correct"}}
    h = [{"item_id": "i0", "annotator_id": a, "label": l} for a, l in zip(("A1", "A2", "A3"), ("incorrect", "incorrect", "correct"))]
    h += [{"item_id": "i1", "annotator_id": a, "label": l} for a, l in zip(("A1", "A2", "A3"), ("correct", "incorrect", "not_attempted"))]
    h += [{"item_id": "i2", "annotator_id": "A1", "label": "not_attempted"},
          {"item_id": "i3", "annotator_id": "A2", "label": "incorrect"}, {"item_id": "i4", "annotator_id": "A3", "label": "correct"}]
    a = agreement(h, judg, cases)
    assert a["items"] == 5 and a["overlap_items_complete"] == 2 and a["overlap_no_majority"] == 1
    assert a["judge_vs_human"]["n"] == 3            # i1 has no majority, i4 has no judge label
    assert a["judge_vs_human"]["raw_agreement"] == 1.0
    assert a["code_vs_human"]["n"] == 4 and a["code_vs_human"]["raw_agreement"] == 1.0
    assert a["by_lang"]["de"]["code_vs_human"]["n"] == 2
