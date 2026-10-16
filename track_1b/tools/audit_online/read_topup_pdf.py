"""Read the filled blind top-up PDF (build_check_pdf.py --blind on work/audit/topup/items_A1.json) into labels.

  python read_topup_pdf.py <items_A1.json> <filled.pdf> <out audit_labels_A1.json>     (needs pypdf)

Writes format audit-v4-labels (annotator A1), the input of `build_audit_topup.py merge`. Pages left on "Choose..."
are skipped and counted. The label time is the PDF's file modification time (the PDF has no per-field times).
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from pypdf import PdfReader

LABEL = {"Correct": "correct", "Incorrect": "incorrect", "Not attempted": "not_attempted"}


def ticked(v) -> bool:
    return str(v or "").strip("/") not in ("", "Off", "No", "None")


items_path, pdf, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
items = json.loads(items_path.read_text(encoding="utf-8"))["items"]
fields = {k: (v.get("/V") if hasattr(v, "get") else v) for k, v in (PdfReader(str(pdf)).get_fields() or {}).items()}
saved = dt.datetime.fromtimestamp(pdf.stat().st_mtime).astimezone().isoformat(timespec="seconds")
labels, empty = {}, 0
for it in items:
    k = f"{it['n']:03d}"
    label = LABEL.get(str(fields.get(f"grade_{k}") or "").strip("/"))
    if not label:
        empty += 1
        continue
    labels[it["id"]] = {"label": label, "used_translation": ticked(fields.get(f"trans_{k}")),
                        "unsure": ticked(fields.get(f"unsure_{k}")), "t": saved}
res = {"format": "audit-v4-labels", "annotator": "A1", "source": pdf.name, "exported_at": saved,
       "saved_at_source": "file modification time of the returned PDF", "complete": len(labels), "total": len(items),
       "labels": labels}
out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
print(json.dumps({"labelled": len(labels), "left_empty": empty, "total": len(items)}))
