"""Read a filled Grading Check PDF (build_check_pdf.py) into the human-check labels.

  python read_check_pdf.py <filled.pdf> <human_check_items.json> <results dir>     (needs pypdf)

Writes <results>/human_check.jsonl: one row per answered page with the human label (annotator A1), the AI label that
was shown, whether the human agreed with it, and the tick boxes. Pages left on "Choose..." are skipped. `score`
reports these rows under `human_check` (blind: false).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

FROM_TEXT = {"Correct": "correct", "Incorrect": "incorrect", "Not attempted": "not_attempted"}


def checked(v) -> bool:
    return str(v or "").strip("/") not in ("", "Off", "No", "None")


def read(pdf: Path, items_path: Path) -> list[dict]:
    items = json.loads(items_path.read_text(encoding="utf-8"))["items"]
    fields = {k: (v.get("/V") if hasattr(v, "get") else v) for k, v in (PdfReader(str(pdf)).get_fields() or {}).items()}
    rows = []
    for it in items:
        k = f"{it['n']:03d}"
        v = str(fields.get(f"grade_{k}") or "").strip()
        if not v or v.startswith("Choose"):
            continue
        if v.startswith("Agree with AI"):
            if not it.get("ai_label"):
                raise SystemExit(f"page {it['n']}: 'agree' chosen but no AI grade was shown")
            label, agree = it["ai_label"], True
        elif v in FROM_TEXT:
            label = FROM_TEXT[v]
            agree = (label == it["ai_label"]) if it.get("ai_label") else None
        else:
            raise SystemExit(f"page {it['n']}: unexpected value {v!r}")
        rows.append({"item_id": it["id"], "annotator_id": "A1", "label": label, "ai_label_shown": it.get("ai_label"),
                     "agreed_with_ai": agree, "used_translation": checked(fields.get(f"trans_{k}")),
                     "unsure": checked(fields.get(f"unsure_{k}")), "protocol": "human-check-v1 (not blind: the second "
                     "AI's proposed grade was shown)", "source": pdf.name})
    return rows


if __name__ == "__main__":
    pdf, items_path, results = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    rows = read(pdf, items_path)
    with open(results / "human_check.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"answered": len(rows), "labels": Counter(r["label"] for r in rows),
                      "agreed_with_ai": Counter(str(r["agreed_with_ai"]) for r in rows)}))
