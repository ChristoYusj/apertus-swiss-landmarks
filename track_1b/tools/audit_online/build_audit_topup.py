"""Grading audit top-up (16 Oct): bring the human check to 20 % of the 70B core answers, stratum by stratum.

  python build_audit_topup.py draw  <dataset> <results> <out dir>
  python build_audit_topup.py page  <out dir>                       (needs the glosses: landmarks-eval glosses)
  python build_audit_topup.py merge <out dir> <results> <labels.json> [<labels.json> ...]

draw: the 70B core answers (arms photo_main, photo_alt, text_only, trap_premise, trap_lowinfo) are split into the
original audit strata (arm x language x judge label); in every stratum, answers not yet human-labelled are drawn
(seed 20261020) until the stratum's human-labelled share reaches 20 % (rounded up). The existing labels are kept as
they are, so the union is a stratified 20 % sample of the current core answers. Writes topup_sample.json (format of
audit_sample.json, for the glosses) and items_A1.json (blind: no grade of any kind; own seeded order).
page: writes the online page (audit_v4.html, one annotator) to <out>/page/index.html.
merge: appends the labels (online page database documents of collection `audit4`, or a downloaded
audit_labels_A1.json) to <results>/human_audit.jsonl as protocol "audit-v4 top-up"; refuses items outside the draw.
"""

from __future__ import annotations

import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

from landmarks_eval.build.audit import _q_gloss
from landmarks_eval.grading.judge import gold_text
from landmarks_eval.run import load_jsonl

SEED, SHARE = 20261020, 0.20
CORE = ("photo_main", "photo_alt", "text_only", "trap_premise", "trap_lowinfo")
LABELS = {"correct", "incorrect", "not_attempted"}


def draw(dataset: Path, results: Path, out: Path) -> dict:
    cases = {c["item_id"]: c for c in load_jsonl(dataset / "data" / "test_cases.jsonl")}
    lms = {l["qid"]: l for l in load_jsonl(dataset / "data" / "landmarks.jsonl")}
    resp = {r["item_id"]: r for r in load_jsonl(results / "responses.jsonl")}
    judg = {j["item_id"]: j for j in load_jsonl(results / "judgements.jsonl")}
    done = {h["item_id"] for h in load_jsonl(results / "human_audit.jsonl")}
    strata: dict[tuple, list[str]] = defaultdict(list)
    for iid, c in cases.items():
        if c["arm"] in CORE and iid in resp:
            j = judg[iid]
            strata[(c["arm"], c["lang"], j.get("judge_label") or j["code_label"])].append(iid)
    rng = random.Random(SEED)
    picked, per = [], {}
    for key in sorted(strata):
        ids = sorted(strata[key])
        have = sum(i in done for i in ids)
        need = max(0, math.ceil(SHARE * len(ids)) - have)
        pool = [i for i in ids if i not in done]
        rng.shuffle(pool)
        take = sorted(pool[:need])
        picked += take
        per["|".join(key)] = {"n": len(ids), "already": have, "drawn": len(take)}
    total = sum(len(v) for v in strata.values())
    out.mkdir(parents=True, exist_ok=True)
    sample = {"protocol": "audit-v4 top-up: stratified, to 20 % of the 70B core answers", "seed": SEED, "share": SHARE,
              "core_answers": total, "already_labelled_in_dataset": sum(i in done for v in strata.values() for i in v),
              "n_sample": len(picked), "strata": per,
              "items": [{"item_id": i, "stratum": "|".join((cases[i]["arm"], cases[i]["lang"],
                                                              judg[i].get("judge_label") or judg[i]["code_label"]))}
                        for i in picked]}
    (out / "topup_sample.json").write_text(json.dumps(sample, indent=1), encoding="utf-8", newline="\n")
    order = list(picked)
    random.Random(SEED + 1).shuffle(order)
    items = [{"id": iid, "n": n, "lang": cases[iid]["lang"], "arm": cases[iid]["arm"],
              "qtype": cases[iid]["question_type"], "question": cases[iid]["question_text"],
              "q_gloss": _q_gloss(cases[iid]), "gold": gold_text(cases[iid], lms[cases[iid]["landmark_qid"]]),
              "answer": resp[iid]["response_text"] or "", "a_gloss": None} for n, iid in enumerate(order, 1)]
    (out / "items_A1.json").write_text(json.dumps({"annotator": "A1", "items": items}, ensure_ascii=False, indent=1),
                                       encoding="utf-8", newline="\n")
    return {"core_answers": total, "target": math.ceil(SHARE * total), "drawn": len(picked),
            "labelled_after": sample["already_labelled_in_dataset"] + len(picked)}


