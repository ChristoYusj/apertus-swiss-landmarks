"""Agreement between the human audit (Task G), the LLM judge and the code grader (analysis_plan.md, "Human audit").

The human label of an item is the annotator's label; on an item labelled by three annotators it is the majority
of the three (no majority -> left out of the human-vs-grader comparisons, counted as "no_majority"). As run
(audit-v4), human_audit.jsonl holds one label per item, all by one annotator (A1); the repeat labels of the 30
shared items are in human_audit_repeat.jsonl.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from .metrics import LABELS, cohen_kappa, fleiss_kappa


def _confusion(pairs):
    m = {a: {b: 0 for b in LABELS} for a in LABELS}
    for a, b in pairs:
        m[a][b] += 1
    return m


def _compare(items, key):
    pairs = [(it["human"], it[key]) for it in items if it["human"] and it[key]]
    if not pairs:
        return None
    return {"n": len(pairs), "cohen_kappa": cohen_kappa([a for a, _ in pairs], [b for _, b in pairs]),
            "raw_agreement": sum(a == b for a, b in pairs) / len(pairs),
            "confusion_human_rows": _confusion(pairs)}


def agreement(human_rows: list[dict], judgements: dict, cases: dict) -> dict:
    by_item = defaultdict(list)
    for r in human_rows:
        by_item[r["item_id"]].append(r)
    items, no_majority = [], 0
    for iid, rs in sorted(by_item.items()):
        labels = [r["label"] for r in rs]
        if len(labels) == 1:
            human = labels[0]
        else:
            top, k = Counter(labels).most_common(1)[0]
            human = top if k >= 2 else None
            no_majority += human is None
        j = judgements.get(iid, {})
        items.append({"item_id": iid, "lang": cases[iid]["lang"], "human": human, "judge": j.get("judge_label"),
                      "code": j.get("code_label"), "n_raters": len(labels)})
    overlap = [[r["label"] for r in sorted(rs, key=lambda r: r["annotator_id"])]
               for rs in by_item.values() if len(rs) == 3]
    out = {
        "items": len(items), "labels": len(human_rows), "overlap_items_complete": len(overlap),
        "overlap_no_majority": no_majority,
        "fleiss_kappa_3_humans": fleiss_kappa(overlap) if overlap else None,
        "raw_agreement_3_humans": (sum(len(set(t)) == 1 for t in overlap) / len(overlap)) if overlap else None,
        "judge_vs_human": _compare(items, "judge"), "code_vs_human": _compare(items, "code"),
        "judge_vs_code_on_audit_items": None,
        "used_translation_rate": sum(r.get("used_translation", False) for r in human_rows) / len(human_rows) if human_rows else None,
        "unsure_rate": sum(r.get("unsure", False) for r in human_rows) / len(human_rows) if human_rows else None,
        "by_lang": {},
    }
    jc = [(it["judge"], it["code"]) for it in items if it["judge"] and it["code"]]
    if jc:
        out["judge_vs_code_on_audit_items"] = {"n": len(jc), "cohen_kappa": cohen_kappa([a for a, _ in jc], [b for _, b in jc])}
    for lang in sorted({it["lang"] for it in items}):
        sub = [it for it in items if it["lang"] == lang]
        out["by_lang"][lang] = {"n": len(sub), "judge_vs_human": _short(_compare(sub, "judge")),
                                "code_vs_human": _short(_compare(sub, "code"))}
    return out


def self_consistency(first_rows: list[dict], repeat_rows: list[dict]) -> dict | None:
    """Agreement of one annotator with their own repeat labels of the same items (designed for protocol v3's hidden
    repeats; as run, the repeats are the 30 shared items of audit-v4, a known overlap, so not a blind test-retest)."""
    first = {(r["item_id"], r["annotator_id"]): r["label"] for r in first_rows}
    pairs = [(first[(r["item_id"], r["annotator_id"])], r["label"]) for r in repeat_rows
             if (r["item_id"], r["annotator_id"]) in first]
    if not pairs:
        return None
    return {"n": len(pairs), "raw_agreement": sum(a == b for a, b in pairs) / len(pairs),
            "cohen_kappa": cohen_kappa([a for a, _ in pairs], [b for _, b in pairs]),
            "changes": {f"{a}->{b}": n for (a, b), n in sorted(Counter(pairs).items()) if a != b}}


def _short(c):
    return None if c is None else {k: c[k] for k in ("n", "cohen_kappa", "raw_agreement")}
