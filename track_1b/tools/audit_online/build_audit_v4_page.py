"""Online page for the blind grading audit (protocol audit-v4): the same items as the blind PDFs.

  python build_audit_v4_page.py <dir with items_A1.json ... items_A3.json> <out dir>

Writes <out>/index.html from audit_v4.html: each annotator picks an ID and sees only their own 194 items, with no
grade of any kind. Labels are stored per (annotator, item) in the artifact database (collection `audit4`, doc id
`<ID>__<item_id>`, fields a, item, label, used_translation, unsure, t), or downloaded as audit_labels_<ID>.json when
the viewer cannot write. `merge_audit_v4.py` turns either into <results>/human_audit.jsonl.
"""

import json
import sys
from pathlib import Path

src, out = Path(sys.argv[1]), Path(sys.argv[2])
data = {}
for who in ("A1", "A2", "A3"):
    items = json.loads((src / f"items_{who}.json").read_text(encoding="utf-8"))["items"]
    assert not any(k in it for it in items for k in ("ai_label", "judge_label", "code_label")), "the page must stay blind"
    data[who] = items
page = (Path(__file__).parent / "audit_v4.html").read_text(encoding="utf-8")
out.mkdir(parents=True, exist_ok=True)
payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
(out / "index.html").write_text(page.replace("__DATA__", payload), encoding="utf-8", newline="\n")
print({who: len(v) for who, v in data.items()}, round((out / "index.html").stat().st_size / 1e6, 2), "MB")
