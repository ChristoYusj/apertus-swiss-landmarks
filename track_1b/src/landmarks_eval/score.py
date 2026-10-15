"""Grade responses (code grader on 100 %, judge on 100 % when available) and compute scores.json."""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path

from .analysis import hypotheses, load_gazetteer, location_analysis
from .client import Endpoint
from .grading import judge as J
from .grading.rules import grade
from .metrics import cluster_bootstrap, cohen_kappa, rates, rnd, wilson
from .run import load_jsonl, write_jsonl
from .schema import Judgement


def sha(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def load_dataset(dataset: Path) -> tuple[dict, dict]:
    cases = {c["item_id"]: c for c in load_jsonl(dataset / "data" / "test_cases.jsonl")}
    lms = {l["qid"]: l for l in load_jsonl(dataset / "data" / "landmarks.jsonl")}
    return cases, lms


def grade_all(dataset: Path, results: Path, judge_ep: Endpoint | None = None, log=print) -> Path:
    cases, lms = load_dataset(dataset)
    responses = load_jsonl(results / "responses.jsonl")
    jpath = results / "judgements.jsonl"
    cached = {j["item_id"]: j for j in load_jsonl(jpath)} if jpath.exists() else {}
    out = []
    n_judged = n_cached = 0
    gz = load_gazetteer(dataset)
    todo = []                                     # (row index, case, lm, response) still to be judged
    for r in responses:
        case, lm = cases[r["item_id"]], lms[cases[r["item_id"]]["landmark_qid"]]
        cg = grade(case, lm, r["response_text"], gz) if r["status"] == "ok" else None
        row = {"item_id": r["item_id"], "response_sha256": sha(r["response_text"]),
               "code_label": cg.label if cg else None, "code_rule": cg.rule if cg else f"status:{r['status']}",
               "canton_correct": cg.canton_correct if cg else None,
               "municipality_correct": cg.municipality_correct if cg else None,
               "year_within_window": cg.year_within_window if cg else None,
               "judge_label": None, "judge_raw": None, "judge_model": None, "judge_prompt_version": None,
               "predicted_place": None}
        prev = cached.get(r["item_id"])
        if prev and prev.get("judge_label") and prev["response_sha256"] == row["response_sha256"] \
                and prev.get("judge_prompt_version") == J.JUDGE_PROMPT_VERSION:
            for k in ("judge_label", "judge_raw", "judge_model", "judge_prompt_version", "predicted_place"):
                row[k] = prev[k]
            n_cached += 1
        elif judge_ep and r["status"] == "ok":
            todo.append((len(out), case, lm, r["response_text"]))
        out.append(row)

    def finish(rows):
        for row in rows:
            row["final_label"] = row["judge_label"] or row["code_label"]
            row["final_source"] = "judge" if row["judge_label"] else ("code" if row["code_label"] else "none")
            Judgement.model_validate(row)

    # judge calls in parallel (JUDGE_CONCURRENCY, default 4); the file is written after every chunk, so an
    # interrupted run resumes from the cache (only labelled judgements are reused)
    workers = int(os.environ.get("JUDGE_CONCURRENCY", "4"))
    for start in range(0, len(todo), 200):
        chunk = todo[start:start + 200]
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(lambda t: J.judge(judge_ep, t[1], t[2], t[3]), chunk))
        for (i, *_), (label, place, raw, _h) in zip(chunk, results):
            out[i].update(judge_label=label, judge_raw=raw, judge_model=judge_ep.model,
                          judge_prompt_version=J.JUDGE_PROMPT_VERSION, predicted_place=place)
        n_judged += len(chunk)
        finish(out)
        write_jsonl(jpath, out)
        log(f"  judge: {min(start + 200, len(todo))}/{len(todo)} "
            f"(no label so far: {sum(1 for (i, *_) in todo[:start + 200] if not out[i]['judge_label'])}; "
            f"calls {J.USAGE['calls']}, tokens in {J.USAGE['prompt_tokens']:,} / out {J.USAGE['completion_tokens']:,})")
    finish(out)
    write_jsonl(jpath, out)
    log(f"graded {len(out)} responses (judge: {n_judged} new, {n_cached} cached; "
        f"code-only: {sum(1 for o in out if o['final_source'] == 'code')})")
    return jpath


def _group(rows, keyf):
    g = defaultdict(list)
    for r in rows:
        g[keyf(r)].append(r)
    return {("|".join(k) if isinstance(k, tuple) else k): v for k, v in sorted(g.items())}


