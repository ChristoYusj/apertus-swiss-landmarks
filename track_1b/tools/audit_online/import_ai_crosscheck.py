"""Write a second AI system's grades of the audit sample as an AI cross-check (NOT the human audit).

  python import_ai_crosscheck.py <CLAUDE_FINAL_AI_HANDOFF.json> <results dir> <audit_sample.json>

Writes <results>/ai_crosscheck_audit.jsonl, one row per sampled item: the AI label (null where the reviewer left
the item unscored as uncertain), its confidence and rationale. `score` reports its agreement with the judge and
the code grader under `ai_crosscheck_audit`, marked `not_a_human_audit`.
"""
import json
import sys
from pathlib import Path

src, results, sample_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
h = json.loads(src.read_text(encoding="utf-8"))
assert h.get("format") == "apertus-conservative-resolution-v1", src
sample = {s["item_id"] for s in json.loads(sample_path.read_text(encoding="utf-8"))["items"]}
rows = []
for g in h["resolved_grading"]:
    assert g["item_id"] in sample, g["item_id"]
    assert g["reviewer"].startswith("ai:"), g["reviewer"]
    assert g["label"] in (None, "correct", "incorrect", "not_attempted"), (g["item_id"], g["label"])
    rows.append({"item_id": g["item_id"], "annotator_id": g["reviewer"], "label": g["label"],
                 "confidence": g.get("confidence"), "disposition": g.get("disposition"),
                 "used_translation": bool(g.get("used_translation")), "rationale": g.get("rationale")})
assert {r["item_id"] for r in rows} == sample and len(rows) == len(sample), "the AI grades must cover the sample exactly"
with open(results / "ai_crosscheck_audit.jsonl", "w", encoding="utf-8", newline="\n") as f:
    for r in sorted(rows, key=lambda r: r["item_id"]):
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"{len(rows)} rows, {sum(1 for r in rows if r['label'])} scored -> {results / 'ai_crosscheck_audit.jsonl'}")
