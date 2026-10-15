"""Grading audit protocol v4 (15 Oct): three annotators, blind, with a shared overlap for inter-annotator agreement.

The pre-registered audit sample (`audit_sample.json`, a seeded, stratified 20 % of the 70B answers; drawn before
the photo screening) minus the items whose landmark the screening removed is split, seeded, into
  - an overlap of OVERLAP items that every annotator labels (Fleiss' kappa between the three), and
  - three disjoint parts of the rest, one per annotator (A1, A2, A3),
each annotator's items in their own seeded order. No grade (judge, code or AI cross-check) is in the items.

    python build_audit_v4.py <dataset> <results> <audit_sample.json> <out dir>

Writes <out>/assignment.json and <out>/items_A1.json ... items_A3.json (input for build_check_pdf.py --blind).

As registered: three annotators. As run: one person (A1) labelled all three parts, so there is no agreement between
people; the labels were merged with merge_audit_v4.py --one-annotator A1.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from landmarks_eval.build.audit import _q_gloss
from landmarks_eval.grading.judge import gold_text
from landmarks_eval.run import load_jsonl

SEED, OVERLAP, ANNOTATORS = 20261018, 30, ("A1", "A2", "A3")

dataset, results, sample_path, out = (Path(a) for a in sys.argv[1:5])
sample = json.loads(sample_path.read_text(encoding="utf-8"))
cases = {c["item_id"]: c for c in load_jsonl(dataset / "data" / "test_cases.jsonl")}
lms = {l["qid"]: l for l in load_jsonl(dataset / "data" / "landmarks.jsonl")}
resp = {r["item_id"]: r for r in load_jsonl(results / "responses.jsonl")}
gloss = {g["item_id"]: g["gloss_en"] for g in load_jsonl(results / "glosses.jsonl")}
ids = sorted(s["item_id"] for s in sample["items"] if s["item_id"] in cases and s["item_id"] in resp)
rng = random.Random(SEED)
rng.shuffle(ids)
overlap, rest = sorted(ids[:OVERLAP]), ids[OVERLAP:]
parts = {a: sorted(rest[k::len(ANNOTATORS)]) for k, a in enumerate(ANNOTATORS)}
assignment = {"protocol": "audit-v4: three annotators, blind, seeded split", "seed": SEED,
              "sample_items_in_dataset": len(ids), "dropped_with_landmark": len(sample["items"]) - len(ids),
              "overlap": overlap, "parts": parts}
out.mkdir(parents=True, exist_ok=True)
(out / "assignment.json").write_text(json.dumps(assignment, indent=1), encoding="utf-8", newline="\n")
for k, a in enumerate(ANNOTATORS):
    mine = parts[a] + overlap
    random.Random(SEED + 1 + k).shuffle(mine)
    items = []
    for n, iid in enumerate(mine, 1):
        c = cases[iid]
        items.append({"id": iid, "n": n, "lang": c["lang"], "arm": c["arm"], "qtype": c["question_type"],
                      "question": c["question_text"], "q_gloss": _q_gloss(c), "gold": gold_text(c, lms[c["landmark_qid"]]),
                      "answer": resp[iid]["response_text"] or "", "a_gloss": gloss.get(iid)})   # NO grade of any kind
    (out / f"items_{a}.json").write_text(json.dumps({"annotator": a, "items": items}, ensure_ascii=False, indent=1),
                                         encoding="utf-8", newline="\n")
print(json.dumps({"in_dataset": len(ids), "overlap": len(overlap), **{a: len(parts[a]) + len(overlap) for a in ANNOTATORS}}))