def compute_scores(dataset: Path, results: Path, bootstrap: int = 2000) -> dict:
    cases, lms = load_dataset(dataset)
    resp = {r["item_id"]: r for r in load_jsonl(results / "responses.jsonl")}
    judg = {j["item_id"]: j for j in load_jsonl(results / "judgements.jsonl")}
    rows = []
    for iid, j in judg.items():
        c, lm = cases[iid], lms[cases[iid]["landmark_qid"]]
        rows.append({"item_id": iid, "landmark_qid": lm["qid"], "arm": c["arm"], "qtype": c["question_type"],
                     "lang": c["lang"], "tier": lm["fame_tier"], "region": lm["language_region"],
                     "type": lm["type_group"], "label": j["final_label"], "code": j["code_label"],
                     "judge": j["judge_label"], "canton_correct": j["canton_correct"], "code_rule": j.get("code_rule"),
                     "text": (resp.get(iid) or {}).get("response_text") or ""})
    graded = [r for r in rows if r["label"]]
    lab = lambda rs: [r["label"] for r in rs]

    def table(rs, keyf):
        return {k: rates(lab(v)) for k, v in _group(rs, keyf).items()}

    main = [r for r in graded if r["arm"] == "photo_main"]
    s = {
        "model": sorted({r["model"] for r in resp.values()}),
        "coverage": {"test_cases": sum(1 for c in cases.values() if c.get("split", "main") == "main"),
                     "responses": len(resp), "graded": len(graded),
                     "status": dict(sorted(_count(r["status"] for r in resp.values()).items())),
                     "final_source": dict(sorted(_count(j["final_source"] for j in judg.values()).items()))},
        "overall_by_arm_qtype": table(graded, lambda r: (r["arm"], r["qtype"])),
        "photo_main_by_tier_qtype": table(main, lambda r: (r["tier"], r["qtype"])),
        "photo_main_by_region_qtype": table(main, lambda r: (r["region"], r["qtype"])),
        "photo_main_by_lang_qtype": table(main, lambda r: (r["lang"], r["qtype"])),
        "photo_main_by_type_qtype": table(main, lambda r: (r["type"], r["qtype"])),
        "text_only_by_tier_qtype": table([r for r in graded if r["arm"] == "text_only"], lambda r: (r["tier"], r["qtype"])),
        "traps": table([r for r in graded if r["arm"].startswith("trap")], lambda r: r["arm"]),
    }
    # H1: hallucination rate (incorrect / attempted) of naming from the main photo, low vs high fame
    def hall(rs):
        return rates(lab(rs))["hallucination_rate"]
    def h1(rs):
        lo = [r for r in rs if r["tier"] == "low"]
        hi = [r for r in rs if r["tier"] == "high"]
        a, b = hall(lo), hall(hi)
        return None if a is None or b is None else a - b
    name_main = [r for r in main if r["qtype"] == "name"]
    s["H1_name_hallucination_low_minus_high"] = {
        "estimate": h1(name_main),
        "ci95_cluster_bootstrap": cluster_bootstrap(name_main, h1, b=bootstrap) if bootstrap else None}
    for k, v in s["photo_main_by_tier_qtype"].items():
        n_att = v["correct"] + v["incorrect"]
        v["hallucination_ci95_wilson"] = wilson(v["incorrect"], n_att)
    # canton sub-score for place questions
    pl = [r for r in main if r["qtype"] == "place" and r["canton_correct"] is not None]
    s["photo_main_place_canton_correct_rate"] = sum(r["canton_correct"] for r in pl) / len(pl) if pl else None
    both = [r for r in graded if r["code"] and r["judge"]]
    s["agreement_judge_vs_code"] = {"n": len(both), "cohen_kappa": cohen_kappa([r["code"] for r in both], [r["judge"] for r in both]),
                                    "raw_agreement": (sum(r["code"] == r["judge"] for r in both) / len(both)) if both else None}
    from .agreement import agreement, self_consistency

    def in_dataset(rows):  # sampled items whose landmark the photo screening dropped later are left out (counted)
        kept = [r for r in rows if r["item_id"] in judg and r["item_id"] in cases]
        return kept, len({r["item_id"] for r in rows} - {r["item_id"] for r in kept})

    if (results / "human_audit.jsonl").exists():
        human, gone = in_dataset(load_jsonl(results / "human_audit.jsonl"))
        s["human_audit"] = agreement(human, judg, cases)
        s["human_audit"]["sampled_items_dropped_with_landmark"] = gone
        if (results / "human_audit_repeat.jsonl").exists():
            s["human_audit"]["self_consistency"] = self_consistency(human, load_jsonl(results / "human_audit_repeat.jsonl"))
    if (results / "human_check.jsonl").exists():
        # a person's grades on part of the audit sample, given with the second AI's proposed grade on screen (NOT
        # blind; tools/audit_online/build_check*.py): reported apart from the blind audit
        rows, gone = in_dataset(load_jsonl(results / "human_check.jsonl"))
        a = agreement(rows, judg, cases)
        ai_pairs = [(r["label"], r["ai_label_shown"]) for r in rows if r.get("ai_label_shown")]
        s["human_check"] = {
            "blind": False, "shown_to_annotator": "the second AI's proposed grade", "annotator": "A1",
            "items": a["items"], "sampled_items_dropped_with_landmark": gone,
            "judge_vs_human": a["judge_vs_human"], "code_vs_human": a["code_vs_human"],
            "ai_vs_human": {"n": len(ai_pairs), "raw_agreement": sum(x == y for x, y in ai_pairs) / len(ai_pairs),
                            "cohen_kappa": cohen_kappa([x for x, _ in ai_pairs], [y for _, y in ai_pairs])} if ai_pairs else None,
            "used_translation_rate": a["used_translation_rate"], "unsure_rate": a["unsure_rate"], "by_lang": a["by_lang"]}
    if (results / "ai_crosscheck_audit.jsonl").exists():
        # the audit sample graded by a second AI system (NOT the human audit): its agreement with the judge and code
        rows = load_jsonl(results / "ai_crosscheck_audit.jsonl")
        kept, gone = in_dataset(rows)
        a = agreement([r for r in kept if r.get("label")], judg, cases)

        def ai(c):  # the generic matrix is keyed "human_rows"; here the rows are the AI's labels
            return c and {("confusion_ai_rows" if k == "confusion_human_rows" else k): v for k, v in c.items()}
        s["ai_crosscheck_audit"] = {
            "reviewer": sorted({r["annotator_id"] for r in rows}), "not_a_human_audit": True, "sampled": len(rows),
            "sampled_items_dropped_with_landmark": gone,
            "left_unscored_as_uncertain": sum(1 for r in kept if not r.get("label")), "items": a["items"],
            "judge_vs_ai": ai(a["judge_vs_human"]), "code_vs_ai": ai(a["code_vs_human"]),
            "by_lang": {k: {"n": v["n"], "judge_vs_ai": v["judge_vs_human"], "code_vs_ai": v["code_vs_human"]}
                        for k, v in a["by_lang"].items()}}
    adj_path = results / "disagreement_adjudication.jsonl"
    if adj_path.exists():
        # sensitivity analysis (not the registered result): the judge's label replaced by the adjudicated label where
        # an independent two-read adjudication of a judge-vs-code disagreement settled it
        adj = {a["item_id"]: a["adjudicated_label"] for a in load_jsonl(adj_path) if a.get("adjudicated_label")}
        alt = [{**r, "label": adj.get(r["item_id"], r["label"])} for r in graded]
        alt_main = [r for r in alt if r["arm"] == "photo_main"]
        s["sensitivity_adjudicated"] = {
            "replaced": sum(1 for r in graded if r["item_id"] in adj and adj[r["item_id"]] != r["label"]),
            "overall_by_arm_qtype": table(alt, lambda r: (r["arm"], r["qtype"])),
            "photo_main_by_lang_qtype": table(alt_main, lambda r: (r["lang"], r["qtype"]))}
    # descriptive (analysis_plan.md, secondary): the same landmark, language and question on two photos
    s["photo_alt_vs_main"] = _paired(graded, "photo_main", "photo_alt", ("name", "place", "year"))
    s["lowinfo_vs_main_name"] = _paired(graded, "photo_main", "trap_lowinfo", ("name",))
    gz = load_gazetteer(dataset)
    if gz is not None:  # hypotheses H1b-H4 + location analysis need the gazetteer shipped with the dataset
        s["hypotheses"] = hypotheses(graded, gz, lms, cases, bootstrap=bootstrap)
        s["location_photo_main_place"] = location_analysis(
            [r for r in main if r["qtype"] == "place"], gz, lms)
    return rnd(s)


