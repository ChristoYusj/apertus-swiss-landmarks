"""Build the human check of the AI cross-check grades (NOT blind: the second AI's proposed grade is shown).

The items are the first N of annotator A1's seeded order of the pre-registered audit sample (`audit_sample.json`,
the same order as the blind audit page), skipping items whose landmark the photo screening removed. For each item
the page shows the question, the gold answer, the model answer (with the English gloss) and the second AI's grade
and reason; the annotator agrees or picks another label. The labels are stored per item in the artifact database
(collection `hcheck`) and merged into `human_check.jsonl`; `score` reports them under `human_check` (blind: false).

    python tools/audit_online/build_check.py <dataset> <results> <audit_sample.json> <ai_crosscheck_audit.jsonl> <out dir> [N]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from landmarks_eval.build.audit import REPEAT_SUFFIX, _orders, _q_gloss
from landmarks_eval.grading.judge import gold_text
from landmarks_eval.run import load_jsonl

dataset, results, sample_path, ai_path, out = (Path(a) for a in sys.argv[1:6])
n = int(sys.argv[6]) if len(sys.argv) > 6 else 150
sample = json.loads(sample_path.read_text(encoding="utf-8"))
orders, _ = _orders(sample)
order = [i for i in orders["A1"] if not i.endswith(REPEAT_SUFFIX)]
cases = {c["item_id"]: c for c in load_jsonl(dataset / "data" / "test_cases.jsonl")}
lms = {l["qid"]: l for l in load_jsonl(dataset / "data" / "landmarks.jsonl")}
resp = {r["item_id"]: r for r in load_jsonl(results / "responses.jsonl")}
gloss = {g["item_id"]: g["gloss_en"] for g in load_jsonl(results / "glosses.jsonl")}
ai = {r["item_id"]: r for r in load_jsonl(ai_path)}
items, skipped = [], 0
for iid in order:
    if iid not in cases or iid not in resp:
        skipped += 1                                  # landmark removed by the photo screening
        continue
    c, a = cases[iid], ai.get(iid, {})
    items.append({"id": iid, "n": len(items) + 1, "lang": c["lang"], "arm": c["arm"], "qtype": c["question_type"],
                  "question": c["question_text"], "q_gloss": _q_gloss(c), "gold": gold_text(c, lms[c["landmark_qid"]]),
                  "answer": resp[iid]["response_text"] or "", "a_gloss": gloss.get(iid),
                  "ai_label": a.get("label"), "ai_reason": a.get("rationale") or "", "ai_who": a.get("annotator_id")})
    if len(items) == n:
        break
out.mkdir(parents=True, exist_ok=True)
page = (Path(__file__).parent / "human_check.html").read_text(encoding="utf-8")
payload = json.dumps({"items": items}, ensure_ascii=False).replace("</", "<\\/")
(out / "human_check.html").write_text(page.replace("__DATA__", payload), encoding="utf-8", newline="\n")
(out / "human_check_items.json").write_text(json.dumps({"items": items}, ensure_ascii=False, indent=1), encoding="utf-8",
                                            newline="\n")   # the same items for the PDF form (build_check_pdf.py)
print(json.dumps({"items": len(items), "skipped_dropped_landmarks": skipped, "first": items[0]["id"],
                  "without_ai_label": sum(1 for i in items if not i["ai_label"]),
                  "by_lang": {l: sum(1 for i in items if i["lang"] == l) for l in ("fr", "de", "it", "rm")}}))
