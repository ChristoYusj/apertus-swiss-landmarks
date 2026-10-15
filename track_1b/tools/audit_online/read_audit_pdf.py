"""Read the three filled blind audit PDFs (protocol audit-v4) into <results>/human_audit.jsonl.

  python read_audit_pdf.py <assignment.json> <results dir> A1=<file.pdf> A2=<file.pdf> A3=<file.pdf>   (needs pypdf)

One row per answered page: item_id, annotator_id, label, used_translation, unsure, in_overlap. Pages left on
"Choose..." are skipped and counted. The item order of each PDF comes from items_<ID>.json next to assignment.json.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

LABEL = {"Correct": "correct", "Incorrect": "incorrect", "Not attempted": "not_attempted"}


def checked(v) -> bool:
    return str(v or "").strip("/") not in ("", "Off", "No", "None")


def main() -> None:
    assignment_path, results = Path(sys.argv[1]), Path(sys.argv[2])
    assignment = json.loads(assignment_path.read_text(encoding="utf-8"))
    overlap = set(assignment["overlap"])
    rows, report = [], {}
    for arg in sys.argv[3:]:
        who, pdf = arg.split("=", 1)
        items = json.loads((assignment_path.parent / f"items_{who}.json").read_text(encoding="utf-8"))["items"]
        fields = {k: (v.get("/V") if hasattr(v, "get") else v) for k, v in (PdfReader(pdf).get_fields() or {}).items()}
        answered = 0
        for it in items:
            k = f"{it['n']:03d}"
            v = str(fields.get(f"grade_{k}") or "").strip()
            if v not in LABEL:
                continue
            answered += 1
            rows.append({"item_id": it["id"], "annotator_id": who, "label": LABEL[v],
                         "used_translation": checked(fields.get(f"trans_{k}")), "unsure": checked(fields.get(f"unsure_{k}")),
                         "in_overlap": it["id"] in overlap, "protocol": "audit-v4 (blind, three annotators)",
                         "source": Path(pdf).name})
        report[who] = {"pages": len(items), "answered": answered,
                       "labels": dict(Counter(r["label"] for r in rows if r["annotator_id"] == who))}
    with open(results / "human_audit.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
