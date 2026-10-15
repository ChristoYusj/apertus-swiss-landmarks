"""Judge dev set: run the LLM judge on the 40 dev items before the judge prompt is frozen. Their labels
(`confirmed_label`) were proposed by Claude; the team lead ruled on 4 hard cases and accepted the other 36 without
item-by-item review. Reports agreement with these labels (and with the code grader) and lists every disagreement,
so prompt changes are made on these 40 items only and never on the audit sample (which is drawn afterwards).
Writes <results>/judge_dev_eval.json.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import os
from collections import Counter
from pathlib import Path

from .client import Endpoint
from .grading import judge as J
from .metrics import cohen_kappa, rnd
from .run import load_jsonl
from .score import load_dataset


def judge_dev(dataset: Path, results: Path, ep: Endpoint, log=print) -> dict:
    cases, lms = load_dataset(dataset)
    dev = load_jsonl(results / "judge_dev_set.jsonl")
    resp = {r["item_id"]: r for r in load_jsonl(results / "responses.jsonl")}
    code = {j["item_id"]: j for j in load_jsonl(results / "judgements.jsonl")}

    def one(d):
        c = cases[d["item_id"]]
        return J.judge(ep, c, lms[c["landmark_qid"]], resp[d["item_id"]]["response_text"])

    with cf.ThreadPoolExecutor(max_workers=int(os.environ.get("JUDGE_CONCURRENCY", "4"))) as ex:
        verdicts = list(ex.map(one, dev))
    items = []
    for d, (label, _place, raw, _h) in zip(dev, verdicts):
        items.append({"item_id": d["item_id"], "confirmed": d["confirmed_label"], "judge": label,
                      "code": code.get(d["item_id"], {}).get("code_label"), "answer": resp[d["item_id"]]["response_text"],
                      "judge_raw": raw, "confirmed_by": d.get("confirmed_by")})
    labelled = [i for i in items if i["judge"]]
    agree = sum(i["judge"] == i["confirmed"] for i in labelled)
    report = {
        "judge_model": ep.model, "judge_prompt_version": J.JUDGE_PROMPT_VERSION, "judge_params": J.JUDGE_PARAMS,
        "n": len(items), "n_unparsed": len(items) - len(labelled),
        "agreement_with_confirmed": rnd(agree / len(labelled)) if labelled else None,
        "kappa_with_confirmed": rnd(cohen_kappa([i["confirmed"] for i in labelled], [i["judge"] for i in labelled])),
        "agreement_code_with_confirmed": rnd(sum(i["code"] == i["confirmed"] for i in items) / len(items)),
        "confusion_confirmed_to_judge": {f"{a}->{b}": n for (a, b), n in
                                         sorted(Counter((i["confirmed"], i["judge"]) for i in items).items())},
        "disagreements": [i for i in items if i["judge"] != i["confirmed"]],
        "items": items,
    }
    (results / "judge_dev_eval.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"judge dev set: {agree}/{len(labelled)} agree with the confirmed labels "
        f"(kappa {report['kappa_with_confirmed']}; code grader {report['agreement_code_with_confirmed']}); "
        f"{report['n_unparsed']} unparsed")
    return report
