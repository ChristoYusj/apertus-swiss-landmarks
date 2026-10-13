"""`landmarks-eval verify`: offline self-check of a results directory against the dataset and expected scores.

Checks (any failure -> exit code 1):
  V1 every dataset file and every response/judgement row validates against the frozen schema
  V2 every shipped image's SHA-256 matches the hash recorded in the dataset metadata
  V3 every main test case has exactly one response (coverage)
  V4 re-running the deterministic code grader reproduces every stored code_label exactly
  V5 final labels follow the documented rule (judge label if present, else code label)
  V7 privacy: every shipped photo was cleared in the human screening (no unscreened photo is publishable)
  V6 recomputed scores equal the expected scores file (all numbers, after rounding)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .analysis import load_gazetteer
from .grading.rules import grade
from .run import load_jsonl
from .schema import ImageRecord, Judgement, Landmark, Response, TestCase
from .score import compute_scores, sha


def _diff(a, b, path="") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}/{k}: {'missing in recomputed' if k not in a else 'missing in expected'}")
            else:
                out += _diff(a[k], b[k], f"{path}/{k}")
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in _diff(x, y, f"{path}[{i}]")]
    return [] if a == b else [f"{path}: recomputed={a!r} expected={b!r}"]


def verify(dataset: Path, results: Path, expected: Path | None, log=print) -> bool:
    ok = True

    def check(name: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= passed
        log(f"  [{'PASS' if passed else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")

    log(f"verify: dataset={dataset} results={results}")
    errs = []
    for fname, model in (("data/landmarks.jsonl", Landmark), ("data/test_cases.jsonl", TestCase),
                         ("metadata/images.jsonl", ImageRecord)):
        for i, row in enumerate(load_jsonl(dataset / fname)):
            try:
                model.model_validate(row)
            except Exception as e:  # noqa: BLE001
                errs.append(f"{fname}:{i + 1}: {str(e).splitlines()[0]}")
    responses = load_jsonl(results / "responses.jsonl")
    judgements = load_jsonl(results / "judgements.jsonl")
    for fname, rows, model in (("responses", responses, Response), ("judgements", judgements, Judgement)):
        for i, row in enumerate(rows):
            try:
                model.model_validate(row)
            except Exception as e:  # noqa: BLE001
                errs.append(f"{fname}:{i + 1}: {str(e).splitlines()[0]}")
    check("V1 schema validation", not errs, "; ".join(errs[:5]))

    bad, uncleared = [], []
    image_recs = load_jsonl(dataset / "metadata" / "images.jsonl")
    for rec in image_recs:
        p = dataset / "images" / f"{rec['image_id']}.jpg"
        if rec.get("pii_decision") != "keep":
            uncleared.append(rec["image_id"])
        if rec.get("pii_decision") == "exclude":
            continue
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != rec["shipped_sha256"]:
            bad.append(rec["image_id"])
    check("V2 image hashes", not bad, f"{len(bad)} mismatched: {bad[:5]}")
    # V7 privacy: every shipped photo was cleared in the human screening (Task P); an unscreened dataset is
    # not publishable, whatever the other checks say
    on_disk = {p.stem for p in (dataset / "images").glob("*.jpg")}
    uncleared += sorted(on_disk - {r["image_id"] for r in image_recs})
    check("V7 privacy screening", not uncleared,
          f"{len(uncleared)} shipped photo(s) not cleared by the screening: {uncleared[:3]}" if uncleared
          else f"{len(image_recs)} photos cleared")

    cases = {c["item_id"]: c for c in load_jsonl(dataset / "data" / "test_cases.jsonl")}
    lms = {l["qid"]: l for l in load_jsonl(dataset / "data" / "landmarks.jsonl")}
    ids = [r["item_id"] for r in responses]
    dup = len(ids) - len(set(ids))
    unknown = [i for i in ids if i not in cases]
    main = {i for i, c in cases.items() if c.get("split", "main") == "main"}
    missing = sorted(main - set(ids))
    check("V3 coverage", dup == 0 and not unknown, f"{len(set(ids))}/{len(main)} main items answered, "
          f"{dup} duplicates, {len(unknown)} unknown ids" + (f", {len(missing)} not in this results set" if missing else ""))

    resp = {r["item_id"]: r for r in responses}
    mism = []
    gz = load_gazetteer(dataset)
    for j in judgements:
        r = resp.get(j["item_id"])
        if r is None:
            mism.append(f"{j['item_id']}: no response")
            continue
        if sha(r["response_text"]) != j["response_sha256"]:
            mism.append(f"{j['item_id']}: response hash")
            continue
        c = cases[j["item_id"]]
        g = grade(c, lms[c["landmark_qid"]], r["response_text"], gz) if r["status"] == "ok" else None
        if (g.label if g else None) != j["code_label"]:
            mism.append(f"{j['item_id']}: code_label {j['code_label']} != recomputed {g.label if g else None}")
    check("V4 code grader reproduces stored labels", not mism, "; ".join(mism[:5]))

    rule = [j["item_id"] for j in judgements if j["final_label"] != (j["judge_label"] or j["code_label"])]
    check("V5 final-label rule", not rule, f"{len(rule)} violations")

    scores = compute_scores(dataset, results)
    (results / "scores.recomputed.json").write_text(json.dumps(scores, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                                                    encoding="utf-8")
    if expected is not None:
        exp = json.loads(expected.read_text(encoding="utf-8"))
        d = _diff(scores, exp)
        check("V6 scores match expected", not d, f"{len(d)} differences, first: {d[:3]}")
    else:
        log("  [SKIP] V6 scores match expected (no expected file given)")
    log("verify: " + ("ALL CHECKS PASSED" if ok else "FAILED"))
    return ok
