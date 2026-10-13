"""Answer stability at temperature 0: is a stored answer what the endpoint gives again?

Hosted inference with batching is not bit-for-bit deterministic even at temperature 0, which is why
`verify` replays the STORED answers instead of re-querying. This check measures how much it matters:
  * rerun:  a seeded stratified sample of N items is asked once more (fresh request, no cache)
  * probe:  the first K of those are asked R more times
Reported: identical-text rate, same-code-label rate, Cohen's kappa (official vs rerun labels), and per
probe item the number of distinct answers / labels. Responses are stored in stability_responses.jsonl.
"""

from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
from collections import Counter
from pathlib import Path

from .client import Endpoint, build_messages, chat
from .analysis import load_gazetteer
from .grading.rules import grade
from .metrics import cohen_kappa, rnd, wilson
from .run import GEN_PARAMS, load_jsonl, stratified_sample, write_jsonl

SEED = 20261016


def stability(dataset: Path, results: Path, ep: Endpoint, n: int = 100, probe: int = 20, repeats: int = 2,
              workers: int = 4, log=print) -> dict:
    cases = {c["item_id"]: c for c in load_jsonl(dataset / "data" / "test_cases.jsonl")}
    lms = {l["qid"]: l for l in load_jsonl(dataset / "data" / "landmarks.jsonl")}
    official = {r["item_id"]: r for r in load_jsonl(results / "responses.jsonl") if r["status"] == "ok"}
    pool = [c for c in cases.values() if c["item_id"] in official]
    sample = stratified_sample(pool, n, seed=SEED)[:n]
    jobs = [(c, 1) for c in sample] + [(c, k) for c in sample[:probe] for k in range(2, repeats + 2)]
    log(f"stability: {len(sample)} items rerun once, {min(probe, len(sample))} of them {repeats} more times "
        f"({len(jobs)} requests to {ep.model})")

    def ask(job):
        c, k = job
        img = (dataset / "images" / f"{c['image_id']}.jpg").read_bytes() if c.get("image_id") else None
        res = chat(ep, build_messages(c["question_text"], img), GEN_PARAMS)
        return {"item_id": c["item_id"], "repeat": k, "model": ep.model, "status": res.status,
                "response_text": res.text, "finish_reason": res.finish_reason, "error": res.error,
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(ask, jobs))
    write_jsonl(results / "stability_responses.jsonl", rows)

    gz = load_gazetteer(dataset)

    def label(item_id, text):
        c = cases[item_id]
        return grade(c, lms[c["landmark_qid"]], text, gz).label

    ok = [r for r in rows if r["status"] == "ok"]
    first = [r for r in ok if r["repeat"] == 1]
    same_text = sum(r["response_text"] == official[r["item_id"]]["response_text"] for r in first)
    a = [label(r["item_id"], official[r["item_id"]]["response_text"]) for r in first]
    b = [label(r["item_id"], r["response_text"]) for r in first]
    same_label = sum(x == y for x, y in zip(a, b))
    probe_items = []
    for c in sample[:probe]:
        answers = [official[c["item_id"]]["response_text"]] + [r["response_text"] for r in ok if r["item_id"] == c["item_id"]]
        probe_items.append({"item_id": c["item_id"], "n_answers": len(answers), "distinct_texts": len(set(answers)),
                            "distinct_labels": len({label(c["item_id"], t) for t in answers})})
    report = {
        "model": ep.model, "params": GEN_PARAMS, "seed": SEED, "requests": len(jobs), "api_errors": len(rows) - len(ok),
        "rerun_n": len(first),
        "identical_text_rate": rnd(same_text / len(first)) if first else None,
        "identical_text_ci95": wilson(same_text, len(first)),
        "same_code_label_rate": rnd(same_label / len(first)) if first else None,
        "same_code_label_ci95": wilson(same_label, len(first)),
        "kappa_official_vs_rerun": rnd(cohen_kappa(a, b)) if first else None,
        "label_transitions": {f"{x}->{y}": k for (x, y), k in sorted(Counter(zip(a, b)).items()) if x != y},
        "by_arm_identical_text": {arm: f"{sum(r['response_text'] == official[r['item_id']]['response_text'] for r in first if cases[r['item_id']]['arm'] == arm)}"
                                       f"/{sum(cases[r['item_id']]['arm'] == arm for r in first)}"
                                  for arm in sorted({cases[r['item_id']]['arm'] for r in first})},
        "probe": {"items": len(probe_items), "answers_per_item": repeats + 2,
                  "items_all_identical": sum(p["distinct_texts"] == 1 for p in probe_items),
                  "items_label_always_same": sum(p["distinct_labels"] == 1 for p in probe_items),
                  "detail": probe_items},
    }
    (results / "stability.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return report
