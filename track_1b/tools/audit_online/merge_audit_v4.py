"""Merge the blind audit labels (protocol audit-v4) into <results>/human_audit.jsonl.

  python merge_audit_v4.py <assignment.json> <results dir> <source> [<source> ...]

A source is either a JSON list of database documents from the online page (collection `audit4`; each with the
fields a, item, label, used_translation, unsure, t) or a downloaded audit_labels_<ID>.json (format
audit-v4-labels). The latest label per (annotator, item) wins. Items outside an annotator's assignment are
refused, so a label can never be credited to the wrong person.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

LABELS = {"correct", "incorrect", "not_attempted"}


def rows_from(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and data.get("format") == "audit-v4-labels":
        return [{"a": data["annotator"], "item": k, **v} for k, v in data["labels"].items()]
    if isinstance(data, list):
        return [d.get("data", d) for d in data]
    raise SystemExit(f"{path}: unknown format")


def main() -> None:
    assignment_path, results = Path(sys.argv[1]), Path(sys.argv[2])
    assignment = json.loads(assignment_path.read_text(encoding="utf-8"))
    overlap = set(assignment["overlap"])
    allowed = {a: set(items) | overlap for a, items in assignment["parts"].items()}
    best: dict[tuple, dict] = {}
    for src in sys.argv[3:]:
        for r in rows_from(Path(src)):
            a, item = r["a"], r["item"]
            if item not in allowed.get(a, set()):
                raise SystemExit(f"{src}: {a} labelled {item}, which is not in {a}'s assignment")
            if r.get("label") not in LABELS:
                continue
            if (a, item) not in best or (r.get("t") or "") >= (best[(a, item)].get("t") or ""):
                best[(a, item)] = r
    rows = [{"item_id": item, "annotator_id": a, "label": r["label"], "used_translation": bool(r.get("used_translation")),
             "unsure": bool(r.get("unsure")), "in_overlap": item in overlap, "labelled_at": r.get("t"),
             "protocol": "audit-v4 (blind, three annotators)"} for (a, item), r in sorted(best.items())]
    with open(results / "human_audit.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    per = Counter(r["annotator_id"] for r in rows)
    print(json.dumps({"labels": len(rows), "per_annotator": per,
                      "overlap_complete": sum(1 for i in overlap if all((a, i) in best for a in allowed))}, indent=1))


if __name__ == "__main__":
    main()