def page(out: Path, results: Path) -> dict:
    gloss = {g["item_id"]: g["gloss_en"] for g in load_jsonl(results / "glosses.jsonl")}
    data = json.loads((out / "items_A1.json").read_text(encoding="utf-8"))
    for it in data["items"]:
        it["a_gloss"] = gloss.get(it["id"])
    assert not any(k in it for it in data["items"] for k in ("ai_label", "judge_label", "code_label")), "must stay blind"
    html = (Path(__file__).parent / "audit_v4.html").read_text(encoding="utf-8")
    who = ('<button type="button" data-who="A1">A1</button> <button type="button" data-who="A2">A2</button> '
           '<button type="button" data-who="A3">A3</button>')
    assert html.count(who) == 1
    html = html.replace(who, '<button type="button" data-who="A1">A1</button>')
    payload = json.dumps({"A1": data["items"], "A2": [], "A3": []}, ensure_ascii=False).replace("</", "<\\/")
    (out / "page").mkdir(parents=True, exist_ok=True)
    (out / "page" / "index.html").write_text(html.replace("__DATA__", payload), encoding="utf-8", newline="\n")
    non_fr = [it for it in data["items"] if it["lang"] != "fr" and it["answer"].strip()]
    return {"items": len(data["items"]), "non_french": len(non_fr), "glossed": sum(1 for it in non_fr if it["a_gloss"])}


def merge(out: Path, results: Path, sources: list[Path]) -> dict:
    allowed = {i["item_id"] for i in json.loads((out / "topup_sample.json").read_text(encoding="utf-8"))["items"]}
    have = {h["item_id"] for h in load_jsonl(results / "human_audit.jsonl")}
    best: dict[str, dict] = {}
    for src in sources:
        data = json.loads(src.read_text(encoding="utf-8"))
        rows = ([{"a": data["annotator"], "item": k, **v} for k, v in data["labels"].items()]
                if isinstance(data, dict) and data.get("format") == "audit-v4-labels"
                else [d.get("data", d) for d in data])
        for r in rows:
            if r.get("a") != "A1" or r["item"] not in allowed:
                raise SystemExit(f"{src}: {r.get('a')} labelled {r['item']}, which is not in the top-up draw")
            if r.get("label") in LABELS and (r["item"] not in best or (r.get("t") or "") >= (best[r["item"]].get("t") or "")):
                best[r["item"]] = r
    new = [{"item_id": i, "annotator_id": "A1", "label": r["label"], "used_translation": bool(r.get("used_translation")),
            "unsure": bool(r.get("unsure")), "in_overlap": False, "part": "topup", "labelled_at": r.get("t"),
            "protocol": "audit-v4 top-up (16 Oct): one annotator, blind PDF"}
           for i, r in sorted(best.items()) if i not in have]
    with open(results / "human_audit.jsonl", "a", encoding="utf-8", newline="\n") as f:
        for r in new:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"drawn": len(allowed), "labelled": len(best), "appended": len(new), "missing": len(allowed - set(best))}


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "draw":
        print(json.dumps(draw(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])), indent=1))
    elif cmd == "page":
        print(json.dumps(page(Path(sys.argv[2]), Path(sys.argv[3])), indent=1))
    elif cmd == "merge":
        print(json.dumps(merge(Path(sys.argv[2]), Path(sys.argv[3]), [Path(p) for p in sys.argv[4:]]), indent=1))
    else:
        raise SystemExit(__doc__)