def _paired(rows, arm_a: str, arm_b: str, qtypes: tuple) -> dict:
    """Items of two arms paired on (landmark, language, question type): label rates on each arm and exact McNemar
    tests on 'correct' and on 'incorrect' (descriptive; not among the registered hypotheses)."""
    from .metrics import mcnemar
    key = lambda r: (r["landmark_qid"], r["lang"], r["qtype"])
    a = {key(r): r["label"] for r in rows if r["arm"] == arm_a}
    b = {key(r): r["label"] for r in rows if r["arm"] == arm_b}
    out = {}
    for q in qtypes:
        ks = sorted(k for k in set(a) & set(b) if k[2] == q)
        if not ks:
            continue
        la, lb = [a[k] for k in ks], [b[k] for k in ks]
        res = {"n_pairs": len(ks), "landmarks": len({k[0] for k in ks}), arm_a: rates(la), arm_b: rates(lb)}
        for lab in ("correct", "incorrect"):
            only_a = sum(x == lab and y != lab for x, y in zip(la, lb))
            only_b = sum(y == lab and x != lab for x, y in zip(la, lb))
            res[f"{lab}_only_{arm_a}"], res[f"{lab}_only_{arm_b}"] = only_a, only_b
            res[f"{lab}_mcnemar_p"] = mcnemar(only_a, only_b)
        out[q] = res
    return out


def _count(it):
    d = defaultdict(int)
    for x in it:
        d[x] += 1
    return d


def write_scores(scores: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scores, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
