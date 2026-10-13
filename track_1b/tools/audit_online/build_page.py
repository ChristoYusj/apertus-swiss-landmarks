"""Build the online version of the grading-audit page (Task G) from the drawn audit sample.

Same items, orders and blindness as the offline page (`landmarks-eval audit-page`): no judge or code labels are
in the page, and each annotator only ever sees their own labels. Published as a private claude.ai artifact with
the `db` capability: one document per (annotator, item) in the collection `audit` (fields a, item, label,
used_translation, unsure, t); viewers who cannot write keep labels on their device and download
audit_labels_<ID>.json (same `audit-v1` format as the offline page), which `landmarks-eval merge-audit` reads.

    python tools/audit_online/build_page.py --dataset work/dataset --results work/dataset/responses/apertus-v1.5-70b --out <dir>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from landmarks_eval.build.audit import GUIDELINE_VERSION, page_data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    dev = a.results / "judge_dev_set.jsonl"
    dev_ids = {json.loads(l)["item_id"] for l in open(dev, encoding="utf-8")} if dev.exists() else set()
    data, sample = page_data(a.dataset, a.results, dev_ids)
    template = (Path(__file__).parent / "audit.html").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "index.html").write_text(template.replace("__DATA__", payload).replace("__VERSION__", GUIDELINE_VERSION),
                                      encoding="utf-8")
    (a.out / "audit_sample.json").write_text(json.dumps(sample, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in sample.items() if k != "items"}, indent=1))


if __name__ == "__main__":
    main()
