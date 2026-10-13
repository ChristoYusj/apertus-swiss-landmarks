"""Query a model on the benchmark and store every response (resumable, content-hash cache)."""

from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
import random
import threading
from pathlib import Path

from . import __version__
from .client import Endpoint, build_messages, chat, supports_images
from .schema import Response, TestCase

GEN_PARAMS = {"temperature": 0.0, "top_p": 1.0, "max_tokens": 300, "seed": 1234}


def load_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def request_hash(model: str, case: dict, image_sha: str | None, params: dict) -> str:
    """Hash of everything that determines the answer (image by content hash, never by path)."""
    key = {"model": model, "question": case["question_text"], "image_sha256": image_sha,
           "prompt_version": case["prompt_version"], "params": params}
    return hashlib.sha256(json.dumps(key, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def stratified_sample(cases: list[dict], n: int, seed: int = 7) -> list[dict]:
    """Seeded sample keeping the arm x language x question-type mix."""
    rng = random.Random(seed)
    groups: dict[tuple, list[dict]] = {}
    for c in sorted(cases, key=lambda c: c["item_id"]):
        groups.setdefault((c["arm"], c["lang"], c["question_type"]), []).append(c)
    out = []
    for key in sorted(groups):
        g = groups[key]
        k = max(1, round(n * len(g) / len(cases)))
        out += rng.sample(g, min(k, len(g)))
    return sorted(out, key=lambda c: c["item_id"])[: max(n, len(groups))]


def run(dataset: Path, out_dir: Path, ep: Endpoint, sample: int | None = None,
        concurrency: int | None = None, log=print) -> Path:
    cases = load_jsonl(dataset / "data" / "test_cases.jsonl")
    for c in cases:
        TestCase.model_validate(c)
    cases = [c for c in cases if c.get("split", "main") == "main"]
    if sample:
        cases = stratified_sample(cases, sample)
    images: dict[str, bytes] = {}
    for c in cases:
        if c.get("image_id") and c["image_id"] not in images:
            images[c["image_id"]] = (dataset / "images" / f"{c['image_id']}.jpg").read_bytes()

    out_path = out_dir / "responses.jsonl"
    done: dict[str, dict] = {}
    previous = load_jsonl(out_path) if out_path.exists() else []
    for r in previous:
        if r["status"] == "ok":
            done[r["request_sha256"]] = r
    vision = supports_images(ep, next(iter(images.values()))) if images else True
    if not vision:
        log(f"{ep.model}: image input not accepted -> only text-only items will be asked")
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lock = threading.Lock()
    results: dict[str, dict] = {r["item_id"]: r for r in previous}  # keep rows of items not in this run

    def one(case: dict) -> dict:
        img = images.get(case.get("image_id"))
        img_sha = hashlib.sha256(img).hexdigest() if img else None
        rh = request_hash(ep.model, case, img_sha, GEN_PARAMS)
        if rh in done:
            return {**done[rh], "item_id": case["item_id"]}
        base = {"item_id": case["item_id"], "model": ep.model, "endpoint_host": ep.host, "params": GEN_PARAMS,
                "prompt_version": case["prompt_version"], "request_sha256": rh, "run_id": run_id,
                "harness_version": __version__}
        if img and not vision:
            row = {**base, "response_text": None, "status": "skipped_no_vision", "error": "model has no image input",
                   "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        else:
            res = chat(ep, build_messages(case["question_text"], img), GEN_PARAMS)
            row = {**base, "response_text": res.text, "status": res.status, "finish_reason": res.finish_reason,
                   "usage": res.usage, "latency_s": res.latency_s, "returned_model_id": res.returned_model,
                   "error": res.error, "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        Response.model_validate(row)
        return row

    workers = concurrency or int(os.environ.get("LLM_CONCURRENCY", "4"))
    todo = [c for c in cases]
    n_cached = sum(1 for c in todo if request_hash(ep.model, c, hashlib.sha256(images[c["image_id"]]).hexdigest()
                                                   if c.get("image_id") else None, GEN_PARAMS) in done)
    log(f"{len(todo)} items ({n_cached} already answered, {len(todo) - n_cached} to query) with {workers} workers")
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for i, row in enumerate(pool.map(one, todo), 1):
            with lock:
                results[row["item_id"]] = row
                if i % 50 == 0 or i == len(todo):
                    write_jsonl(out_path, sorted(results.values(), key=lambda r: r["item_id"]))
                    log(f"  {i}/{len(todo)} done")
    write_jsonl(out_path, sorted(results.values(), key=lambda r: r["item_id"]))
    return out_path
