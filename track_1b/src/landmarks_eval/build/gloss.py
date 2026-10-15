"""English machine glosses of answers for the human audit (annotation aid only; docs/ai_use_statement.md).

Only audit-sample items whose question is not in French (and whose answer is not empty) are glossed (the team
reads French and English).
The gloss keeps every proper name exactly as written, so annotators still compare names against the gold
themselves; the original answer stays authoritative and is shown next to the gloss. Same open-weights model as
the judge, temperature 0. Cached in <results>/glosses.jsonl by response hash.
"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import os
from pathlib import Path

from ..client import Endpoint, chat
from ..run import load_jsonl, write_jsonl

GLOSS_PROMPT_VERSION = "gloss-v1"
GLOSS_PARAMS = {"temperature": 0.0, "max_tokens": 1500}
PROMPT = ("Translate the following answer into plain English. Keep every name of a building, monument, place, "
          "canton or person exactly as written (do not translate, correct or complete names). Keep hedges such as "
          "\"not sure\" or \"maybe\". Output only the translation.\n\nANSWER:\n\"\"\"{answer}\"\"\"")


def _sha(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def make_glosses(dataset: Path, results: Path, ep: Endpoint, sample_path: Path, log=print) -> dict:
    cases = {c["item_id"]: c for c in load_jsonl(dataset / "data" / "test_cases.jsonl")}
    resp = {r["item_id"]: r for r in load_jsonl(results / "responses.jsonl")}
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    ids = sorted(sample["items"]) if isinstance(sample["items"], dict) else sorted(i["item_id"] for i in sample["items"])
    path = results / "glosses.jsonl"
    cache = {g["item_id"]: g for g in load_jsonl(path)} if path.exists() else {}
    todo, out = [], {}
    for i in ids:
        text = resp[i]["response_text"]
        if cases[i]["lang"] == "fr" or not (text or "").strip():
            continue
        g = cache.get(i)
        if g and g["response_sha256"] == _sha(text) and g["gloss_prompt_version"] == GLOSS_PROMPT_VERSION and g["gloss_en"]:
            out[i] = g
        else:
            todo.append(i)

    def one(i):
        res = chat(ep, [{"role": "user", "content": PROMPT.format(answer=resp[i]["response_text"])}], GLOSS_PARAMS)
        return {"item_id": i, "response_sha256": _sha(resp[i]["response_text"]), "gloss_en": (res.text or "").strip() or None,
                "gloss_model": ep.model, "gloss_prompt_version": GLOSS_PROMPT_VERSION,
                "label": "machine translation (annotation aid)", "error": res.error}

    with cf.ThreadPoolExecutor(max_workers=int(os.environ.get("JUDGE_CONCURRENCY", "4"))) as ex:
        for g in ex.map(one, todo):
            out[g["item_id"]] = g
    write_jsonl(path, [out[i] for i in sorted(out)])
    report = {"sample_items": len(ids), "glossed": sum(1 for g in out.values() if g["gloss_en"]),
              "new_calls": len(todo), "failed": sum(1 for g in out.values() if not g["gloss_en"])}
    log(json.dumps(report))
    return report
