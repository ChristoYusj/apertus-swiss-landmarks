"""Read a filled photo-check PDF (build_photo_check_pdf.py): which published photos a person flagged.

  python read_photo_check_pdf.py <filled.pdf> <out.json>        (needs pypdf)

Writes {"checked_by": "A1", "photos": N, "flagged": [image ids]}. A flagged main photo removes its landmark; a
flagged 2nd view or too-generic photo removes only that photo (the screening rules, docs/annotation_guidelines.md).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pypdf import PdfReader

pdf, out = Path(sys.argv[1]), Path(sys.argv[2])
fields = PdfReader(str(pdf)).get_fields() or {}
boxes = {k[len("prob_"):]: v.get("/V") for k, v in fields.items() if k.startswith("prob_")}
flagged = sorted(i for i, v in boxes.items() if str(v or "").strip("/") not in ("", "Off", "No", "None"))
res = {"checked_by": "A1", "source": pdf.name, "photos": len(boxes), "flagged": flagged}
out.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(res, indent=1))
